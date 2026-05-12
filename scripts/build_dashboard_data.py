"""
Copies data/analyzed.json -> docs/data.json so GitHub Pages serves it.

Defensive: if analyzed.json is missing (e.g. analyze.py crashed),
fall back to the seed sample so the dashboard never breaks.
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
src = ROOT / "data" / "analyzed.json"
seed = ROOT / "data" / "sample_data.json"
dst = ROOT / "docs" / "data.json"
dst.parent.mkdir(exist_ok=True)

if src.exists():
    shutil.copy2(src, dst)
    print(f"Copied {src} -> {dst}")
elif seed.exists():
    shutil.copy2(seed, dst)
    print(f"WARN: analyzed.json missing - fell back to seed sample_data.json")
else:
    dst.write_text('{"error": "no data available", "keywords": [], "cross_source_validation": []}', encoding="utf-8")
    print(f"WARN: no source data found - wrote stub to {dst}")
