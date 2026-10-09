"""Tests for scripts/verify_live_freshness.py.

The script used to append a junk timestamp comment to the fetched content
just to force a hash change, and fetched with a browser user agent. These
tests pin both holes shut: ingest must send the fetched bytes unmodified
(the unique per-run source_url is the new-version signal), and the fetch
must identify the bot honestly.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "verify_live_freshness.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("_verify_live_freshness", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = _load_script()


class _FakeResponse:
    def __init__(self, status_code=200, text="body"):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        pass


def test_ingest_sends_content_unmodified_with_unique_url():
    """The fetched bytes must reach ingest unchanged; the URL carries novelty."""
    content = "<html>live FDA content</html>"
    run_id = "run-123"
    captured = {}

    def fake_post(url, json=None, headers=None):
        captured["payload"] = json
        return _FakeResponse(200)

    with patch.object(mod.requests, "post", fake_post):
        assert mod.ingest_live_content(content, run_id) is True

    payload = captured["payload"]
    assert payload["text"] == content, (
        "ingest payload text differs from fetched content, the junk-comment append is back"
    )
    assert "Verified at" not in payload["text"]
    assert payload["source_url"] == f"{mod.LIVE_FDA_URL}?run={run_id}"


def test_fetch_uses_honest_bot_user_agent():
    """The fetch must not masquerade as a browser."""
    captured = {}

    def fake_get(url, headers=None):
        captured["headers"] = headers or {}
        return _FakeResponse(200, text="<html>ok</html>")

    with patch.object(mod.requests, "get", fake_get):
        assert mod.fetch_live_content() == "<html>ok</html>"

    ua = captured["headers"].get("User-Agent", "")
    assert "Mozilla" not in ua and "Chrome" not in ua and "Safari" not in ua, (
        f"fetch still mislabels itself with a browser user agent: {ua!r}"
    )
    assert "RegEngine" in ua or "regengine" in ua.lower(), f"user agent does not identify the bot honestly: {ua!r}"


def test_source_no_longer_appends_junk_comment():
    """Static guard: the timestamp-comment trick must stay out of the script."""
    source = _SCRIPT.read_text()
    assert "Verified at {time.time()}" not in source, (
        "the junk timestamp comment append is still in verify_live_freshness.py"
    )
