"""Drift guard: launch_orchestrator runbooks must describe the real CLI (#2963).

`launch_orchestrator/design_partners/SANDBOX_PROVISIONING.md` shipped a
copy-pasteable command, ``python orchestrator.py --mode provision_sandbox
--partner-id "acme-corp"``, that argparse rejected on both counts — there is no
``provision_sandbox`` mode and no ``--partner-id`` argument — and promised a
``dp_sandbox_`` API-key prefix and partner-scoped sandbox namespace that the
code never produces.

These tests pin the runbooks to the code so the same drift cannot reappear:

1. ``test_documented_invocations_parse`` — every ``python orchestrator.py ...``
   command in ``launch_orchestrator/**/*.md`` is fed to the *live* parser that
   ``orchestrator.main()`` builds. Nothing here re-declares the arguments, so a
   mode or flag renamed in the code fails the docs immediately.
2. ``test_documented_key_prefix_matches_code`` / ``test_documented_sandbox_id_
   format_matches_code`` — the strings the runbooks quote must be the strings
   ``_provision_sandbox`` actually emits.

The parser is exercised through ``main()`` rather than a reconstruction of it,
because a reconstruction would silently stop matching the real CLI — which is
the exact failure mode being guarded against. ``LaunchOrchestrator`` is stubbed
so parsing happens for real but no orchestration runs.
"""

from __future__ import annotations

import importlib.util
import io
import contextlib
import re
import shlex
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_DIR = REPO_ROOT / "launch_orchestrator"
ORCHESTRATOR_PY = ORCHESTRATOR_DIR / "orchestrator.py"

pytestmark = pytest.mark.skipif(
    not ORCHESTRATOR_PY.exists(),
    reason="launch_orchestrator/orchestrator.py not present",
)

# Matches a documented invocation up to end-of-line or a closing backtick.
_INVOCATION = re.compile(r"python orchestrator\.py[^\n`]*")


class _ParsedOK(Exception):
    """Raised by the LaunchOrchestrator stub once argv has parsed cleanly."""


def _load_orchestrator():
    spec = importlib.util.spec_from_file_location("_orchestrator_under_test", ORCHESTRATOR_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _documented_invocations() -> list[tuple[str, int, str]]:
    """Return (relative_path, line_number, command) for every documented call."""
    found: list[tuple[str, int, str]] = []
    for md in sorted(ORCHESTRATOR_DIR.rglob("*.md")):
        for line_no, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            for raw in _INVOCATION.findall(line):
                found.append((str(md.relative_to(REPO_ROOT)), line_no, raw.strip().rstrip("`,.")))
    return found


def test_at_least_one_invocation_is_documented():
    """Guard the guard: an empty match set must not pass silently."""
    assert _documented_invocations(), (
        "No 'python orchestrator.py' invocations found under launch_orchestrator/**/*.md — "
        "the regex in this test has probably drifted from the docs."
    )


@pytest.mark.parametrize(
    ("doc", "line_no", "command"),
    _documented_invocations(),
    ids=lambda v: f"{v}" if isinstance(v, (str, int)) else "",
)
def test_documented_invocations_parse(doc: str, line_no: int, command: str, monkeypatch):
    """Every documented command must survive orchestrator.main()'s own parser."""
    module = _load_orchestrator()

    def _stub(*_args, **_kwargs):
        raise _ParsedOK

    # shlex gives ["python", "orchestrator.py", ...]; argparse reads argv[0] as
    # the program name, so hand it the script and only the real arguments.
    tokens = shlex.split(command)[2:]
    monkeypatch.setattr(module, "LaunchOrchestrator", _stub)
    monkeypatch.setattr(sys, "argv", ["orchestrator.py", *tokens])

    argv_tail = " ".join(tokens)
    try:
        # main() prints usage to stderr on failure; keep test output readable.
        with contextlib.redirect_stderr(io.StringIO()) as err, contextlib.redirect_stdout(io.StringIO()):
            module.main()
    except _ParsedOK:
        return  # argv parsed cleanly and orchestration was stubbed out
    except SystemExit as exc:
        if exc.code in (0, None):
            return  # e.g. --help, which exits 0 by design
        pytest.fail(
            f"{doc}:{line_no} documents a command argparse rejects "
            f"(exit {exc.code}): python {argv_tail}\n{err.getvalue().strip()}"
        )


def test_documented_key_prefix_matches_code():
    """The runbooks must not promise an API-key prefix the code never emits."""
    source = ORCHESTRATOR_PY.read_text(encoding="utf-8")
    match = re.search(r'api_key\s*=\s*"([a-z_]+)"\s*\+', source)
    assert match, "Could not locate the API-key prefix literal in _provision_sandbox"
    actual_prefix = match.group(1)

    for md in sorted(ORCHESTRATOR_DIR.rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        assert "dp_sandbox_" not in text, (
            f"{md.relative_to(REPO_ROOT)} documents the 'dp_sandbox_' API-key prefix, "
            f"but _provision_sandbox emits '{actual_prefix}' and registered keys use 'rge_'."
        )


def test_documented_sandbox_id_format_matches_code():
    """Sandbox ids are sequential, not partner-scoped; docs must not claim otherwise."""
    source = ORCHESTRATOR_PY.read_text(encoding="utf-8")
    assert 'f"dp-sandbox-{i + 1}"' in source, (
        "Sandbox id generation changed; update this guard and the runbooks together."
    )

    runbook = ORCHESTRATOR_DIR / "design_partners" / "SANDBOX_PROVISIONING.md"
    if runbook.exists():
        assert "dp-sandbox-{partner-id}" not in runbook.read_text(encoding="utf-8"), (
            "SANDBOX_PROVISIONING.md claims a partner-scoped sandbox namespace, but "
            "_provision_sandbox ignores partner identity and emits dp-sandbox-1..N."
        )
