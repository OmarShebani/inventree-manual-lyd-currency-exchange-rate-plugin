"""Generate self-contained packages from shared sources. Run before building."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for variant in ("individual", "global"):
    package = ROOT / "plugins" / variant / f"inventree_lyd_{variant}"
    for name in ("engine.py", "runtime.py", "static/settings.js"):
        target = package / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "shared" / name, target)
