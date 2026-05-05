"""
fetch_gdelt.py
--------------
GDELT 2.0 doc API — global news mention volume per brand, monthly buckets.
Fully open, no auth.

Endpoint:
  https://api.gdeltproject.org/api/v2/doc/doc?
    query=<term>&mode=TimelineVolInfo&timespan=12m&format=json

GDELT returns global English-language news article volume mentioning the term,
expressed as % of all articles in each time bucket.

Output: data/gdelt_raw.json
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

UA = "oruun-market-radar/0.2"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA})

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def load_config() -> dict:
    with open(ROOT / "keywords.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_volume(term: str, timespan: str = "12m") -> list[dict]:
    """Returns time-bucketed news mention volume for `term`."""
    # Quote multi-word brand names. GDELT understands phrase queries.
    if " " in term:
        q = f'"{term}"'
    else:
        q = term
    params = {
        "query": q,
        "mode": "TimelineVolInfo",
        "timespan": timespan,
        "format": "json",
    }
    try:
        r = SESSION.get(GDELT_URL, params=params, timeout=20)
        if r.status_code != 200 or not r.text.strip():
            return []
        # GDELT sometimes returns HTML on rate-limit; guard parse
        try:
            j = r.json()
        except Exception:
            return []
        timeline = j.get("timeline") or []
        if not timeline:
            return []
        rows = timeline[0].get("data") or []
        out = []
        for d in rows:
            ts = d.get("date", "")
            # GDELT date format: "20250501T000000Z"
            iso = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}" if len(ts) >= 8 else ts
            out.append({"date": iso, "value": float(d.get("value", 0))})
        return out
    except Exception as e:
        print(f"  GDELT failed for '{term}': {e}", flush=True)
        return []


def main() -> None:
    cfg = load_config()
    # Track BOTH brands and use-case keywords in news.
    targets: list[tuple[str, str]] = []
    for b in cfg.get("brands", []):
        targets.append((b, "brand"))
    # News volume on category/persona keywords reveals media moments
    # (e.g. "trail running" spikes after a UTMB feature).
    for cat in ("product_category", "use_case_persona"):
        for term in cfg.get("categories", {}).get(cat, [])[:8]:  # cap at 8 to keep run fast
            targets.append((term, cat))

    out_rows: list[dict] = []
    for term, kind in targets:
        print(f"[gdelt] {kind:<20s} {term}", flush=True)
        timeline = fetch_volume(term, "12m")
        out_rows.append({"term": term, "kind": kind, "timeline": timeline})
        time.sleep(0.8)

    out = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "rows": out_rows,
    }
    target = DATA_DIR / "gdelt_raw.json"
    target.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {target}  ({len(out_rows)} terms)")


if __name__ == "__main__":
    main()
