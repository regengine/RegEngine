"""seed_demo.js must not report success when tenant creation fails.

Regression test for the audit finding: tenant-creation failures used to
return null, seeding continued, and the script printed "Demo setup
complete!" with exit code 0. Now the failure must propagate and the
script must exit nonzero without printing success.

The test drives the script in a node subprocess with fetch stubbed
in-process, so no local services or listening sockets are needed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "seed_demo.js"

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")

_HARNESS = """\
const logs = [];
console.log = (...a) => logs.push(a.join(" "));
console.error = (...a) => logs.push(a.join(" "));
let exitCode = 0;
process.exit = (code) => {
    exitCode = code === undefined ? 0 : code;
    throw new Error("__exit__:" + exitCode);
};
delete process.env.DEMO_TENANT_ID;
process.env.REGENGINE_TENANT_PROVISIONER_KEY = "sentinel-provisioner-key";
const mode = process.env.SEED_HARNESS_MODE || "fail";
globalThis.fetch = async (url) => {
    const target = String(url);
    if (target.endsWith("/health")) {
        return { ok: true, status: 200, json: async () => ({ status: "ok" }) };
    }
    if (target.includes("/v1/internal/tenants")) {
        if (mode === "fail") {
            return { ok: false, status: 500, json: async () => ({ error: "boom" }) };
        }
        return { ok: true, status: 200, json: async () => ({ tenant_id: "sentinel-tenant-id" }) };
    }
    if (target.endsWith("/checklists")) {
        return { ok: true, status: 200, json: async () => [] };
    }
    return { ok: false, status: 404, json: async () => ({}) };
};
const seed = require(process.env.SEED_SCRIPT_PATH);
(async () => {
    try {
        await seed.main();
    } catch (e) {
        if (!String((e && e.message) || e).startsWith("__exit__")) {
            throw e;
        }
    }
    process.stdout.write(JSON.stringify({ exitCode, logs }));
})();
"""


def _run_harness(tmp_path: Path, mode: str):
    harness = tmp_path / "seed_demo_harness.js"
    harness.write_text(_HARNESS)
    env = {
        **os.environ,
        "SEED_HARNESS_MODE": mode,
        "SEED_SCRIPT_PATH": str(SCRIPT),
    }
    env.pop("DEMO_TENANT_ID", None)
    proc = subprocess.run(
        [NODE, str(harness)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, f"harness crashed: {proc.stdout}{proc.stderr}"
    return json.loads(proc.stdout)


@needs_node
def test_tenant_creation_failure_exits_nonzero_without_success(tmp_path):
    """A 500 from tenant creation must fail the run, not print success."""
    result = _run_harness(tmp_path, "fail")
    assert result["exitCode"] != 0
    assert not any("Demo setup complete!" in line for line in result["logs"])
    assert any("Failed to create tenant" in line for line in result["logs"])


@needs_node
def test_tenant_creation_success_still_reports_complete(tmp_path):
    """The happy path must keep working: exit 0 with the success banner."""
    result = _run_harness(tmp_path, "ok")
    assert result["exitCode"] == 0
    assert any("Demo setup complete!" in line for line in result["logs"])
