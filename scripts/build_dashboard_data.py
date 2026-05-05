"""
Copies data/analyzed.json → docs/data.json so GitHub Pages serves it
without exposing the rest of /data.
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
src = ROOT / "data" / "analyzed.json"
dst = ROOT / "docs" / "data.json"
dst.parent.mkdir(exist_ok=True)
shutil.copy2(src, dst)
print(f"Copied {src} → {dst}")
