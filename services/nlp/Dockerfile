# ---------- builder stage: compile C extensions with gcc ----------
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install shared requirements
COPY services/shared/requirements.txt /build/shared_requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r /build/shared_requirements.txt

# Install NLP service requirements
COPY services/nlp/requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r /build/requirements.txt

# ---------- runtime stage: no gcc, no build tools (#996) ----------
FROM python:3.11-slim

WORKDIR /app

# Runtime-only system deps
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built Python packages from builder
COPY --from=builder /install /usr/local

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
