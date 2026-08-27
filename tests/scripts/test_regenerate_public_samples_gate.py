"""#2842 — the public-samples drift gate must not pass vacuously.

``scripts/regenerate_public_samples.py`` regenerates ``demo_exports/`` — the
public Proof Surface external parties verify FDA exports, EPCIS and Merkle
audit bundles against — and backend-ci fails the build if the regenerated
output differs from what is checked in.

The import-failure path used to ``return 0`` with the comment "CI's diff check
will still pass because we didn't write anything". Nothing regenerated, empty
diff, green check: the failure was indistinguishable from a pass, so any change
to the import chain of ``app.epcis_export`` / ``app.fda_export_service`` /
``shared.merkle_tree`` would have switched the gate off permanently and
silently.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "regenerate_public_samples.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("_tests_regen_public_samples", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script():
    module = _load_script_module()
    yield module
    sys.modules.pop("_tests_regen_public_samples", None)


class TestImportFailureIsRed:
    def test_main_exits_non_zero_when_helpers_cannot_be_imported(self, script, monkeypatch):
        """The core regression: 'could not import' must be a red check."""
        monkeypatch.setattr(script, "_try_import_production_helpers", lambda: None)

        assert script.main() != 0, (
            "import failure returned 0 — the drift gate passes having "
            "regenerated nothing (#2842)"
        )

    def test_main_writes_nothing_on_the_failure_path(self, script, monkeypatch, tmp_path):
        """Failing must not also corrupt the checked-in artifacts."""
        monkeypatch.setattr(script, "_try_import_production_helpers", lambda: None)
        export_dir = tmp_path / "demo_exports"
        monkeypatch.setattr(script, "EXPORT_DIR", export_dir)

        rc = script.main()

        assert rc != 0
        assert list(export_dir.iterdir()) == []

    def test_source_no_longer_claims_a_vacuous_pass(self):
        """The old behaviour was documented in a comment; it must be gone."""
        source = SCRIPT.read_text()

        assert "CI's diff check will still" not in source
        assert "exiting 0 without rewriting" not in source


class TestHappyPathStillReturnsZero:
    def test_main_succeeds_when_helpers_import(self, script, monkeypatch, tmp_path):
        """Guard against 'make it red' turning into 'always red'.

        Exercises the real helper imports and the real synthetic inputs, so it
        proves the gate can still pass on a healthy checkout. EXPORT_DIR is
        redirected into tmp_path: all three writers read that module global at
        call time (regenerate_public_samples.py:234, :290, :323), so the real
        checked-in demo_exports/ is never touched by the test suite. Writing to
        it would silently rewrite the public Proof Surface as a side effect of
        running tests.
        """
        if script._try_import_production_helpers() is None:
            pytest.skip("production helpers not importable in this environment")

        monkeypatch.setattr(script, "EXPORT_DIR", tmp_path / "demo_exports")

        assert script.main() == 0
        assert (tmp_path / "demo_exports" / "sample_fda_export.csv").exists()


class TestWorkflowInstallsTheLockfile:
    """#2842 second half: the job installed three hand-picked packages.

    With the vacuous pass removed, guessing the import closure would turn every
    transitive-dependency addition into a red build.
    """

    @property
    def job(self) -> str:
        content = (ROOT / ".github" / "workflows" / "backend-ci.yml").read_text()
        return content.split("regenerate-public-samples:", 1)[1].split("\n  # ", 1)[0]

    def test_job_installs_requirements_lock(self):
        assert "requirements.lock" in self.job

    def test_job_no_longer_installs_three_hand_picked_packages(self):
        assert "pip install pydantic fastapi sqlalchemy" not in self.job
