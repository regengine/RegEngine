FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY services/compliance/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code
COPY shared /app/shared

# Copy service code
COPY services/compliance/app /app/app
COPY services/compliance/checklist_engine.py /app/checklist_engine.py
COPY services/compliance/drift_engine.py /app/drift_engine.py
COPY services/compliance/fsma_engine.py /app/fsma_engine.py
COPY services/compliance/fsma_spreadsheet.py /app/fsma_spreadsheet.py
COPY services/compliance/main.py /app/main.py

# Copy plugins if they exist (assuming simple structure, modify if plugins dir is complex)
# Ideally COPY entire services/compliance context but sticking to explicit copies for safety
COPY services/compliance/plugins /app/plugins

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8500

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8500/health || exit 1

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8500"]
