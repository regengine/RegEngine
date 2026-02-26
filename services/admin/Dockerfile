FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY services/admin/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user for security
RUN adduser --disabled-password --gecos '' --uid 1001 appuser

# Copy shared code
COPY services/shared /app/shared

# Copy service code
COPY services/admin/app /app/app
COPY services/admin/main.py /app/main.py

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8400

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8400/health || exit 1

# Set ownership and switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8400"]
