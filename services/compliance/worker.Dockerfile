
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy schemas (shared volume in Compose usually, but copy for safety)
# Expectation: schemas are at ../../../schemas relative to service
COPY schemas /app/schemas

# Copy dependencies
COPY services/compliance/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/compliance /app/services/compliance

# Define PYTHONPATH to include service and root
# We need to run from /app so that "services.compliance" is importable if needed
# But our worker script uses relative imports from "worker".
# Let's set PYTHONPATH to /app
ENV PYTHONPATH=/app

# Command
CMD ["python", "services/compliance/worker/main.py"]
