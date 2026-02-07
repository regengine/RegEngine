# RegEngine Ingestion Service
# Supports: PDF, HTML, XML, CSV, Excel, Word DOCX, EDI

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for document processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    # For PDF OCR fallback
    tesseract-ocr \
    poppler-utils \
    # For lxml
    libxml2-dev \
    libxslt1-dev \
    # For health checks
    curl \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Copy shared module first (for auth, etc.)
COPY shared /app/shared

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

# Copy Avro schemas for Kafka serialization
COPY schemas /app/schemas

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with uvicorn
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
