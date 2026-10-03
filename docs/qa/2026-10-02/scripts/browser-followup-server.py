"""Reuse the prior production build in a disposable, credential-free local mirror.

The existing node-isolation.cjs protects file reads and off-host sockets.
Browser clients must intercept API requests and deny off-origin traffic.
"""
from pathlib import Path
import hashlib
import os
import secrets
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'docs/qa/2026-10-02/artifacts/browser'
OUT.mkdir(parents=True, exist_ok=True)
BASE = Path(tempfile.mkdtemp(prefix='regengine-browser-followup-', dir='/private/tmp'))
APP = BASE / 'frontend'
APP.mkdir()
for name in ['next.config.js', 'package.json']:
    shutil.copy2(ROOT / 'frontend' / name, APP / name)
shutil.copytree(ROOT / 'frontend/public', APP / 'public')
shutil.copytree(ROOT / 'frontend/.next', APP / '.next',
                ignore=lambda directory, names: [name for name in names if name in {'cache', 'dev'}])
(APP / 'node_modules').symlink_to(ROOT / 'frontend/node_modules', target_is_directory=True)
GUARD = ROOT / 'docs/qa/2026-10-02/scripts/node-isolation.cjs'
env = {key: value for key, value in os.environ.items() if key in {'PATH', 'TMPDIR', 'LANG'}}
env.update({
    'NODE_OPTIONS': f'--require={GUARD}',
    'NEXT_TELEMETRY_DISABLED': '1', 'DO_NOT_TRACK': '1',
    'CSRF_SECRET': secrets.token_urlsafe(48),
    'ADMIN_SERVICE_URL': 'http://127.0.0.1:3113',
    'INGESTION_SERVICE_URL': 'http://127.0.0.1:3113',
    'COMPLIANCE_SERVICE_URL': 'http://127.0.0.1:3113',
    'NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES': 'true',
})
command = ['node', str(ROOT / 'frontend/node_modules/next/dist/bin/next'),
           'start', '-H', '127.0.0.1', '-p', '3114']
process = subprocess.Popen(command, cwd=APP, env=env)
metadata = (f'PID={process.pid}\nPort=3114\nMirror={APP}\n'
            f'StopFile={BASE / "stop"}\nGuard SHA256={hashlib.sha256(GUARD.read_bytes()).hexdigest()}\n'
            f'Build ID={(APP / ".next/BUILD_ID").read_text().strip()}\n'
            'Runtime CSRF value: ephemeral synthetic, not recorded\n')
stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
(OUT / f'followup-server-{stamp}-metadata.txt').write_text(metadata)
print(metadata, flush=True)
try:
    deadline = time.monotonic() + 5100
    while process.poll() is None and time.monotonic() < deadline and not (BASE / 'stop').exists():
        time.sleep(.25)
finally:
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    print(f'QA built server stopped; exit {process.returncode}', flush=True)
