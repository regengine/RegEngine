"""#2965 — the inbound schema loader must fail CLOSED, not open.

The production ``Dockerfile`` never copied ``data-schemas/`` into the runtime
image, so ``_load_inbound_schema()`` raised ``FileNotFoundError`` in every
container, the module-level loader swallowed it into
``_INBOUND_VALIDATOR = None``, and the consumer's ``if _INBOUND_VALIDATOR is
not None`` guard turned that miss into "validate nothing".

These tests reload ``schema_validation`` with the schema directory pointed at
an empty path — reproducing the container exactly, without needing to build the
image (which cannot be built in this environment) — and assert the resulting
validator REJECTS messages rather than passing them through.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

MODULE = "services.nlp.app.consumer.schema_validation"


def _reload_with_schema_dir(monkeypatch, schema_dir: Path):
    """Re-import schema_validation with ``data_schemas_dir()`` redirected."""
    import shared.paths as shared_paths

    monkeypatch.setattr(shared_paths, "data_schemas_dir", lambda: schema_dir)
    sys.modules.pop(MODULE, None)
    module = importlib.import_module(MODULE)
    return module


@pytest.fixture(autouse=True)
def _restore_module():
    """Leave the real module in sys.modules for every other test in the run."""
    yield
    sys.modules.pop(MODULE, None)
    importlib.import_module(MODULE)


class TestInboundValidatorFailsClosed:
    def test_missing_schema_dir_does_not_yield_a_permissive_none(self, monkeypatch, tmp_path):
        """The load failure must not degrade to ``None``.

        ``None`` is precisely what makes ``consumer/__init__.py`` skip
        validation entirely.
        """
        module = _reload_with_schema_dir(monkeypatch, tmp_path / "no-such-data-schemas")

        assert module._INBOUND_VALIDATOR is not None

    def test_missing_schema_rejects_an_otherwise_valid_event(self, monkeypatch, tmp_path):
        """A message that WOULD validate is still rejected when the schema is gone."""
        module = _reload_with_schema_dir(monkeypatch, tmp_path / "no-such-data-schemas")

        evt = {
            "document_id": "doc-123",
            "document_hash": "abc123",
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "normalized_s3_path": "s3://bucket/key.json",
        }
        errors = list(module._INBOUND_VALIDATOR.iter_errors(evt))

        assert errors, "missing inbound schema must reject, not pass through"
        assert "fail-closed" in errors[0].message

    def test_missing_schema_rejects_a_hostile_event(self, monkeypatch, tmp_path):
        module = _reload_with_schema_dir(monkeypatch, tmp_path / "no-such-data-schemas")

        errors = list(module._INBOUND_VALIDATOR.iter_errors({"unexpected": "payload"}))

        assert errors
        assert module._INBOUND_VALIDATOR.is_valid({"unexpected": "payload"}) is False

    def test_consumer_guard_semantics_reject_on_missing_schema(self, monkeypatch, tmp_path):
        """Replicate the exact guard at ``consumer/__init__.py:554-555``."""
        module = _reload_with_schema_dir(monkeypatch, tmp_path / "no-such-data-schemas")

        validator = module._INBOUND_VALIDATOR
        rejected = False
        if validator is not None:
            if list(validator.iter_errors({"document_id": "d"})):
                rejected = True

        assert rejected, (
            "consumer would have accepted an unvalidated message — this is the "
            "fail-open behaviour #2965 reports"
        )

    def test_load_raises_when_schema_absent(self, monkeypatch, tmp_path):
        module = _reload_with_schema_dir(monkeypatch, tmp_path / "no-such-data-schemas")

        with pytest.raises(FileNotFoundError):
            module._load_inbound_schema()


class TestInboundValidatorWithRealSchema:
    def test_real_schema_still_loads_on_a_source_checkout(self):
        """The fail-closed path must not fire when data-schemas/ IS present."""
        module = importlib.import_module(MODULE)

        assert not isinstance(
            module._INBOUND_VALIDATOR, module._UnavailableInboundValidator
        )
        evt = {
            "document_id": "doc-123",
            "document_hash": "abc123",
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "normalized_s3_path": "s3://bucket/key.json",
        }
        assert list(module._INBOUND_VALIDATOR.iter_errors(evt)) == []


class TestDockerfilePackagesSchemas:
    """#2965 acceptance criterion 1, checked statically.

    The image cannot be built in this environment, so assert the two lines that
    make ``/app/data-schemas/events/ingest.normalized.schema.json`` exist.
    """

    @property
    def dockerfile(self) -> str:
        root = Path(__file__).resolve().parents[3]
        return (root / "Dockerfile").read_text()

    def test_dockerfile_copies_data_schemas(self):
        assert "COPY data-schemas /app/data-schemas" in self.dockerfile

    def test_dockerfile_sets_project_root(self):
        """``shared/paths.py`` documents PROJECT_ROOT as set in Docker."""
        assert "ENV PROJECT_ROOT=/app" in self.dockerfile
