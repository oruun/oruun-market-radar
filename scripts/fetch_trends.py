"""
fetch_trends.py
---------------
Pulls Google Trends data for every keyword in keywords.yaml.

For each term we collect:
  • interest_over_time across each geo (the time-series chart)
  • related_queries  — what people search ALONGSIDE this term
                      ("top" = all-time co-occurring, "rising" = fastest growing)
  • The "rising" set is the single best free signal of where buyer interest
    is moving. It's used downstream by the intent classifier.

Output: data/trends_raw.json
"""
from __future__ import annotations
import json
import time
import random
from datetime import datetime, timezone
from pathlib import Path

import yaml
from pytrends.request import TrendReq

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

MAX_RETRIES = 4
BASE_SLEEP = 8


def load_config() -> dict:
    with open(ROOT / "keywords.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def all_keywords(cfg: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for category, terms in cfg["categories"].items():
        for t in terms:
            out.append((t, category))
    for brand in cfg.get("brands", []):
        out.append((brand, "brand"))
    return out


def fetch_series(pytrends: TrendReq, term: str, geo: str, timeframe: str) -> list[dict]:
    for attempt in range(MAX_RETRIES):
        try:
            pytrends.build_payload([term], timeframe=timeframe, geo=geo)
            df = pytrends.interest_over_time()
            if df is None or df.empty or term not in df.columns:
                return []
            return [
                {"date": idx.strftime("%Y-%m-%d"), "value": int(row[term])}
                for idx, row in df.iterrows()
            ]
        except Exception as e:
            sleep = BASE_SLEEP * (attempt + 1) + random.uniform(0, 5)
            print(f"  retry {attempt+1}/{MAX_RETRIES} '{term}' ({geo}): {e} → {sleep:.1f}s", flush=True)
            time.sleep(sleep)
    return []


def fetch_related(pytrends: TrendReq, term: str, geo: str, timeframe: str) -> dict:
    """
    Returns: {"top": [{"query": str, "value": int}, ...],
              "rising": [{"query": str, "value": int}, ...]}
    """
    for attempt in range(MAX_RETRIES):
        try:
            pytrends.build_payload([term], timeframe=timeframe, geo=geo)
            data = pytrends.related_queries() or {}
            sub = data.get(term, {}) or {}
            out: dict = {"top": [], "rising": []}
            for key in ("top", "rising"):
                df = sub.get(key)
                if df is not None and len(df):
                    for _, row in df.head(25).iterrows():
                        try:
                            v = int(row["value"]) if str(row["value"]).strip().isdigit() else int(float(row["value"]))
                        except Exception:
                            v = 0
                        out[key].append({"query": str(row["query"]), "value": v})
            return out
        except Exception as e:
            sleep = BASE_SLEEP * (attempt + 1) + random.uniform(0, 5)
            print(f"  related retry {attempt+1}/{MAX_RETRIES} '{term}': {e} → {sleep:.1f}s", flush=True)
            time.sleep(sleep)
    return {"top": [], "rising": []}


def main() -> None:
    cfg = load_config()
    timeframe = cfg.get("timeframe", "today 12-m")
    geos = cfg.get("geos", ["US"])
    primary_geo = cfg.get("related_queries_geo", "US")  # related_queries pulled for one geo only

    pytrends = TrendReq(hl="en-US", tz=0, retries=2, backoff_factor=0.5)
    series_out = []

    for term, category in all_keywords(cfg):
        print(f"[trends] {category:<20s} {term}", flush=True)
        geo_series: dict[str, list[dict]] = {}
        for geo in geos:
            label = geo if geo else "WORLD"
            geo_series[label] = fetch_series(pytrends, term, geo, timeframe)
            time.sleep(1.5)

        related = fetch_related(pytrends, term, primary_geo, timeframe)
        time.sleep(2)

        series_out.append({
            "term": term,
            "category": category,
            "geo_series": geo_series,
            "related": related,  # {"top": [...], "rising": [...]}
        })

    out = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "timeframe": timeframe,
        "primary_geo": primary_geo,
        "series": series_out,
    }
    target = DATA_DIR / "trends_raw.json"
    target.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {target}  ({len(series_out)} terms)")


if __name__ == "__main__":
    main()
