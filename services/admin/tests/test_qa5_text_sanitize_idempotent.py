"""QA5: response sanitizer must be idempotent over stored text.

The store path escapes entities (``&`` becomes ``&amp;``) and the read
path used to run the same escaping again, so every ``&``, quote, or
``<`` in a document doubled on each read (``&amp;amp;``) and the UI
showed literal entities. The response path now unescapes once before
re-sanitizing: stored rows read back stable, legacy raw rows are still
cleaned exactly once.
"""

from __future__ import annotations

import sys
from pathlib import Path

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

from app.text_sanitize import (  # noqa: E402
    sanitize_source_text_for_response,
    sanitize_source_text_for_store,
)


class TestResponseIdempotency:
    def test_stored_value_reads_back_stable(self):
        """store() then response() must equal store(): no double escape."""
        stored = sanitize_source_text_for_store("a < b & 'quoted'")
        assert sanitize_source_text_for_response(stored) == stored

    def test_ampersand_round_trip(self):
        stored = sanitize_source_text_for_store("Ben & Jerry's")
        assert stored == "Ben &amp; Jerry&#x27;s"
        assert sanitize_source_text_for_response(stored) == stored

    def test_plain_text_untouched(self):
        assert sanitize_source_text_for_response(sanitize_source_text_for_store("hello world")) == "hello world"

    def test_legacy_raw_row_still_cleaned_exactly_once(self):
        """Pre-sanitization rows (raw markup in the column) are still
        stripped and escaped, but entities they contain are not doubled."""
        assert sanitize_source_text_for_response("<script>alert(1)</script>benign") == "benign"
        assert sanitize_source_text_for_response("fish & chips") == "fish &amp; chips"
        assert "<script>" not in sanitize_source_text_for_response("<b>bold</b> & raw")

    def test_user_typed_entity_stays_single_escaped(self):
        """A user who literally typed ``&lt;`` sees ``&lt;``, not ``&amp;lt;``."""
        assert sanitize_source_text_for_response("a &lt; b") == "a &lt; b"
