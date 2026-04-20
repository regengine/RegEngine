# ── Stage 1: builder ──────────────────────────────────────────────
# Install build-time system deps (gcc, libpq-dev) and all Python packages.
# Nothing from this stage leaks into the final runtime image.
FROM python:3.11-slim AS builder

WORKDIR /app

# Build deps needed only at compile/link time
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY kernel/reporting/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime ──────────────────────────────────────────────
# Lean image: no gcc, no libpq-dev, no build-essential.
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime-only system deps (libpq5 for psycopg2, curl for health-check)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy shared code
COPY shared /app/shared

# Copy service code
COPY services/compliance/app /app/app
COPY services/compliance/checklist_engine.py /app/checklist_engine.py
COPY services/compliance/drift_engine.py /app/drift_engine.py
COPY services/compliance/fsma_engine.py /app/fsma_engine.py
COPY services/compliance/fsma_spreadsheet.py /app/fsma_spreadsheet.py
COPY services/compliance/main.py /app/main.py

# Copy plugins
COPY services/compliance/plugins /app/plugins

# Create non-root user for security
RUN groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid 1001 --no-create-home appuser

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8500

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8500/health || exit 1

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8500"]
