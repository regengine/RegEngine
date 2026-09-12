"""Unit tests for ``shared.agent_org.slugs.slugify``.

Pure function, no mocking needed: pins the regex/lower/strip/hyphen-collapse
semantics inherited from ``services/admin/app/tenant_slug_helpers.py`` plus
the one behavior change this extraction makes explicit — a caller-supplied
``fallback`` instead of a hardcoded ``"tenant"``.
"""

from __future__ import annotations

import pytest
from shared.agent_org.slugs import slugify


class TestSlugify:
    def test_simple_name_lowercased(self):
        assert slugify("Outreach", fallback="x") == "outreach"

    def test_spaces_collapse_to_single_hyphen(self):
        assert slugify("Outreach Pod One", fallback="x") == "outreach-pod-one"

    def test_multiple_non_alnum_runs_collapse_to_one_hyphen(self):
        assert slugify("Outreach!!  --  Pod", fallback="x") == "outreach-pod"

    def test_leading_and_trailing_non_alnum_stripped(self):
        assert slugify("  --Outreach Pod--  ", fallback="x") == "outreach-pod"

    def test_digits_are_preserved(self):
        assert slugify("Pod 42", fallback="x") == "pod-42"

    @pytest.mark.parametrize("bad_input", ["", "   ", "!!!", "---", None])
    def test_empty_or_all_non_alnum_input_uses_caller_fallback(self, bad_input):
        assert slugify(bad_input, fallback="my-fallback") == "my-fallback"

    def test_fallback_is_caller_supplied_not_hardcoded(self):
        # The extraction's one behavior change vs. the original
        # admin-only helper: the empty-input default is not fixed to
        # "tenant" — every caller must say what it wants instead.
        assert slugify("", fallback="agent") == "agent"
        assert slugify("", fallback="tenant") == "tenant"

    def test_unicode_letters_are_stripped_as_non_alnum(self):
        # The regex is [^a-z0-9]+ — non-ASCII letters are not preserved.
        assert slugify("Café Pod", fallback="x") == "caf-pod"
