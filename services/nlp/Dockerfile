FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# gcc used for building some python packages if needed (e.g. psutil)
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY services/nlp/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt



# Copy shared code
COPY shared /app/shared

# Copy service code
# We expect the context to be the project root
COPY services/nlp/app /app/app
COPY services/nlp/main.py /app/main.py
COPY data-schemas /app/data-schemas

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8100"]
