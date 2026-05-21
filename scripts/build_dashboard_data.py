"""
Copies data/analyzed.json -> docs/data.json so GitHub Pages serves it.

IMPORTANT: if analyzed.json is missing (e.g. analyze.py crashed), we DO NOT
overwrite docs/data.json. Keeping the previous good dashboard data is always
better than clobbering it with the stale seed sample.

This used to silently revert the live dashboard to the May 2026 seed every
time a fetch failed -- that bug is fixed here: the seed is only ever used on a
brand-new repo that has no docs/data.json at all.
"""
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
src = ROOT / "data" / "analyzed.json"
dst = ROOT / "docs" / "data.json"
seed = ROOT / "data" / "sample_data.json"
dst.parent.mkdir(exist_ok=True)

if src.exists():
    shutil.copy2(src, dst)
    print(f"Copied {src} -> {dst}")
elif dst.exists():
    # Real data was not produced this run. Leave the existing dashboard data
    # exactly as it is -- never replace good data with the seed.
    print("WARN: analyzed.json missing - keeping existing docs/data.json untouched.")
    print("      (Run analyze.py to refresh. Dashboard still shows last good data.)")
    sys.exit(1)
elif seed.exists():
    # First-ever run on a fresh repo: nothing to preserve, so seed it.
    shutil.copy2(seed, dst)
    print("WARN: no analyzed.json and no docs/data.json - seeded from sample_data.json")
else:
    dst.write_text('{"error": "no data available", "keywords": []}', encoding="utf-8")
    print(f"WARN: no source data found - wrote stub to {dst}")
