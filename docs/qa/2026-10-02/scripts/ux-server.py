"""Start an isolated localhost-only UI mirror; stop when its stop file appears."""
from pathlib import Path
import hashlib
import os
import shutil
import secrets
import subprocess
import sys
import threading
import time

from run_logged import redact

root = Path(__file__).resolve().parents[4]
base = Path('/private/tmp/regengine-qa-ux-u2059hm8')
app = base / 'app-built'
if not app.exists():
    shutil.copytree(root / 'frontend', app, ignore=lambda directory, names: [
        name for name in names if name in {'node_modules', '.next', 'coverage', 'test-results', 'playwright-report', '.git', '.npmrc', '.netrc', 'credentials'} or name.startswith('.env')
    ])
    (app / 'node_modules').symlink_to(root / 'frontend/node_modules', target_is_directory=True)
    shutil.copytree(root / 'frontend/.next', app / '.next', ignore=lambda directory, names: [name for name in names if name in {'cache', 'dev'}])
guard = root / 'docs/qa/2026-10-02/scripts/node-isolation.cjs'
artifacts = root / 'docs/qa/2026-10-02/artifacts/ux'
env = dict(os.environ, NODE_OPTIONS=f'--require={guard}',
           CSRF_SECRET=secrets.token_urlsafe(48),
           ADMIN_SERVICE_URL='http://127.0.0.1:3103',
           INGESTION_SERVICE_URL='http://127.0.0.1:3103',
           COMPLIANCE_SERVICE_URL='http://127.0.0.1:3103')
command = ['node', str(root / 'frontend/node_modules/next/dist/bin/next'), 'start', '-H', '127.0.0.1', '-p', '3104']
process = subprocess.Popen(command, cwd=app, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
(artifacts / 'ready-server-metadata.txt').write_text(f'PID={process.pid}\nPort=3104\nGuard SHA256={hashlib.sha256(guard.read_bytes()).hexdigest()}\nMirror={app}\nCommand={command}\nCSRF runtime value: ephemeral synthetic, never recorded\n')

def capture():
    with (artifacts / 'ready-server-output.txt').open('w') as log:
        for line in process.stdout:
            log.write(redact(line))
            log.flush()

thread = threading.Thread(target=capture, daemon=True)
thread.start()
try:
    deadline = time.monotonic() + 1500
    while process.poll() is None and time.monotonic() < deadline and not (base / 'stop-ready-server').exists():
        time.sleep(0.25)
finally:
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    thread.join(timeout=5)
    print(f'QA server stopped; exit {process.returncode}; redacted output saved')
