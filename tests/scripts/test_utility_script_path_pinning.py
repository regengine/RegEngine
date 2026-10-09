"""Import-hijacking guard for scripts/utilities demo helpers.

Audit finding: scripts/utilities/demo_retailer_intelligence.py appended the
caller's working directory to sys.path and printed environment detail (cwd,
directory listing, sys.path); scripts/utilities/verify_phi.py did the same
path append. Running either script from an untrusted directory let files
planted there shadow the real imports. Both scripts must derive their search
paths from their own location and must not print environment detail.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "scripts" / "utilities" / "demo_retailer_intelligence.py"
VERIFY_PHI = ROOT / "scripts" / "utilities" / "verify_phi.py"


def test_demo_script_has_no_working_directory_path_setup():
    source = DEMO.read_text(encoding="utf-8")
    assert "getcwd" not in source
    assert "listdir" not in source


def test_demo_script_has_no_environment_debug_prints():
    source = DEMO.read_text(encoding="utf-8")
    assert "DEBUG:" not in source
    assert "PRE-PATH" not in source


def test_demo_script_pins_paths_to_its_own_location():
    source = DEMO.read_text(encoding="utf-8")
    assert "__file__" in source


def test_verify_phi_has_no_working_directory_path_setup():
    source = VERIFY_PHI.read_text(encoding="utf-8")
    assert "getcwd" not in source
    assert "__file__" in source


def test_demo_script_ignores_hostile_working_directory(tmp_path):
    """A planted ``app`` package in the cwd must not be imported.

    The hostile package touches a marker file on import. The demo must exit
    cleanly using the repo's own service code, leaving no marker behind.
    """
    hostile = tmp_path / "hostile"
    app_pkg = hostile / "app"
    app_pkg.mkdir(parents=True)
    marker = hostile / "hijacked.marker"
    (app_pkg / "__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
        encoding="utf-8",
    )
    (app_pkg / "classification.py").write_text(
        'class SignalClassifier:\n    def classify_signal(self, text):\n        return ("FOOD_SAFETY", "HIGH", 0.99)\n',
        encoding="utf-8",
    )
    (app_pkg / "extractor.py").write_text(
        "def extract_entities(text):\n    return []\n",
        encoding="utf-8",
    )
    (app_pkg / "resolution.py").write_text(
        "class EntityResolver:\n    def resolve_organization(self, name):\n        return None\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(DEMO)],
        cwd=str(hostile),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "STATUS: DEMO COMPLETE" in result.stdout
    assert not marker.exists()
