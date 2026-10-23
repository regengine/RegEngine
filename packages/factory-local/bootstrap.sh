#!/usr/bin/env bash
# One command local setup for an explicitly selected live bill or state scan.
#   ./bootstrap.sh
#   ./bootstrap.sh --bill BILL [--state STATE]
# requirements.lock carries every dependency (including beautifulsoup4, pypdf, openai).
# Host ports: export FACTORY_PG_PORT / FACTORY_OPA_PORT / FACTORY_NEO4J_BOLT_PORT /
# FACTORY_NEO4J_HTTP_PORT first if the defaults are taken. PYTHON picks the interpreter.
set -euo pipefail
cd "$(dirname "$0")"

if [ "$#" -eq 0 ]; then
  echo "No data yet"
  exit 0
fi

if [ -z "${PYTHON:-}" ]; then
  if command -v python3.12 >/dev/null 2>&1; then PYTHON=python3.12; else PYTHON=python3; fi
fi

if [ ! -x .venv/bin/python ]; then
  echo "==> creating .venv with $PYTHON"
  "$PYTHON" -m venv .venv
fi

# Reinstall only when requirements.lock changed since the last successful install.
lock_hash=$(.venv/bin/python -c 'import hashlib; print(hashlib.sha256(open("requirements.lock", "rb").read()).hexdigest())')
stamp=.venv/.requirements.lock.sha256
if [ ! -f "$stamp" ] || [ "$(cat "$stamp")" != "$lock_hash" ]; then
  echo "==> installing requirements.lock (--require-hashes)"
  .venv/bin/python -m pip install --quiet --disable-pip-version-check --require-hashes -r requirements.lock
  echo "$lock_hash" > "$stamp"
fi

if docker compose version >/dev/null 2>&1; then
  compose=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  compose=(docker-compose)
else
  echo "docker compose not found (neither the plugin nor docker-compose)" >&2
  exit 1
fi

if [ ! -f .env ]; then
  # Each changeme placeholder gets its own random value. Written 0600, never printed.
  .venv/bin/python - <<'PY'
import os
import re
import secrets

text = re.sub("changeme", lambda _: secrets.token_urlsafe(24), open(".env.example").read())
fd = os.open(".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as fh:
    fh.write(text)
PY
  echo "==> created .env with generated passwords"
  # Containers left from an older .env would be recreated with their old Postgres
  # volume, whose password no longer matches. Remove the containers (not volumes).
  "${compose[@]}" down --remove-orphans >/dev/null 2>&1 || true
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

echo "==> starting OPA, Postgres, Neo4j"
"${compose[@]}" up -d --wait

# Healthy inside the Docker VM can come before the host port forward (colima).
.venv/bin/python - <<'PY'
import os
import socket
import time

ports = [int(os.environ.get(name, default)) for name, default in
         (("FACTORY_PG_PORT", "5432"), ("FACTORY_OPA_PORT", "8181"), ("FACTORY_NEO4J_BOLT_PORT", "7687"))]
deadline = time.monotonic() + 60
for port in ports:
    while True:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=2).close()
            break
        except OSError:
            if time.monotonic() > deadline:
                raise SystemExit(f"host port {port} not reachable after 60s")
            time.sleep(1)
PY

# Live bills embed with nomic-embed-text (EMBEDDING_MODEL) for copycat detection.
if command -v ollama >/dev/null 2>&1; then
  echo "==> ollama pull nomic-embed-text"
  ollama pull nomic-embed-text || echo "ollama pull failed; live bills need the embedding model" >&2
fi

echo "==> live input selected"
.venv/bin/python app/local_factory.py "$@"
