FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install shared requirements
COPY services/shared/requirements.txt /app/shared_requirements.txt
RUN pip install --no-cache-dir -r /app/shared_requirements.txt

# Install Python dependencies
COPY services/nlp/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user for security
RUN adduser --disabled-password --gecos '' --uid 1001 appuser

# Copy shared modules
COPY services/shared /app/services/shared

# Copy service code
COPY services/nlp /app/services/nlp
COPY data-schemas /app/data-schemas

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8100

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8100/health || exit 1

# Set ownership and switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Run application
CMD ["python", "-m", "uvicorn", "services.nlp.main:app", "--host", "0.0.0.0", "--port", "8100"]
