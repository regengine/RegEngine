FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY services/graph/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user for security
RUN adduser --disabled-password --gecos '' --uid 1001 appuser

# Copy shared code
COPY services/shared /app/shared

# Copy service code
COPY services/graph/app /app/app
COPY services/graph/main.py /app/main.py

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Expose default local port (Railway injects PORT at runtime)
EXPOSE 8200

# Health check (Railway-compatible dynamic port)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD sh -c 'curl -fsS "http://localhost:${PORT:-8200}/health" || exit 1'

# Set ownership and switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Run application (Railway-compatible dynamic port)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8200}"]
