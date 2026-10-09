"""Regression tests for the production overlay image pins.

The defect: the comment above the ``images`` list in
infra/k8s/overlays/production/kustomization.yaml claimed CI/CD sets the
image tag, but no workflow edits these tags (infra-k8s-ci.yml only renders
the overlay), so every entry pinned v1.1.0 and deploys kept shipping that
stale tag. These tests pin the corrected comment and the explicit tags.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
OVERLAY_PATH = REPO_ROOT / "infra" / "k8s" / "overlays" / "production" / "kustomization.yaml"

EXPECTED_SERVICES = {
    "regengine/compliance-service",
    "regengine/admin-service",
    "regengine/ingestion-service",
    "regengine/scheduler",
    "regengine/graph-service",
    "regengine/nlp-service",
}


def _overlay():
    with OVERLAY_PATH.open() as handle:
        return yaml.safe_load(handle)


def test_comment_does_not_claim_ci_sets_the_tag():
    """Fails on the old comment, which said IMAGE_TAG is set by CI/CD."""
    text = OVERLAY_PATH.read_text()
    assert "is set by CI" not in text, "overlay comment claims CI sets the image tag, but no workflow edits it"


def test_every_service_has_an_explicit_pinned_tag():
    """Each image entry must pin a concrete tag, never a placeholder."""
    images = _overlay().get("images", [])
    by_name = {entry.get("name"): entry for entry in images}
    missing = EXPECTED_SERVICES - set(by_name)
    assert not missing, f"overlay images list is missing services: {sorted(missing)}"
    for name in sorted(EXPECTED_SERVICES):
        entry = by_name[name]
        assert entry.get("newName"), f"{name} has no newName"
        tag = entry.get("newTag")
        assert tag, f"{name} has no pinned newTag"
        assert "$(" not in str(tag), f"{name} newTag is a placeholder, not a pin: {tag}"
        assert str(tag).lower() != "latest", f"{name} floats on latest, pin a release tag"
