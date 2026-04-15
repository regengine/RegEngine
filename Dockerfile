FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies — single consolidated requirements file
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user
RUN adduser --disabled-password --gecos '' --uid 1001 appuser

# Copy Alembic migration framework
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY migrations /app/migrations
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

# Set ownership and switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Run migrations then start monolith with Gunicorn + Uvicorn workers
# WEB_CONCURRENCY controls worker count (default: 4).
# Gunicorn manages process lifecycle; each worker is a Uvicorn async process.
CMD ["sh", "-c", "bash /app/scripts/run-migrations.sh && gunicorn server.main:app --worker-class uvicorn.workers.UvicornWorker --workers ${WEB_CONCURRENCY:-4} --bind 0.0.0.0:${PORT:-8000} --timeout 120 --graceful-timeout 30 --keep-alive 5 --access-logfile - --error-logfile -"]
