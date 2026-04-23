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

# Runtime-only system deps (libpq for psycopg2, curl for health-check)
RUN apt-get update && apt-get install -y --no-install-recommends \
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

# Copy kernel package (obligation, discovery, graph, reporting modules)
COPY kernel /app/kernel

# Copy plugins (FSMA sources, etc.)
COPY plugins /app/plugins

# Copy monolith entry point
COPY server /app/server

# Set PYTHONPATH so all service imports resolve
ENV PYTHONPATH=/app:/app/services:/app/services/ingestion:/app/services/admin:/app/services/graph:/app/services/nlp:/app/services/compliance

# Expose default port (Railway injects PORT at runtime)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD sh -c 'curl -fsS "http://localhost:${PORT:-8000}/health" || exit 1'

# Issue #1155: Remove any test files that slipped through the build context
RUN find /app -name "test_*.py" -delete

# Set ownership and switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Run migrations then start monolith with Gunicorn + Uvicorn workers
# WEB_CONCURRENCY controls worker count (default: 4).
# Gunicorn manages process lifecycle; each worker is a Uvicorn async process.
CMD ["sh", "-c", "bash /app/scripts/run-migrations.sh && gunicorn server.main:app --worker-class uvicorn.workers.UvicornWorker --workers ${WEB_CONCURRENCY:-4} --bind 0.0.0.0:${PORT:-8000} --timeout 120 --graceful-timeout 30 --keep-alive 5 --access-logfile - --error-logfile -"]
