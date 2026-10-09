"""Per-request timeouts for the JS network probes.

Audit finding: scripts/e2e_tests.js and scripts/check_public_api_surface.mjs
issued fetch() calls with no timeout, so one hung endpoint stalls the suite
and CI indefinitely. Every network call in those scripts must carry a
per-request timeout.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_E2E = _REPO_ROOT / "scripts" / "e2e_tests.js"
_PROBE = _REPO_ROOT / "scripts" / "check_public_api_surface.mjs"

# A bare fetch( token that is not part of a longer identifier such as
# fetchWithTimeout(. The helper's own fetch carries its signal on the same
# line, so the signal check below still admits it.
_BARE_FETCH = re.compile(r"(?<![A-Za-z0-9_$])fetch\s*\(")


def _assert_every_fetch_has_a_timeout(path: Path) -> None:
    source = path.read_text()
    assert "AbortSignal.timeout" in source, (
        f"{path.name} issues network calls with no timeout: no AbortSignal.timeout found"
    )
    bare = [line.strip() for line in source.splitlines() if _BARE_FETCH.search(line)]
    assert bare, f"{path.name} has no fetch calls at all, nothing is guarded"
    without_signal = [line for line in bare if "signal" not in line]
    assert without_signal == [], f"{path.name} has fetch calls with no timeout signal: {without_signal}"


def test_e2e_tests_every_fetch_has_a_timeout() -> None:
    _assert_every_fetch_has_a_timeout(_E2E)


def test_public_api_surface_probe_every_fetch_has_a_timeout() -> None:
    _assert_every_fetch_has_a_timeout(_PROBE)


@pytest.mark.parametrize("script", [_E2E, _PROBE], ids=["e2e_tests.js", "check_public_api_surface.mjs"])
def test_script_still_parses(script: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    result = subprocess.run([node, "--check", str(script)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_abort_signal_timeout_fires_on_this_node() -> None:
    """The timeout mechanism used by the fix must work on this Node runtime.

    Confirms AbortSignal.timeout actually aborts after its deadline. This
    needs no sockets: the sandbox here forbids listening ports, so a
    hung-server round trip cannot run in this environment.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    probe = (
        "const controller = new AbortController();"
        "const timeout = AbortSignal.timeout(50);"
        "timeout.addEventListener('abort', () => {"
        "  console.log('aborted as expected: ' + timeout.reason.name);"
        "  controller.abort();"
        "});"
        "setTimeout(() => {"
        "  if (!timeout.aborted) {"
        "    console.error('signal never aborted');"
        "    process.exitCode = 1;"
        "  }"
        "  controller.abort();"
        "}, 5000);"
    )
    result = subprocess.run([node, "-e", probe], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "aborted as expected" in result.stdout
