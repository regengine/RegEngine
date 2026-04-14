FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install shared requirements
COPY services/shared/requirements.txt /app/shared_requirements.txt
RUN pip install --no-cache-dir -r /app/shared_requirements.txt

# Install service requirements
COPY services/scheduler/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code
COPY services/shared /app/services/shared

# Copy application code
COPY services/scheduler /app/services/scheduler

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Create non-root user
RUN useradd --create-home --shell /bin/bash scheduler
USER scheduler

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8600/health || exit 1

# Expose health check port
EXPOSE 8600

# Run the scheduler
CMD ["python", "services/scheduler/main.py"]
