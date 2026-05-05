"""
fetch_wikipedia.py
------------------
Pulls 12 months of daily English Wikipedia pageviews for each brand
in keywords.yaml. The Wikipedia REST API is fully open — no key, no auth.

Endpoint:
  https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/
    en.wikipedia/all-access/all-agents/{ARTICLE}/daily/{START}/{END}

Pageview growth = "deep research" interest. People who land on a brand's
Wikipedia page have already moved past discovery; they're comparing.

Output: data/wikipedia_raw.json
"""
from __future__ import annotations
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

UA = "oruun-market-radar/0.2 (https://github.com/oruun)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA})


def load_config() -> dict:
    with open(ROOT / "keywords.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def best_article_title(brand: str, override_map: dict) -> str | None:
    """Resolves a brand name to its English Wikipedia article title.
    Uses (1) explicit override in keywords.yaml, then (2) MediaWiki search API."""
    if brand in override_map:
        return override_map[brand]
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": brand,
        "srlimit": 1,
        "format": "json",
    }
    try:
        r = SESSION.get(url, params=params, timeout=15)
        r.raise_for_status()
        results = (r.json().get("query") or {}).get("search") or []
        if results:
            return results[0]["title"]
    except Exception as e:
        print(f"  search failed for '{brand}': {e}", flush=True)
    return None


def fetch_pageviews(article: str, start: str, end: str) -> list[dict]:
    """Returns daily pageview dicts: [{date: 'YYYY-MM-DD', views: int}, ...]"""
    article_url = quote(article.replace(" ", "_"), safe="")
    url = (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"en.wikipedia/all-access/all-agents/{article_url}/daily/{start}/{end}"
    )
    try:
        r = SESSION.get(url, timeout=20)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        items = r.json().get("items") or []
        return [
            {
                "date": f"{i['timestamp'][:4]}-{i['timestamp'][4:6]}-{i['timestamp'][6:8]}",
                "views": int(i.get("views", 0)),
            }
            for i in items
        ]
    except Exception as e:
        print(f"  pageviews failed for '{article}': {e}", flush=True)
        return []


def main() -> None:
    cfg = load_config()
    brands = cfg.get("brands", [])
    overrides = cfg.get("wikipedia_titles", {}) or {}

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=395)  # ~13 months for clean YoY math
    s = start.strftime("%Y%m%d")
    e = end.strftime("%Y%m%d")

    out_brands: list[dict] = []
    for brand in brands:
        title = best_article_title(brand, overrides)
        if not title:
            print(f"[wiki] {brand:<20s} → no article found", flush=True)
            out_brands.append({"brand": brand, "article": None, "daily": []})
            continue
        print(f"[wiki] {brand:<20s} → {title}", flush=True)
        daily = fetch_pageviews(title, s, e)
        out_brands.append({"brand": brand, "article": title, "daily": daily})
        time.sleep(0.7)  # Wikimedia is generous but be polite

    out = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "range": {"start": s, "end": e},
        "brands": out_brands,
    }
    target = DATA_DIR / "wikipedia_raw.json"
    target.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {target}")


if __name__ == "__main__":
    main()
