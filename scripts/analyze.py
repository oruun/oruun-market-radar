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
def classify_brand_signal(trends_yoy: float, wiki_yoy_v: float, gdelt_yoy_v: float, hn_yoy: float) -> str:
    """Maps the 4 YoY signals to a brand-status label.
    Mirrors the user's reference table semantics."""
    signals = {
        "trends": trends_yoy,
        "wiki": wiki_yoy_v,
        "gdelt": gdelt_yoy_v,
        "hn": hn_yoy,
    }
    strong = sum(1 for v in signals.values() if v > 30)
    moderate = sum(1 for v in signals.values() if 5 < v <= 30)
    flat = sum(1 for v in signals.values() if -5 <= v <= 5)
    declining = sum(1 for v in signals.values() if v < -5)
    available = sum(1 for v in signals.values() if v != 0.0)

    if strong >= 3:
        return "Authentic"          # 多源大涨 → 真热度
    if strong + moderate >= 3 and declining == 0:
        return "Rising"             # 多源上升 → 上升期
    if declining >= 2:
        return "Saturated"          # 多源下行 → 饱和/触顶
    if strong >= 1 and declining >= 1:
        return "Mixed"              # 信号冲突 → 需深挖
    if available == 0:
        return "Unknown"
    if flat >= 2:
        return "Mature"             # 多源平稳 → 成熟期
    return "Mixed"


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> None:
    cfg = load_config()
    brands = [b.lower().strip() for b in cfg.get("brands", [])]
    brand_set = set(brands)

    trends = safe_load(DATA_DIR / "trends_raw.json")
    if not trends:
        raise SystemExit("missing data/trends_raw.json — run fetch_trends.py first")
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

    # ------- Per-brand cross-source validation -------
    # Build lookup tables
    trends_by_brand: dict[str, float] = {}
    for s in trends["series"]:
        if s["category"] == "brand":
            avg = average_across_geos(s["geo_series"])
            trends_by_brand[s["term"].lower()] = yoy_pct([float(v) for v in avg], 26) if avg else 0.0

    wiki_by_brand: dict[str, tuple[float, list[dict], str | None]] = {}
    for w in wiki.get("brands", []):
        yoy_v, monthly = wiki_yoy(w.get("daily") or [])
        wiki_by_brand[w["brand"].lower()] = (yoy_v, monthly, w.get("article"))

    gdelt_by_term: dict[str, tuple[float, list[dict]]] = {}
    for r in gdelt.get("rows", []):
        yoy_v, monthly = gdelt_yoy(r.get("timeline") or [])
        gdelt_by_term[r["term"].lower()] = (yoy_v, monthly)

    hn_by_brand: dict[str, tuple[float, int, list]] = {}
    for r in hn.get("rows", []):
        hn_by_brand[r["brand"].lower()] = (
            float(r.get("yoy_pct", 0.0)),
            int(r.get("recent_12m_count", 0)),
            r.get("top_stories") or [],
        )

    cross_rows = []
    for brand in brands:
        t_yoy = trends_by_brand.get(brand, 0.0)
        w_yoy, w_monthly, w_article = wiki_by_brand.get(brand, (0.0, [], None))
        g_yoy, g_monthly = gdelt_by_term.get(brand, (0.0, []))
        h_yoy, h_count, h_stories = hn_by_brand.get(brand, (0.0, 0, []))

        verdict = classify_brand_signal(t_yoy, w_yoy, g_yoy, h_yoy)
        cross_rows.append({
            "brand": brand,
            "trends_yoy_pct": round(t_yoy, 1),
            "wiki_yoy_pct": round(w_yoy, 1),
            "gdelt_yoy_pct": round(g_yoy, 1),
            "hn_yoy_pct": round(h_yoy, 1),
            "wiki_monthly": w_monthly,
            "gdelt_monthly": g_monthly,
            "hn_count_12m": h_count,
            "hn_top_stories": h_stories[:3],
            "wiki_article": w_article,
            "verdict": verdict,
        })
    # Order: Authentic / Rising first
    order = {"Authentic": 0, "Rising": 1, "Mixed": 2, "Mature": 3, "Saturated": 4, "Unknown": 5}
    cross_rows.sort(key=lambda r: (order.get(r["verdict"], 99), -r["trends_yoy_pct"]))

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
    for r in auto.get("rows", []):
        suggs = r.get("suggestions") or []
        # Classify each suggestion
        intents: Counter = Counter()
        annotated = []
        for s in suggs:
            label = classify_query(s, brand_set)
            intents[label] += 1
            annotated.append({"text": s, "intent": label})
        autocomplete_rows.append({
            "term": r["term"],
            "category": r["category"],
            "suggestions": annotated,
            "intent_breakdown": [{"intent": k, "count": v} for k, v in intents.most_common()],
        })

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


if __name__ == "__main__":
    main()
