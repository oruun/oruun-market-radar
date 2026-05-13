"""
fetch_autocomplete.py
---------------------
Pulls Google Search autocomplete suggestions for each tracked keyword
across 10 intent-targeted variations.

Endpoint: https://suggestqueries.google.com/complete/search?client=chrome&q=<term>

For each seed term we query:
  bare        — what does Google autocomplete first  (general)
  seed + " "  — long-tail completions               (general)
  seed + " for"      — persona/use-case
  seed + " vs"       — comparison intent
  seed + " best"     — commercial decision
  seed + " review"   — decision-stage research
  seed + " 2026"     — temporal / fresh-product hunt
  seed + " cheap"    — price-sensitive transactional
  seed + " alternative" — switching / replacement
  seed + " reddit"   — community-driven research
  "best " + seed     — prefix variation (what tops "best X" searches)

Output: data/autocomplete_raw.json
"""
from __future__ import annotations
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; oruun-market-radar/0.4)"})

# Variations to query per seed term. Order matters — earlier ones get priority
# in deduplication so the most "natural" completions stay at the top.
VARIATIONS = [
    ("",                "raw"),         # bare seed
    (" ",               "raw"),         # long-tail
    (" for",            "persona"),
    (" vs",             "comparison"),
    (" best",           "commercial"),
    (" review",         "decision"),
    (" 2026",           "fresh"),
    (" cheap",          "price"),
    (" alternative",    "switching"),
    (" reddit",         "community"),
    ("best ",           "prefix"),      # prepended, not appended
]


def load_config() -> dict:
    with open(ROOT / "keywords.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_suggestions(query: str, hl: str = "en", gl: str = "us") -> list[str]:
    """Returns Google's autocomplete suggestions for `query`."""
    url = "https://suggestqueries.google.com/complete/search"
    params = {"client": "chrome", "q": query, "hl": hl, "gl": gl}
    try:
        r = SESSION.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return []
        arr = r.json()
        if isinstance(arr, list) and len(arr) > 1 and isinstance(arr[1], list):
            return [str(s) for s in arr[1]]
    except Exception as e:
        print(f"  autocomplete failed '{query}': {e}", flush=True)
    return []


def build_query(seed: str, variation: str) -> str:
    """Handles both suffix variations (' for', ' vs', etc.) and the 'best <seed>' prefix."""
    if variation == "best ":          # prefix variation
        return f"best {seed}"
    return f"{seed}{variation}"


def main() -> None:
    cfg = load_config()
    # Pull autocomplete for all four consumer-search categories.
    seeds: list[tuple[str, str]] = []
    for cat in ("product_category", "competitor_keyword", "feature_material", "use_case_persona"):
        for term in cfg.get("categories", {}).get(cat, []):
            seeds.append((term, cat))

    rows = []
    for i, (seed, category) in enumerate(seeds):
        # For each seed, hit all 11 variations, then dedupe.
        seen: set[str] = set()
        merged: list[dict] = []

        for variation, vlabel in VARIATIONS:
            query = build_query(seed, variation)
            suggs = fetch_suggestions(query)
            for s in suggs:
                key = s.lower().strip()
                if not key or key == seed.lower() or key in seen:
                    continue
                seen.add(key)
                merged.append({"text": s, "from": vlabel})
            # polite delay between variations
            time.sleep(0.4 + random.uniform(0, 0.2))

        # Cap at 60 per seed to keep payload reasonable
        merged = merged[:60]
        rows.append({
            "term": seed,
            "category": category,
            "suggestions": [m["text"] for m in merged],          # back-compat: just strings
            "suggestion_sources": merged,                         # which variation produced each
        })
        print(f"[autocomplete {i+1}/{len(seeds)}] {seed:<30s} -> {len(merged)} unique suggestions", flush=True)

    out = {"fetched_at": datetime.now(timezone.utc).isoformat(), "rows": rows}
    target = DATA_DIR / "autocomplete_raw.json"
    target.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    total = sum(len(r["suggestions"]) for r in rows)
    print(f"\nWrote {target}  ({len(rows)} terms, {total} total suggestions)")


if __name__ == "__main__":
    main()
