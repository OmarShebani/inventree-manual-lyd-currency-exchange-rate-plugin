from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_shared_sources_match_both_standalone_packages():
    for variant in ("individual", "global"):
        folder = ROOT / "plugins" / variant
        package = folder / f"inventree_lyd_{variant}"
        for filename in ("engine.py", "runtime.py", "static/settings.js"):
            assert (ROOT / "shared" / filename).read_bytes() == (package / filename).read_bytes()
        project = tomllib.loads((folder / "pyproject.toml").read_text())["project"]
        assert len(project["entry-points"]["inventree_plugins"]) == 1
        assert not project.get("dependencies")
