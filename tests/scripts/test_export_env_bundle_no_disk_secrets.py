"""Regression tests for scripts/export_env_bundle.py (#2938).

The defect: a script named `rotate_secrets_to_aws.py` neither rotated any
credential nor made any AWS call. Its `--output` flag wrote ADMIN_MASTER_KEY
and every production database / broker / object-store credential as plaintext
JSON, under the operator's default umask, to a path `.gitignore` did not
cover.

The fix is that nothing writes secrets to disk at all: `--output` is refused,
and the bundle can only go to stdout for piping into a secret manager. The
script was renamed to match what it actually does.

All credential values used below are obvious fakes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "export_env_bundle.py"

# Obvious placeholders - never real credentials.
FAKE_ENV = {
    "POSTGRES_PASSWORD": "fake-pg-pw-not-a-real-secret",
    "NEO4J_PASSWORD": "fake-neo4j-pw-not-a-real-secret",
    "ADMIN_MASTER_KEY": "fake-admin-key-not-a-real-secret",  # retired; set to prove it is ignored
    "OBJECT_STORAGE_ACCESS_KEY_ID": "fake-akid-not-a-real-secret",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY": "fake-sak-not-a-real-secret",
}


def _run(args, cwd: Path, extra_env=None):
    env = dict(os.environ)
    env.update(FAKE_ENV)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_script_is_named_for_what_it_does():
    """The misleading `rotate_secrets_to_aws.py` name is gone."""
    assert SCRIPT.exists(), "expected scripts/export_env_bundle.py"
    assert not (REPO_ROOT / "scripts" / "rotate_secrets_to_aws.py").exists(), (
        "a script named rotate_secrets_to_aws.py must not exist: it neither rotates nor contacts AWS"
    )


def test_script_makes_no_aws_call_and_says_so():
    """It must not pretend to rotate; the disclaimer is load-bearing."""
    source = SCRIPT.read_text()
    assert "boto3" not in source and "botocore" not in source
    assert "does not rotate" in source.lower()
    assert "does not contact aws" in source.lower()


def test_output_flag_is_refused_and_writes_nothing(tmp_path):
    """`--output` must not create a plaintext credential bundle.

    Fails against the previous script, which happily wrote every production
    credential as plaintext JSON to this path.
    """
    target = tmp_path / "secrets.json"
    proc = _run(
        ["--environment", "production", "--env-file", str(tmp_path / "absent.env"), "--output", str(target)],
        cwd=tmp_path,
    )

    assert proc.returncode != 0, "--output was accepted"
    assert not target.exists(), "a plaintext secrets bundle was written to disk"
    combined = proc.stdout + proc.stderr
    for value in FAKE_ENV.values():
        assert value not in combined, "refusal path leaked a credential value"


def test_validation_run_writes_no_file_and_prints_no_values(tmp_path):
    """The default run reports key names only and touches no file."""
    proc = _run(
        ["--environment", "production", "--env-file", str(tmp_path / "absent.env")],
        cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr

    assert list(tmp_path.iterdir()) == [], f"script created files: {list(tmp_path.iterdir())}"

    combined = proc.stdout + proc.stderr
    assert "POSTGRES_PASSWORD" in combined, "should confirm the key name was validated"
    assert "ADMIN_MASTER_KEY" not in combined, "the retired admin key is still validated"
    for value in FAKE_ENV.values():
        assert value not in combined, "a credential value was printed"


def test_emit_bundle_goes_to_stdout_only(tmp_path):
    """`--emit-bundle` yields pipeable JSON on stdout and still writes no file."""
    proc = _run(
        ["--environment", "production", "--env-file", str(tmp_path / "absent.env"), "--emit-bundle"],
        cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    assert list(tmp_path.iterdir()) == [], "emitting a bundle must not create a file"

    bundle = json.loads(proc.stdout)
    assert bundle["POSTGRES_PASSWORD"] == FAKE_ENV["POSTGRES_PASSWORD"]
    # The app no longer reads ADMIN_MASTER_KEY; the bundle must not push it
    # to the platform even when it is still set locally.
    assert "ADMIN_MASTER_KEY" not in bundle
    assert bundle["ENVIRONMENT"] == "production"
    # Diagnostics must stay off stdout so the pipe carries only JSON.
    assert "RegEngine" not in proc.stdout


def test_missing_required_secret_fails_without_emitting(tmp_path):
    """A missing credential fails the run and emits nothing."""
    proc = _run(
        ["--environment", "production", "--env-file", str(tmp_path / "absent.env"), "--emit-bundle"],
        cwd=tmp_path,
        extra_env={"POSTGRES_PASSWORD": ""},
    )
    assert proc.returncode == 1
    assert proc.stdout.strip() == "", "emitted a bundle despite failing validation"
    # Error path prints only the absent name(s) as literals (not from
    # payload / REQUIRED_SECRETS iteration), so CodeQL cannot taint them.
    assert "POSTGRES_PASSWORD" in proc.stderr
    assert "NEO4J_PASSWORD" not in proc.stderr  # still present in FAKE_ENV
    assert "required secret(s) missing" in proc.stderr
    for value in FAKE_ENV.values():
        assert value not in proc.stderr, "a credential value was printed on the error path"


@pytest.mark.parametrize("candidate", ["secrets.json", "prod.secrets.json"])
def test_plaintext_bundle_filenames_are_gitignored(candidate):
    """Belt-and-braces: a hand-made bundle cannot be committed by accident."""
    proc = subprocess.run(
        ["git", "check-ignore", "-q", candidate],
        cwd=REPO_ROOT,
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"{candidate} is not covered by .gitignore"


def test_status_names_come_from_constants_not_payload():
    """Code scanning alerts 19 / 20 / 82: status names stay in sync.

    Status lines embed env-var names as literals (not by iterating the
    credential payload or REQUIRED_SECRETS/PAYLOAD_KEYS into print). Keep
    PAYLOAD_KEYS identical to build_secret_payload keys and REQUIRED_SECRETS
    a subset, so the literal lists and validation stay aligned.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("export_env_bundle", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert tuple(module.build_secret_payload("dev").keys()) == module.PAYLOAD_KEYS
    assert set(module.REQUIRED_SECRETS) <= set(module.PAYLOAD_KEYS)
