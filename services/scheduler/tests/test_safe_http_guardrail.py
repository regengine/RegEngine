"""Static guardrail: scheduler must not call ``httpx.get``/``.post`` directly.

RE-SCH-001: every outbound HTTP call site in the scheduler service (other
than the webhook delivery path, which has its own SSRF defenses) must route
through ``shared.safe_http`` so URLs are validated and connections are
pinned to a validated IP. A regression where someone reverts to the raw
``httpx.get(...)`` / ``httpx.post(...)`` shape would silently re-open the
SSRF / DNS-rebinding window.

This is the scheduler-side mirror of
``services/ingestion/tests/security/test_scrapers_ssrf.py::test_no_direct_httpx_get_in_state_adaptors``
landed in PR #2252.
"""

from __future__ import annotations

import pathlib
import re

# Patterns we forbid in scheduler app code:
#   httpx.get(...)         -> direct sync GET, bypasses safe_http
#   httpx.post(...)        -> direct sync POST, bypasses safe_http
#   httpx.AsyncClient(... ).get(  -> rare but possible bypass
# We allow ``httpx.Client(...)``/``httpx.AsyncClient(...)`` constructors,
# ``httpx.HTTPError``/``httpx.TimeoutException`` exception references, and
# ``httpx.Response``/``httpx.Request`` type imports — those are not call
# sites that perform a fetch.
_FORBIDDEN_PATTERNS = [
    re.compile(r"\bhttpx\.get\("),
    re.compile(r"\bhttpx\.post\("),
]

# Files that are allowed to contain direct httpx calls (none in scheduler
# today; the webhook notifier's session.post() is on a session object, not
# the httpx module). Keeping the allowlist explicit so a reviewer has to
# justify any addition.
_ALLOWLIST: set[str] = set()


def _scrubbed_lines(text: str) -> list[str]:
    """Strip line comments before scanning so commented-out examples pass."""
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        out.append(line)
    return out


def test_no_direct_httpx_get_or_post_in_scheduler_app():
    scheduler_root = pathlib.Path(__file__).resolve().parents[1]
    scan_roots = [scheduler_root / "app", scheduler_root / "main.py"]

    offenders: list[tuple[str, int, str]] = []
    for root in scan_roots:
        if root.is_file():
            files = [root]
        else:
            files = list(root.rglob("*.py"))
        for py in files:
            if py.name in _ALLOWLIST:
                continue
            text = py.read_text()
            scrubbed = "\n".join(_scrubbed_lines(text))
            for pat in _FORBIDDEN_PATTERNS:
                for match in pat.finditer(scrubbed):
                    # Find the original line number (in the un-scrubbed text)
                    # by counting newlines up to the match offset of the
                    # *first* occurrence of the matched substring. Good
                    # enough for the failure message.
                    lineno = scrubbed[: match.start()].count("\n") + 1
                    offenders.append((str(py.relative_to(scheduler_root)), lineno, match.group(0)))

    assert offenders == [], (
        "Direct httpx.get/post calls found — route via shared.safe_http "
        f"(safe_httpx_get_sync / safe_httpx_post_sync). Offenders:\n  "
        + "\n  ".join(f"{p}:{ln} -> {m}" for p, ln, m in offenders)
    )
