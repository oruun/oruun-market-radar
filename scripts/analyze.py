"""
analyze.py — cross-source aggregator and intent classifier.

Inputs (any subset is fine; missing files are gracefully skipped):
  data/trends_raw.json        ← Google Trends + related queries (REQUIRED)
  data/wikipedia_raw.json     ← Wikipedia pageviews per brand
  data/gdelt_raw.json         ← Global news mention volume
  data/hackernews_raw.json    ← Tech-savvy chatter
  data/autocomplete_raw.json  ← Live Google search suggestions
  data/reddit_raw.json        ← Reddit posts (optional, can be skipped)

Output: data/analyzed.json — single source of truth for the dashboard.
"""
from __future__ import annotations
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def load_config() -> dict:
    with open(ROOT / "keywords.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def safe_load(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  warn: failed to load {path}: {e}", flush=True)
        return None


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def average_across_geos(geo_series: dict[str, list[dict]]) -> list[int]:
    arrays = [[p["value"] for p in s] for s in geo_series.values() if s]
    if not arrays:
        return []
    n = min(len(a) for a in arrays)
    arrays = [a[-n:] for a in arrays]
    return [int(round(sum(col) / len(col))) for col in zip(*arrays)]


def latest_index(values: list[int], window: int = 4) -> float:
    if not values:
        return 0.0
    tail = values[-window:] if len(values) >= window else values
    return float(np.mean(tail))


def yoy_pct(values: list[float], half_window: int = 26) -> float:
    """Year-over-year % change: last `half_window` weeks vs the prior `half_window`."""
    if len(values) < half_window * 2:
        return 0.0
    recent = float(np.mean(values[-half_window:]))
    prior = float(np.mean(values[-half_window * 2:-half_window]))
    if prior < 0.001:
        return 0.0
    return round((recent - prior) / prior * 100.0, 1)


def wow_pct(values: list[int], window: int = 4) -> float:
    if len(values) < window * 2:
        return 0.0
    recent = float(np.mean(values[-window:]))
    prior = float(np.mean(values[-window * 2:-window]))
    if prior < 0.5:
        return 0.0
    return round((recent - prior) / prior * 100.0, 1)


# ----------------------------------------------------------------------
# Buyer-intent classifier
# ----------------------------------------------------------------------
INFORMATIONAL_TOKENS = [
    "what", "how", "why", "guide", "vs", "comparison", "explain", "meaning",
    "mean", "tutorial", "example", "definition", "wiki",
]
COMMERCIAL_TOKENS = [
    "review", "reviews", "best", "top", "vs", "compared", "comparison",
    "alternative", "rated", "rating", "ranking", "ranked", "worth it",
    "pros and cons", "should i",
]
TRANSACTIONAL_TOKENS = [
    "buy", "purchase", "where to buy", "discount", "sale", "deal", "code",
    "coupon", "promo", "cheap", "cheapest", "near me", "in stock", "shop",
    "order", "checkout", "free shipping", "size", "sizes", "size chart",
    "amazon", "rei", "running warehouse", "returns",
]


def classify_query(q: str, brand_set: set[str]) -> str:
    """Returns one of: branded, transactional, commercial, informational, generic"""
    s = q.lower().strip()
    # Branded if any brand name appears
    for b in brand_set:
        if b and re.search(r"\b" + re.escape(b) + r"\b", s):
            return "branded"
    if any(t in s for t in TRANSACTIONAL_TOKENS):
        return "transactional"
    if any(t in s for t in COMMERCIAL_TOKENS):
        return "commercial"
    if any(t in s for t in INFORMATIONAL_TOKENS):
        return "informational"
    return "generic"


# ----------------------------------------------------------------------
# Wikipedia → YoY pageviews
# ----------------------------------------------------------------------
def wiki_yoy(daily: list[dict]) -> tuple[float, list[dict]]:
    """Daily list → (YoY % change, monthly buckets last 12m)"""
    if not daily:
        return 0.0, []
    # Aggregate to month-end totals
    months: dict[str, int] = defaultdict(int)
    for d in daily:
        key = d["date"][:7]
        months[key] += int(d["views"])
    keys = sorted(months.keys())
    monthly = [{"month": k, "views": months[k]} for k in keys]
    if len(monthly) < 13:
        return 0.0, monthly[-12:]
    last12 = sum(m["views"] for m in monthly[-12:])
    prior12 = sum(m["views"] for m in monthly[-24:-12]) if len(monthly) >= 24 else last12
    yoy = ((last12 - prior12) / prior12 * 100.0) if prior12 > 0 else 0.0
    return round(yoy, 1), monthly[-12:]


