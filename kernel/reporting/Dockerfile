# Stage 1: builder — has gcc/libpq-dev for compiling Python C extensions
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY kernel/reporting/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: runtime — no build toolchain, only the shared runtime library
FROM python:3.11-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Pull installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy shared code
COPY shared /app/shared

# Copy service code
COPY services/compliance/app /app/app
COPY services/compliance/checklist_engine.py /app/checklist_engine.py
COPY services/compliance/drift_engine.py /app/drift_engine.py
COPY services/compliance/fsma_engine.py /app/fsma_engine.py
COPY services/compliance/fsma_spreadsheet.py /app/fsma_spreadsheet.py
COPY services/compliance/main.py /app/main.py

# Copy plugins if they exist (assuming simple structure, modify if plugins dir is complex)
# Ideally COPY entire services/compliance context but sticking to explicit copies for safety
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
