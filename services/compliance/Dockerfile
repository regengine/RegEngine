FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -s /bin/bash regengine
RUN chown -R regengine:regengine /app
USER regengine

EXPOSE 8500

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8500"]