# ----------------------------------------------------------------------
# GDELT → YoY news volume + monthly series
# ----------------------------------------------------------------------
def gdelt_yoy(timeline: list[dict]) -> tuple[float, list[dict]]:
    if not timeline:
        return 0.0, []
    # Sort by date, bucket by year-month
    months: dict[str, list[float]] = defaultdict(list)
    for d in timeline:
        m = d.get("date", "")[:7]
        if m:
            months[m].append(float(d.get("value", 0)))
    keys = sorted(months.keys())
    monthly = [{"month": k, "value": round(float(np.mean(months[k])), 4)} for k in keys]
    vals = [m["value"] for m in monthly]
    yoy = yoy_pct(vals, half_window=6) if len(vals) >= 12 else 0.0
    return yoy, monthly[-12:]


# ----------------------------------------------------------------------
# Cross-source classification
# ----------------------------------------------------------------------
def classify_brand_signal(trends_yoy, wiki_yoy_v, gdelt_yoy_v, hn_yoy) -> str:
    """Maps the 4 YoY signals to a brand-status label.

    CRITICAL: None means "no data from this source" — those signals are
    excluded from classification. Treating missing-data as zero would make
    quiet brands look falsely "Mature".
    """
    raw = {
        "trends": trends_yoy,
        "wiki": wiki_yoy_v,
        "gdelt": gdelt_yoy_v,
        "hn": hn_yoy,
    }
    real = {k: v for k, v in raw.items() if v is not None}
    if len(real) == 0:
        return "Unknown"
    if len(real) < 2:
        # Single-signal evidence is never enough to call a verdict.
        return "Insufficient data"

    strong = sum(1 for v in real.values() if v > 30)
    moderate = sum(1 for v in real.values() if 5 < v <= 30)
    flat = sum(1 for v in real.values() if -5 <= v <= 5)
    declining = sum(1 for v in real.values() if v < -5)

    n = len(real)
    if strong >= max(2, n - 1):                       # almost all sources strongly up
        return "Authentic"
    if (strong + moderate) >= max(2, n - 1) and declining == 0:
        return "Rising"
    if declining >= max(2, n - 1):
        return "Saturated"
    if strong >= 1 and declining >= 1:
        return "Mixed"
    if flat >= max(2, n - 1):
        return "Mature"
    return "Mixed"


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> None:
    cfg = load_config()
    brands = [b.lower().strip() for b in cfg.get("brands", [])]
    brand_set = set(brands)

    trends = safe_load(DATA_DIR / "trends_raw.json")
    if not trends or not trends.get("series"):
        # Soft-fail: emit a minimal scaffold so the rest of the pipeline can run
        # even if Trends was rate-limited or timed out in this job.
        print("WARN: trends_raw.json missing or empty — continuing with other sources", flush=True)
        trends = {"fetched_at": None, "timeframe": "today 12-m", "series": []}
    wiki = safe_load(DATA_DIR / "wikipedia_raw.json") or {"brands": []}
    gdelt = safe_load(DATA_DIR / "gdelt_raw.json") or {"rows": []}
    hn = safe_load(DATA_DIR / "hackernews_raw.json") or {"rows": []}
    auto = safe_load(DATA_DIR / "autocomplete_raw.json") or {"rows": []}
    reddit = safe_load(DATA_DIR / "reddit_raw.json") or {"posts": [], "skipped": True}

    # ------- Per-keyword analysis -------
    keyword_rows: list[dict] = []
    intent_global: Counter = Counter()

    for s in trends["series"]:
        avg_series = average_across_geos(s["geo_series"])
        if not avg_series:
            continue
        vol = latest_index(avg_series, 4)
        wow = wow_pct(avg_series, 4)
        yoy = yoy_pct([float(v) for v in avg_series], half_window=26)

        # Related queries → intent breakdown
        related = s.get("related") or {}
        top_q = related.get("top") or []
        rising_q = related.get("rising") or []
        intent_counts: Counter = Counter()
        for q in top_q + rising_q:
            label = classify_query(q.get("query", ""), brand_set)
            intent_counts[label] += 1
            intent_global[label] += 1
        intent_breakdown = [
            {"intent": k, "count": v}
            for k, v in intent_counts.most_common()
        ]

        # Reddit saturation (denominator for blue-ocean score)
        sat = 0
        for post in reddit.get("posts", []):
            blob = " ".join([
                post.get("title", ""),
                post.get("selftext", ""),
                *post.get("comments", []),
            ]).lower()
            sat += blob.count(s["term"].lower())

        weights = cfg.get("opportunity_weights", {})
        if vol < weights.get("volume_floor", 5):
            opp = 0.0
        else:
            growth_factor = max(0.0, 1.0 + wow / 100.0)
            opp = vol * growth_factor / (sat + weights.get("saturation_epsilon", 1))

        last_date = ""
        for series in s["geo_series"].values():
            if series:
                last_date = series[-1]["date"]
                break

        keyword_rows.append({
            "term": s["term"],
            "category": s["category"],
            "volume_index": round(vol, 1),
            "wow_change_pct": round(wow, 1),
            "yoy_change_pct": yoy,
            "reddit_mentions": sat,
            "opportunity_score": round(opp, 1),
            "history": [
                {"date": p["date"], "value": v}
                for p, v in zip(
                    next(iter(s["geo_series"].values())) or [],
                    avg_series,
                )
            ][-52:],
            "last_date": last_date,
            "related_top": top_q[:15],
            "related_rising": rising_q[:15],
            "intent_breakdown": intent_breakdown,
        })

    keyword_rows.sort(key=lambda r: -r["opportunity_score"])

    # Brand cross-source validation removed by design — this dashboard now
    # tracks CONSUMER SEARCH TERMS only. Brand list still exists in
    # keywords.yaml solely to power the buyer-intent classifier
    # (e.g. "nike pegasus review" → branded intent).
    cross_rows: list[dict] = []

    # ------- Buyer journey aggregation -------
    # Brand-category rows are intentionally excluded — buyer journey is about
    # CONSUMER SEARCH INTENT for product/feature/use-case terms, not about
    # brand-name searches. Brand health is shown separately in the
    # Cross-source validation card.
    journey_pool = [k for k in keyword_rows if k["category"] != "brand"]
    journey = []
    for kw in journey_pool[:20]:  # top 20 non-brand keywords by opportunity
        breakdown = {b["intent"]: b["count"] for b in kw["intent_breakdown"]}
        total = sum(breakdown.values()) or 1
        journey.append({
            "term": kw["term"],
            "category": kw["category"],
            "volume_index": kw["volume_index"],
            "intent_pct": {
                k: round(100.0 * breakdown.get(k, 0) / total, 1)
                for k in ("informational", "commercial", "transactional", "branded", "generic")
            },
            "rising_queries": [q["query"] for q in kw["related_rising"][:8]],
            "top_queries": [q["query"] for q in kw["related_top"][:8]],
        })

    # ------- Autocomplete (long-tail intent) -------
    autocomplete_rows = []
    all_suggestions: list[dict] = []          # flat list across all seeds, used for aggregations
    for r in auto.get("rows", []):
        suggs = r.get("suggestions") or []
        sources = {s["text"]: s.get("from", "raw") for s in (r.get("suggestion_sources") or [])}
        intents: Counter = Counter()
        annotated = []
        for s in suggs:
            label = classify_query(s, brand_set)
            intents[label] += 1
            entry = {"text": s, "intent": label, "from": sources.get(s, "raw")}
            annotated.append(entry)
            all_suggestions.append({**entry, "seed": r["term"], "category": r["category"]})
        autocomplete_rows.append({
            "term": r["term"],
            "category": r["category"],
            "suggestions": annotated,
            "intent_breakdown": [{"intent": k, "count": v} for k, v in intents.most_common()],
        })

    # ----- Aggregation A: top buying-intent terms across ALL seeds -----
    # Transactional + Commercial only — sorted by uniqueness (longer/more specific first)
    buying_intent = [s for s in all_suggestions if s["intent"] in ("transactional", "commercial")]
    seen_text: set[str] = set()
    buying_intent_unique = []
    for s in buying_intent:
        key = s["text"].lower()
        if key in seen_text:
            continue
        seen_text.add(key)
        buying_intent_unique.append(s)
    buying_intent_unique.sort(key=lambda s: (-len(s["text"]),))  # longer = more specific niche
    top_buying_intent = buying_intent_unique[:30]

    # ----- Aggregation B: brand share-of-voice IN AUTOCOMPLETE -----
    # Replaces the brand-cross-source signal we lost when removing Wikipedia/GDELT/HN.
    brand_mentions_ac: Counter = Counter()
    for s in all_suggestions:
        text = s["text"].lower()
        for b in brand_set:
            if not b:
                continue
            if re.search(r"\b" + re.escape(b) + r"\b", text):
                brand_mentions_ac[b] += 1
    total_brand_mentions = sum(brand_mentions_ac.values()) or 1
    brand_sov_autocomplete = sorted(
        [
            {
                "brand": b,
                "mentions": c,
                "share_pct": round(100.0 * c / total_brand_mentions, 2),
            }
            for b, c in brand_mentions_ac.items() if c > 0
        ],
        key=lambda r: -r["mentions"],
    )

    # ----- Aggregation C: long-tail niche discoveries -----
    # Suggestions that are 5+ words, unique, NOT branded — these are the
    # niche/specific queries with low competition.
    long_tail = []
    seen_tail: set[str] = set()
    for s in all_suggestions:
        if s["intent"] == "branded":
            continue
        words = s["text"].split()
        if len(words) < 5:
            continue
        key = s["text"].lower()
        if key in seen_tail:
            continue
        seen_tail.add(key)
        long_tail.append(s)
    long_tail.sort(key=lambda s: (-len(s["text"].split()),))
    long_tail = long_tail[:25]

    # ------- Pain points (Reddit, optional) -------
    pain_points = []
    pain_triggers = []
    pain_summary = None
    if not reddit.get("skipped") and reddit.get("posts"):
        from analyze_reddit_helpers import (
            extract_pain_points,
            trigger_frequency,
            brand_sentiment,
            brand_mentions,
            claude_summary,
        )
        pain_points = extract_pain_points(reddit["posts"], top_n=40)
        pain_triggers = trigger_frequency(pain_points)
        pain_summary = claude_summary(pain_points) if os.environ.get("ANTHROPIC_API_KEY") else None
        sentiment = brand_sentiment(reddit["posts"], brands)
        bcounts = brand_mentions(reddit["posts"], brands)
        total_m = sum(bcounts.values()) or 1
        sov = sorted(
            [{"brand": b, "mentions": c, "share_pct": round(100.0 * c / total_m, 2)}
             for b, c in bcounts.items()],
            key=lambda r: -r["mentions"],
        )
    else:
        sentiment = {}
        sov = []

    # ------- Final payload -------
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trends_fetched_at": trends.get("fetched_at"),
        "wiki_fetched_at": wiki.get("fetched_at") if wiki else None,
        "gdelt_fetched_at": gdelt.get("fetched_at") if gdelt else None,
        "hn_fetched_at": hn.get("fetched_at") if hn else None,
        "autocomplete_fetched_at": auto.get("fetched_at") if auto else None,
        "reddit_fetched_at": reddit.get("fetched_at"),
        "reddit_posts_analyzed": len(reddit.get("posts", [])),
        "timeframe": trends.get("timeframe"),
        "data_sources_active": [
            x for x, v in [
                ("Google Trends", bool(trends and trends.get("series"))),
                ("Wikipedia", bool(wiki and wiki.get("brands"))),
                ("GDELT News", bool(gdelt and gdelt.get("rows"))),
                ("Hacker News", bool(hn and hn.get("rows"))),
                ("Autocomplete", bool(auto and auto.get("rows"))),
                ("Reddit", not reddit.get("skipped") and bool(reddit.get("posts"))),
            ] if v
        ],
        "keywords": keyword_rows,
        "cross_source_validation": cross_rows,
        "buyer_journey": journey,
        "autocomplete": autocomplete_rows,
        "top_buying_intent": top_buying_intent,
        "brand_sov_autocomplete": brand_sov_autocomplete,
        "long_tail": long_tail,
        "intent_global": [{"intent": k, "count": v} for k, v in intent_global.most_common()],
        "brand_share_of_voice": sov,
        "brand_sentiment": sentiment,
        "pain_points": pain_points,
        "pain_triggers": pain_triggers,
        "pain_summary": pain_summary,
    }
    target = DATA_DIR / "analyzed.json"
    target.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {target}")
    print(f"Active sources: {', '.join(out['data_sources_active'])}")


def write_minimal_output(error_msg: str = "") -> None:
    """Last-resort writer so build_dashboard_data.py always has a file to copy.
    Called if main() crashes for any reason."""
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_sources_active": [],
        "keywords": [],
        "cross_source_validation": [],
        "buyer_journey": [],
        "autocomplete": [],
        "intent_global": [],
        "brand_share_of_voice": [],
        "brand_sentiment": {},
        "pain_points": [],
        "pain_triggers": [],
        "pain_summary": None,
        "reddit_posts_analyzed": 0,
        "timeframe": "today 12-m",
        "error": error_msg or None,
    }
    target = DATA_DIR / "analyzed.json"
    target.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote minimal {target} (error: {error_msg})", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        write_minimal_output(f"analyze crashed: {type(e).__name__}: {e}")
