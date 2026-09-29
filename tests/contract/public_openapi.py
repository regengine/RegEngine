"""Load the same TypeScript spec that both public Next.js routes serve."""

import json
import os
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = _REPO_ROOT / "frontend/src/lib/public-openapi.ts"
_LOAD_SPEC = """
const fs = require('node:fs');
const filename = process.argv[1];
(async () => {
  // The maintained module is also valid JavaScript: execute its complete source
  // on Node 20 without stripping syntax, installing a compiler, or copying data.
  const source = fs.readFileSync(filename, 'utf8');
  const module = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
  process.stdout.write(JSON.stringify(module.publicOpenApiSpec));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


def load_public_openapi(env_overrides: dict[str, str] | None = None) -> dict:
    """Execute the JS-compatible TypeScript module, without parsing its text."""
    result = subprocess.run(
        ["node", "-e", _LOAD_SPEC, str(_SPEC)],
        cwd=_REPO_ROOT,
        env={**os.environ, **(env_overrides or {})},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        "Cannot load the public spec. Keep public-openapi.ts valid JavaScript "
        "so Node 20 can execute it without frontend dependencies.\n" + result.stderr
    )
    return json.loads(result.stdout)
