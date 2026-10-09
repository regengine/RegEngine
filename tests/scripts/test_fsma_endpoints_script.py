"""FSMA endpoint smoke script must assert exact statuses, require its key from the environment, and match transport to URL scheme."""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "test_fsma_endpoints.js"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_no_env_file_fallback_or_placeholder_key():
    src = _source()
    assert "loadApiKeyFromEnv" not in src
    assert "readFileSync" not in src
    assert "test-key" not in src
    assert "require('fs')" not in src
    assert 'require("fs")' not in src


def test_missing_key_exits_nonzero():
    env = {k: v for k, v in os.environ.items() if k != "REGENGINE_API_KEY"}
    env["GRAPH_SERVICE_URL"] = "http://127.0.0.1:9"
    proc = subprocess.run(
        ["node", str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert proc.returncode != 0
    assert "REGENGINE_API_KEY" in proc.stderr


def test_key_material_is_never_printed():
    assert "substring(0, 8)" not in _source()


def test_default_expectation_is_exact_success():
    src = _source()
    assert "[200, 401, 404, 422]" not in src
    assert "expectedStatus = 200" in src
    assert "|| res.ok" not in src


def test_transport_matches_url_scheme():
    src = _source()
    assert "url.protocol === 'https:'" in src
    assert "http.request(" not in src


def test_401_is_a_failure_and_transport_selects_by_scheme(tmp_path):
    """No network: the harness injects a fake request function into runTest."""
    harness = tmp_path / "fsma_harness.js"
    harness.write_text(
        textwrap.dedent(
            """\
            const assert = require('assert');
            const http = require('http');
            const https = require('https');

            async function main() {
                process.env.REGENGINE_API_KEY = 'harness-key';
                const suite = require(process.argv[2]);
                assert.strictEqual(
                    suite.transportFor(new URL('https://example.com/x')),
                    https,
                    'https URL must use the https transport',
                );
                assert.strictEqual(
                    suite.transportFor(new URL('http://example.com/x')),
                    http,
                    'http URL must use the http transport',
                );
                const fake401 = async () => ({ status: 401, data: null, ok: false });
                const fake200 = async () => ({ status: 200, data: null, ok: true });
                await suite.runTest('stub unauthorized', 'GET', '/health', undefined, fake401);
                assert.strictEqual(suite.results.failed, 1, 'a 401 must fail, not pass');
                assert.strictEqual(suite.results.passed, 0);
                await suite.runTest('stub ok', 'GET', '/health', undefined, fake200);
                assert.strictEqual(suite.results.passed, 1);
                await suite.runTest('stub expected 401', 'GET', '/health', [401], fake401);
                assert.strictEqual(suite.results.passed, 2, 'explicit per-endpoint status still works');
                console.log('harness ok');
            }

            main().catch((err) => {
                console.error(`harness failed: ${err.message}`);
                process.exit(1);
            });
            """
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["node", str(harness), str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "harness ok" in proc.stdout
