FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install shared requirements
COPY services/shared/requirements.txt /app/shared_requirements.txt
RUN pip install --no-cache-dir -r /app/shared_requirements.txt

# Install service requirements
COPY services/billing/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code
COPY services/shared /app/services/shared

# Copy application code
COPY services/billing /app/services/billing

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Create non-root user
RUN useradd -m -s /bin/bash regengine
RUN chown -R regengine:regengine /app
USER regengine

EXPOSE 8800

CMD ["python", "-m", "uvicorn", "services.billing.main:app", "--host", "0.0.0.0", "--port", "8800"]