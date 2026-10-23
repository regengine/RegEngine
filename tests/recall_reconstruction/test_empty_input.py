"""A recall reconstruction requires source evidence before it can run."""

import pytest

from shared.recall_reconstruction import load_fixture


def test_recall_reconstruction_rejects_empty_input(tmp_path):
    with pytest.raises(FileNotFoundError, match="sync_manifest.json"):
        load_fixture(tmp_path, "complete")
