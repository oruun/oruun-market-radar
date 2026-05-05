"""
fetch_autocomplete.py
---------------------
Pulls Google Search autocomplete suggestions for each tracked keyword.

Endpoint: https://suggestqueries.google.com/complete/search?client=chrome&q=<term>

Returns the actual unfiltered suggestion stream — i.e. what Google thinks
the average user is typing next. Pure goldmine for understanding intent.

We pull two sets:
  • bare term ("trail running shoes")
  • "<term> " (with trailing space → "long-tail" suggestions)

Output: data/autocomplete_raw.json
"""
from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; oruun-market-radar/0.2)"})


def load_config() -> dict:
    with open(ROOT / "keywords.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_suggestions(term: str, hl: str = "en", gl: str = "us") -> list[str]:
    url = "https://suggestqueries.google.com/complete/search"
    params = {"client": "chrome", "q": term, "hl": hl, "gl": gl}
    try:
        r = SESSION.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return []
        # response is JSON-array-shaped: [query, [suggestions], [], [], {meta}]
        arr = r.json()
        if isinstance(arr, list) and len(arr) > 1 and isinstance(arr[1], list):
            return [str(s) for s in arr[1]]
    except Exception as e:
        print(f"  autocomplete failed '{term}': {e}", flush=True)
    return []


def main() -> None:
    cfg = load_config()
    # Track autocomplete for product_category, feature_material, use_case_persona
    # (skip brand & competitor — those autocompletes are mostly product names).
    seeds: list[tuple[str, str]] = []
    for cat in ("product_category", "feature_material", "use_case_persona"):
        for term in cfg.get("categories", {}).get(cat, []):
            seeds.append((term, cat))

    rows = []
    for term, category in seeds:
        bare = fetch_suggestions(term)
        time.sleep(0.4)
        long_tail = fetch_suggestions(term + " ")
        time.sleep(0.4)
        # Combine, dedupe, preserve order
        seen, merged = set(), []
        for s in bare + long_tail:
            sl = s.lower().strip()
            if sl and sl not in seen and sl != term.lower():
                seen.add(sl)
                merged.append(s)
        rows.append({"term": term, "category": category, "suggestions": merged[:25]})
        print(f"[autocomplete] {term:<30s} → {len(merged)} suggestions", flush=True)

    out = {"fetched_at": datetime.now(timezone.utc).isoformat(), "rows": rows}
    target = DATA_DIR / "autocomplete_raw.json"
    target.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {target}  ({len(rows)} terms)")


if __name__ == "__main__":
    main()
