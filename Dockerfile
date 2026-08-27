# ── Stage 1: builder ──────────────────────────────────────────────
# Installs build-time system deps (gcc, libpq-dev) and all Python packages.
# Nothing from this stage leaks into the final runtime image.
FROM python:3.11-slim AS builder

WORKDIR /app

# Build deps needed only at compile/link time
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from the pip-compile lockfile.
# requirements.in = human-edited loose spec; requirements.lock = fully pinned w/ hashes.
# --require-hashes enforces that every dep resolves to the exact artifact in the lock.
COPY requirements.in /app/requirements.in
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock

# ── Stage 2: runtime ──────────────────────────────────────────────
# Lean image: no gcc, no libpq-dev, no build-essential.
# Only the installed site-packages and application code are copied.
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime-only system deps (libpq for psycopg2, curl for health-check).
# Upgrade first so security-fixed Debian packages in the current slim base
# land in the deployed image instead of waiting for the next base tag refresh.
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Packaging/build tooling is only needed during image build. Prune it from the
# runtime layer to reduce attack surface and keep Trivy focused on deployed code.
RUN rm -rf \
    /usr/local/lib/python3.11/site-packages/wheel \
    /usr/local/lib/python3.11/site-packages/wheel-* \
    /usr/local/lib/python3.11/site-packages/setuptools/_vendor/jaraco/context \
    /usr/local/lib/python3.11/site-packages/setuptools/_vendor/jaraco_context* \
    /usr/local/lib/python3.11/site-packages/setuptools/_vendor/jaraco.context* \
    /usr/local/lib/python3.11/site-packages/setuptools/_vendor/wheel* \
    /usr/local/bin/wheel

# Create non-root user
RUN adduser --disabled-password --gecos '' --uid 1001 appuser

# Copy Alembic migration framework (single migration system)
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY scripts/run-migrations.sh /app/scripts/run-migrations.sh

# Copy all service code
COPY services /app/services

# Copy plugins (FSMA sources, etc.)
COPY plugins /app/plugins

# Copy the event JSON schemas (#2965). These are NOT optional documentation:
# services/nlp/app/consumer/schema_validation.py loads
# data-schemas/events/ingest.normalized.schema.json at import to validate every
# inbound Kafka message (OWASP API10:2023). Without this COPY the loader gets a
# FileNotFoundError and the consumer runs with a fail-closed stub validator
# that rejects every message — the container is broken loudly instead of
# silently passing hostile payloads through, but it is still broken.
COPY data-schemas /app/data-schemas

# Copy normalized QA health baseline used by the sysadmin dashboard. Raw test
# outputs stay excluded by .dockerignore; this JSON is a redacted rollup only.
COPY qa/qa-health /app/qa/qa-health

# Copy monolith entry point
COPY server /app/server

# Build identity. The deploy pipeline overwrites this with the commit it is
# shipping immediately before `railway up`; the committed placeholder is the
# literal string "unknown", which build_info rejects as a non-SHA and reports
# as absent. A committed real SHA would be worse than nothing — it would go
# stale and lie. .dockerignore excludes .git, so this file is the only way
# identity reaches the image.
COPY build-sha.txt /app/build-sha.txt

# Set PYTHONPATH so all service imports resolve
ENV PYTHONPATH=/app:/app/services:/app/services/ingestion:/app/services/admin:/app/services/graph:/app/services/nlp:/app/services/compliance

# services/shared/paths.py documents PROJECT_ROOT as "set automatically in
# Docker". It was not (#2965), so project_root() fell through to a heuristic
# that hunts for docker-compose.dev.yml or pyproject.toml — neither of which is
# copied into this image. Setting it makes the documented contract true and
# means the heuristic is never exercised in a container.
ENV PROJECT_ROOT=/app

# Fail the BUILD, not a 3am pager, if a path the shared helpers resolve is
# missing from the image. Cheap backstop for the class of defect above.
RUN python -c "\
import os, sys; \
sys.path.insert(0, '/app/services'); \
from shared.paths import data_schemas_dir; \
p = data_schemas_dir() / 'events' / 'ingest.normalized.schema.json'; \
sys.exit(0) if p.exists() else sys.exit('MISSING in image: %s' % p)"

# Expose default port (Railway injects PORT at runtime)
EXPOSE 8000

# Dependency-aware health check. Railway also probes /readiness.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD sh -c 'curl -fsS "http://localhost:${PORT:-8000}/readiness" || exit 1'

# Issue #1155: Remove any test files that slipped through the build context
RUN find /app -name "test_*.py" -delete

# Set ownership and switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Run migrations then start monolith with Gunicorn + Uvicorn workers
# WEB_CONCURRENCY controls worker count (default: 4).
# Gunicorn manages process lifecycle; each worker is a Uvicorn async process.
CMD ["sh", "-c", "bash /app/scripts/run-migrations.sh && gunicorn server.main:app --worker-class uvicorn.workers.UvicornWorker --workers ${WEB_CONCURRENCY:-4} --bind 0.0.0.0:${PORT:-8000} --timeout 120 --graceful-timeout 30 --keep-alive 5 --access-logfile - --error-logfile -"]
