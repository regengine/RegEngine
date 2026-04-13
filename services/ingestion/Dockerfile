# RegEngine Ingestion Service
# Supports: PDF, HTML, XML, CSV, Excel, Word DOCX, EDI

# Pin to patch version for reproducible builds (#1010)
FROM python:3.11.9-slim

WORKDIR /app

# Install system dependencies for document processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    # For PDF OCR fallback
    tesseract-ocr \
    poppler-utils \
    # For pyzbar runtime QR/barcode decoding
    libzbar0 \
    # For lxml
    libxml2-dev \
    libxslt1-dev \
    # For health checks
    curl \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Copy shared module first (for auth, etc.)
COPY services/shared /app/shared

# Copy service requirements
COPY services/ingestion/requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy service code
COPY services/ingestion/app /app/app
COPY services/ingestion/regengine_ingestion /app/regengine_ingestion
COPY services/ingestion/main.py /app/main.py
COPY services/ingestion/tests /app/tests
COPY services/ingestion/scripts /app/scripts

# Copy kernel and FSMA plugin (required for discovery + scoring)
COPY kernel /app/kernel
COPY plugins /app/plugins

# Copy Avro schemas for Kafka serialization
COPY schemas /app/schemas

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser /app
USER appuser

# Expose default local port (Railway injects PORT at runtime)
EXPOSE 8000

# Health check (Railway-compatible dynamic port)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD sh -c 'curl -fsS "http://localhost:${PORT:-8000}/health" || exit 1'

# Run with uvicorn (Railway-compatible dynamic port)
CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
