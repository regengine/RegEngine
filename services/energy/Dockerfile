FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (layer caching optimization)
COPY services/energy/requirements.txt services/energy/requirements-test.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/energy/app/ ./app/
COPY services/energy/migrations/ ./migrations/
COPY services/energy/alembic.ini ./

# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -f http://localhost:8700/health || exit 1

# Expose port
EXPOSE 8700

# Run migrations then start server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8700"]
