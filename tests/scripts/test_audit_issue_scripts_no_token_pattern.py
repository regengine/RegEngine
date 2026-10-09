"""Audit-issue helper scripts must not show a raw token pattern in usage text.

`ghp_xxx` looks like the prefix of a real GitHub personal access token and
trains copy-paste of real tokens into shell history. Usage lines must use a
redacted placeholder instead.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = [
    REPO_ROOT / "scripts" / "audit-issues.py",
    REPO_ROOT / "scripts" / "audit-issues-pass2.py",
]

TOKENLIKE = re.compile(r"gh[pousr]_|github_pat_")


def test_no_raw_token_pattern_in_usage_text():
    for script in SCRIPTS:
        source = script.read_text(encoding="utf-8")
        assert not TOKENLIKE.search(source), f"{script.name} shows a raw token pattern"


def test_usage_text_uses_redacted_placeholder():
    for script in SCRIPTS:
        source = script.read_text(encoding="utf-8")
        assert "GITHUB_TOKEN=<redacted>" in source, f"{script.name} should show a redacted placeholder"
