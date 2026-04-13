# Pin to patch version for reproducible builds (#1010)
FROM python:3.11.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (cache-bust: 2026-03-18 openpyxl fix)
COPY services/admin/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user for security
RUN adduser --disabled-password --gecos '' --uid 1001 appuser

# Copy shared code
COPY services/shared /app/shared

# Copy Alembic migration framework
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY migrations /app/migrations
COPY scripts/run-migrations.sh /app/scripts/run-migrations.sh

# Copy service code
COPY services/admin/app /app/app
COPY services/admin/main.py /app/main.py

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Expose default local port (Railway injects PORT at runtime)
EXPOSE 8400

# Health check (Railway-compatible dynamic port)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD sh -c 'curl -fsS "http://localhost:${PORT:-8400}/health" || exit 1'

# Set ownership and switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Run migrations then start application (Railway-compatible dynamic port)
CMD ["sh", "-c", "bash /app/scripts/run-migrations.sh && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8400}"]
