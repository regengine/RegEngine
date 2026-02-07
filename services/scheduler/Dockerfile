FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (libpq-dev needed for psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash scheduler
USER scheduler

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8600/health || exit 1

# Expose health check port
EXPOSE 8600

# Run the scheduler
CMD ["python", "main.py"]
