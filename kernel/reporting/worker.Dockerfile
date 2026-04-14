FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install shared requirements
COPY services/shared/requirements.txt /app/shared_requirements.txt
RUN pip install --no-cache-dir -r /app/shared_requirements.txt

# Install service requirements
COPY services/compliance/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code
COPY services/shared /app/services/shared

# Copy application code
COPY kernel /app/kernel
COPY schemas /app/schemas

# Set PYTHONPATH
ENV PYTHONPATH=/app
ENV SCHEMA_DIR=/app/schemas

# Create non-root user
RUN useradd -m -s /bin/bash regengine
RUN chown -R regengine:regengine /app
USER regengine

# Liveness probe: worker writes /tmp/compliance-worker-healthy periodically
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD test -f /tmp/compliance-worker-healthy && \
    test $(( $(date +%s) - $(date -r /tmp/compliance-worker-healthy +%s) )) -lt 120 || exit 1

CMD ["python", "kernel/reporting/worker/main.py"]
