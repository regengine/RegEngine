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
COPY services/compliance /app/services/compliance

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Create non-root user
RUN useradd -m -s /bin/bash regengine
RUN chown -R regengine:regengine /app
USER regengine

EXPOSE 8500

# Health check (Railway-compatible dynamic port)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD sh -c 'curl -fsS "http://localhost:${PORT:-8500}/health" || exit 1'

CMD ["sh", "-c", "python -m uvicorn services.compliance.main:app --host 0.0.0.0 --port ${PORT:-8500}"]
