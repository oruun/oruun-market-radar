"""
fetch_hackernews.py
-------------------
Hacker News search via the Algolia-hosted public API. Free, no auth.

  https://hn.algolia.com/api/v1/search?query=<term>&tags=story&numericFilters=...

We pull last-12-month and prior-12-month story counts per brand
to compute YoY growth in tech-savvy/quantified-self runner chatter.
"""
from __future__ import annotations
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

UA = "oruun-market-radar/0.2"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA})


def load_config() -> dict:
    with open(ROOT / "keywords.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def hn_count(term: str, since_unix: int, before_unix: int) -> tuple[int, list[dict]]:
    """Returns (count, top_stories[:5]) for HN stories matching term in window."""
    q = term
    url = "https://hn.algolia.com/api/v1/search"
    params = {
        "query": q,
        "tags": "story",
        "numericFilters": f"created_at_i>={since_unix},created_at_i<{before_unix}",
        "hitsPerPage": 5,
    }
    try:
        r = SESSION.get(url, params=params, timeout=15)
        r.raise_for_status()
        j = r.json()
        total = int(j.get("nbHits", 0))
        hits = []
        for h in j.get("hits", []):
            hits.append({
                "title": h.get("title") or h.get("story_title") or "",
                "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID','')}",
                "points": int(h.get("points") or 0),
                "num_comments": int(h.get("num_comments") or 0),
                "created_at": h.get("created_at"),
            })
        return total, hits
    except Exception as e:
        print(f"  HN failed '{term}': {e}", flush=True)
        return 0, []


def main() -> None:
    cfg = load_config()
    brands = cfg.get("brands", [])

    now = datetime.now(timezone.utc)
    one_year = int((now - timedelta(days=365)).timestamp())
    two_years = int((now - timedelta(days=730)).timestamp())
    now_ts = int(now.timestamp())

    rows = []
    for brand in brands:
        # HN is noisy with single-word terms like "on" or "satisfy" — quote them.
        q = f'"{brand}" running' if len(brand) <= 4 else brand
        recent_n, recent_hits = hn_count(q, one_year, now_ts)
        prior_n, _ = hn_count(q, two_years, one_year)
        yoy = ((recent_n - prior_n) / prior_n * 100.0) if prior_n > 0 else 0.0
        rows.append({
            "brand": brand,
            "query": q,
            "recent_12m_count": recent_n,
            "prior_12m_count": prior_n,
            "yoy_pct": round(yoy, 1),
            "top_stories": recent_hits,
        })
        time.sleep(0.3)

    out = {"fetched_at": now.isoformat(), "rows": rows}
    target = DATA_DIR / "hackernews_raw.json"
    target.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {target}  ({len(rows)} brands)")


if __name__ == "__main__":
    main()
