"""Per-process temp file isolation for scripts/smoke_test_ingest.sh.

The script used to store every response body in the fixed path
/tmp/smoke_ingest_body, so two runs at once overwrote and deleted each
other's bodies. It now creates a per-process file with mktemp and removes
it on exit. These tests fail on the fixed-path version and pass on the
mktemp version.
"""

import os
import subprocess
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
FIXED_BODY = "/tmp/smoke_ingest_body"


def test_body_path_is_per_process():
    text = (SCRIPTS / "smoke_test_ingest.sh").read_text()
    assert "mktemp" in text
    assert "-o /tmp/smoke_ingest_body" not in text
    assert "cat /tmp/smoke_ingest_body" not in text
    assert "rm -f /tmp/smoke_ingest_body" not in text


def _make_fake_curl_bin(tmp_path: Path):
    """Fake curl that logs its -o target, writes a body there, and stalls.

    The stall forces two concurrent script runs to overlap, so a shared
    fixed path would be observed twice while per-process files differ.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    body_log = tmp_path / "body.log"
    (bin_dir / "curl").write_text(
        "#!/usr/bin/env bash\n"
        "out=''\n"
        "prev=''\n"
        'for a in "$@"; do\n'
        '  if [[ "$prev" == "-o" ]]; then out="$a"; fi\n'
        '  prev="$a"\n'
        "done\n"
        'echo "BODY=$out" >> "$FAKE_BODY_LOG"\n'
        'printf "probe-body" > "$out"\n'
        "sleep 0.3\n"
        'printf "200"\n'
        "exit 0\n"
    )
    os.chmod(bin_dir / "curl", 0o755)
    return bin_dir, body_log


def _run_smoke(bin_dir: Path, body_log: Path):
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "REGENGINE_API_KEY": uuid4().hex,
        "REGENGINE_API_BASE": "http://localhost:8000",
        "FAKE_BODY_LOG": str(body_log),
    }
    return subprocess.Popen(
        ["bash", str(SCRIPTS / "smoke_test_ingest.sh")],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )


def test_concurrent_runs_use_distinct_body_files(tmp_path):
    bin_dir, body_log = _make_fake_curl_bin(tmp_path)
    first = _run_smoke(bin_dir, body_log)
    second = _run_smoke(bin_dir, body_log)
    out1, _ = first.communicate(timeout=60)
    out2, _ = second.communicate(timeout=60)
    # The script has a pre-existing unquoted-semicolon multipart bug that
    # aborts it with exit 1 after the first probes, so only require that the
    # localhost guard passed and probes ran (exit 2 means refused target).
    assert first.returncode != 2, out1
    assert second.returncode != 2, out2

    bodies = [
        line.split("BODY=", 1)[1].strip() for line in body_log.read_text().splitlines() if line.startswith("BODY=")
    ]
    assert len(bodies) >= 2, f"expected curl -o calls, got {bodies!r}"
    assert FIXED_BODY not in bodies, f"runs shared the fixed path: {bodies!r}"
    assert len(set(bodies)) >= 2, f"concurrent runs shared body files: {bodies!r}"
