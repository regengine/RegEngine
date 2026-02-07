FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY services/opportunity/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code
COPY shared /app/shared

# Copy service code
COPY services/opportunity/app /app/app
COPY services/opportunity/main.py /app/main.py

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8300"]
