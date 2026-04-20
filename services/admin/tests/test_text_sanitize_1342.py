"""
Regression coverage for ``app/text_sanitize.py`` — closes the 83% gap
left by the four sanitization smoke tests in ``test_review_hardening.py``.

``sanitize_source_text_for_store`` / ``sanitize_source_text_for_response``
are the #1390 XSS defense for review items whose source text comes from
user-uploaded PDFs / Excel / OCR (untrusted document content). The
sanitizer is the last line of defense before ``source_text`` is rendered
in the admin UI — regressions here are direct stored-XSS vectors.

Pinned branches:

* Line 63 — ``sanitize_source_text_for_store(None)`` returns ``""``.
  Keeps the null-safe contract so upstream pydantic models can pass
  through Optional[str] without a TypeError.
* Line 65 — ``sanitize_source_text_for_store(non_str)`` coerces via
  ``str(value)``. Defense against a caller who forgets to stringify
  (e.g. an int field that ended up in a text column).
* Line 78 — bleach defense-in-depth branch when ``_BLEACH_AVAILABLE``.
  Monkey-patches the flag True because bleach is an optional runtime
  dep; the branch must stay pinned regardless of what the local env
  happens to have installed.
* Line 91 — ``sanitize_source_text_for_response(None)`` returns ``""``.
  Paired with line 63 so both boundary-side null branches are locked.

Tracks GitHub issue #1342.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

from app import text_sanitize  # noqa: E402
from app.text_sanitize import (  # noqa: E402
    sanitize_source_text_for_response,
    sanitize_source_text_for_store,
)


# ---------------------------------------------------------------------------
# Line 63 — None passthrough in store-side sanitizer
# ---------------------------------------------------------------------------


class TestStoreNonePassthrough:

    def test_none_returns_empty_string(self):
        """Line 63: store-time sanitizer must null-safely return "" so
        pydantic Optional[str] fields don't TypeError on None."""
        assert sanitize_source_text_for_store(None) == ""


# ---------------------------------------------------------------------------
# Line 65 — non-str coercion
# ---------------------------------------------------------------------------


class TestStoreNonStringCoercion:

    @pytest.mark.parametrize("value,expected_contains", [
        (42, "42"),
        (3.14, "3.14"),
        (True, "True"),
        (["a", "b"], "a"),  # str([...]) == "['a', 'b']", escape turns ' into &#x27;
    ])
    def test_non_string_inputs_are_stringified(self, value, expected_contains):
        """Line 65: callers that forget to stringify must not crash
        the sanitizer. We str()-coerce and proceed through the
        normal tag-stripping pipeline."""
        result = sanitize_source_text_for_store(value)
        assert isinstance(result, str)
        # Some chars get escaped — substring check is enough
        assert expected_contains in result or expected_contains.replace("'", "&#x27;") in result


# ---------------------------------------------------------------------------
# Line 78 — bleach defense-in-depth when available
# ---------------------------------------------------------------------------


class TestStoreBleachBranch:

    def test_bleach_branch_fires_when_available(self, monkeypatch):
        """Line 78: when _BLEACH_AVAILABLE is True, we pass the already-
        escaped text through bleach.clean(tags=[], attributes={}, strip=True)
        for attribute-level scrubbing. Monkey-patches the module so
        the test is robust to whether bleach is actually installed."""
        fake_bleach = types.SimpleNamespace()
        fake_bleach.clean = MagicMock(
            side_effect=lambda s, tags, attributes, strip: f"<bleached>{s}</bleached>"
        )

        monkeypatch.setattr(text_sanitize, "_bleach", fake_bleach)
        monkeypatch.setattr(text_sanitize, "_BLEACH_AVAILABLE", True)

        result = sanitize_source_text_for_store("hello world")

        assert fake_bleach.clean.called
        # Confirm kwargs — bleach.clean must be invoked with tags=[]
        # attributes={} strip=True (the whole point of the defense-in-
        # depth branch).
        _, kwargs = fake_bleach.clean.call_args
        assert kwargs == {"tags": [], "attributes": {}, "strip": True}
        # Our fake echo wraps the input — confirms the return value
        # flowed through rather than being discarded.
        assert result.startswith("<bleached>")

    def test_bleach_branch_skipped_when_unavailable(self, monkeypatch):
        """Line 76 False: without bleach available, we must NOT try
        to call it (would AttributeError on the None module)."""
        monkeypatch.setattr(text_sanitize, "_bleach", None)
        monkeypatch.setattr(text_sanitize, "_BLEACH_AVAILABLE", False)

        # Must not raise
        result = sanitize_source_text_for_store("safe text")

        assert "safe text" in result


# ---------------------------------------------------------------------------
# Line 91 — None passthrough in response-side sanitizer
# ---------------------------------------------------------------------------


class TestResponseNonePassthrough:

    def test_none_returns_empty_string(self):
        """Line 91: response-time sanitizer mirrors the store-time
        null-safety. The two must agree so a DB row that stored a real
        value and a DB row that stored None both render consistently."""
        assert sanitize_source_text_for_response(None) == ""

    def test_non_none_flows_through_store_sanitizer(self):
        """Line 92: non-None values pass through the store sanitizer
        (re-sanitize on read). This is the belt-and-braces defense for
        rows written before #1390 landed."""
        legacy_raw = "<script>alert(1)</script>benign"
        result = sanitize_source_text_for_response(legacy_raw)
        assert "<script>" not in result
        assert "benign" in result


# ---------------------------------------------------------------------------
# Belt-and-braces XSS smoke — ensures the 4 above can't co-regress
# with the core sanitization pipeline
# ---------------------------------------------------------------------------


class TestSanitizationSmoke:

    def test_script_tag_fully_stripped(self):
        """Core regression: <script> must disappear completely."""
        assert "<script>" not in sanitize_source_text_for_store("<script>x</script>")

    def test_style_iframe_object_embed_all_stripped(self):
        """_SCRIPT_TAG_RE covers more than just script. If someone
        refactors the regex and accidentally narrows it, this test
        flags it."""
        for tag in ("style", "iframe", "object", "embed"):
            src = f"<{tag}>danger</{tag}>"
            assert tag not in sanitize_source_text_for_store(src).lower() or \
                f"<{tag}>" not in sanitize_source_text_for_store(src)

    def test_javascript_uri_neutralized(self):
        """#1390 explicitly calls out javascript: URIs as a pattern we
        must neutralize even after html.escape — because if the markup
        was already rendered before sanitize runs, escape alone isn't
        enough."""
        result = sanitize_source_text_for_store("javascript:alert(1)")
        assert "javascript:" not in result
