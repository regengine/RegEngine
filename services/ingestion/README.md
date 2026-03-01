# Ingestion Service

Document upload, processing, and extraction pipeline for RegEngine compliance automation.

## Overview

The Ingestion service handles asynchronous document processing, format extraction, OCR, and regulatory content extraction. It serves as the entry point for all compliance documents into the RegEngine platform.

### Key Features

- **Multi-Format Support:** PDF, DOCX, XLSX, HTML, TXT
- **Async Processing:** Kafka-based job queue for scalable document handling
- **Redis Job Tracking:** Real-time job status and progress monitoring
- **Format Extractors:** Specialized parsers for each document type
- **OCR Capabilities:** Tesseract integration for scanned documents
- **Webhook Notifications:** Real-time callbacks for job completion
- **Rate Limiting:** Prevents abuse and ensures fair resource allocation

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   FastAPI    │────▶│    Kafka     │────▶│   Workers    │
│   Upload API │     │  Job Queue   │     │  Extractors  │
└──────────────┘     └──────────────┘     └──────────────┘
       │                                          │
       ▼                                          ▼
┌──────────────┐                          ┌──────────────┐
│    Redis     │                          │  PostgreSQL  │
│ Job  Status  │                          │   Results    │
└──────────────┘                          └──────────────┘
```

## API Endpoints

### Upload Document

```http
POST /ingestion/upload
Content-Type: multipart/form-data
Authorization: Bearer <jwt_token>

{
  "file": <binary>,
  "tenant_id": "uuid",
  "document_type": "regulation",
  "callback_url": "https://app.regengine.co/webhooks/ingestion"
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "created_at": "2026-01-27T18:00:00Z",
  "estimated_completion": "2026-01-27T18:05:00Z"
}
```

### Check Job Status

```http
GET /ingestion/jobs/{job_id}
Authorization: Bearer <jwt_token>
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "progress": 65,
  "stage": "extracting_text",
  "created_at": "2026-01-27T18:00:00Z",
  "updated_at": "2026-01-27T18:03:00Z",
  "metadata": {
    "filename": "DORA_regulation.pdf",
    "file_size": 2458912,
    "pages": 156
  }
}
```

**Status Values:**
- `queued` - Job accepted, waiting for worker
- `processing` - Actively being processed
- `completed` - Successfully processed
- `failed` - Processing error occurred
- `cancelled` - User cancelled job

### List Jobs

```http
GET /ingestion/jobs?tenant_id=<uuid>&status=completed&limit=50&offset=0
Authorization: Bearer <jwt_token>
```

### Retry Failed Job

```http
POST /ingestion/jobs/{job_id}/retry
Authorization: Bearer <jwt_token>
```

### Cancel Job

```http
DELETE /ingestion/jobs/{job_id}
Authorization: Bearer <jwt_token>
```

## Supported Document Formats

| Format | Extension | Extractor | OCR Support |
|--------|-----------|-----------|-------------|
| PDF | `.pdf` | PyPDF2 + pdfplumber | ✅ |
| Word | `.docx` | python-docx | ❌ |
| Excel | `.xlsx` | openpyxl | ❌ |
| HTML | `.html` | BeautifulSoup4 | ❌ |
| Plain Text | `.txt` | Built-in | ❌ |
| Images | `.png`, `.jpg` | Tesseract OCR | ✅ |

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection string | - | ✅ |
| `REDIS_URL` | Redis connection for job queue | `redis://localhost:6379/0` | ✅ |
| `KAFKA_BROKERS` | Kafka broker addresses | `localhost:9092` | ✅ |
| `KAFKA_TOPIC` | Topic for ingestion jobs | `regengine.ingestion` | ❌ |
| `MAX_FILE_SIZE_MB` | Maximum upload size | `100` | ❌ |
| `JWT_SECRET` | Secret for JWT validation | `dev-secret` | ✅ (prod) |
| `WEBHOOK_TIMEOUT_SEC` | Callback HTTP timeout | `10` | ❌ |
| `OCR_ENABLED` | Enable Tesseract OCR | `true` | ❌ |
| `ALLOWED_ORIGINS` | CORS origins | `*` | ⚠️ (prod) |

## Local Development

### Prerequisites

- Python 3.9+
- PostgreSQL 14+
- Redis 6+
- Kafka 3+ (optional for local dev)
- Tesseract OCR (for PDF OCR)

### Setup

```bash
cd services/ingestion

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Optional: lightweight test-only bootstrap for focused API tests
pip install -r requirements-dev.txt

# Install Tesseract (macOS)
brew install tesseract

# Set environment variables
cp .env.example .env
# Edit .env with your configuration

# Run migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --port 8100
```

### Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=app tests/ --cov-report=html

# View coverage
open htmlcov/index.html  # macOS
```

### Lightweight Pytest Bootstrap (Targeted API Tests)

If you only need to run the focused simulation + EPCIS API tests locally, you can use a minimal environment:

```bash
# from repo root
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r services/ingestion/requirements-dev.txt

python -m pytest \
  services/ingestion/tests/test_recall_simulations_api.py \
  services/ingestion/tests/test_epcis_ingestion_api.py
```

## Docker Deployment

### docker-compose.yml

```yaml
ingestion-api:
  build: ./services/ingestion
  ports:
    - "8100:8000"
  environment:
    - DATABASE_URL=postgresql://admin:${DB_PASSWORD}@postgres:5432/regengine_admin
    - REDIS_URL=redis://redis:6379/0
    - KAFKA_BROKERS=kafka:9092
    - MAX_FILE_SIZE_MB=100
    - JWT_SECRET=${JWT_SECRET}
  depends_on:
    - postgres
    - redis
    - kafka
  volumes:
    - ./data/uploads:/app/uploads
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

### Start Service

```bash
# Development
docker-compose up ingestion-api

# Production
docker-compose -f docker-compose.prod.yml up -d ingestion-api
```

## Health Check

```bash
curl http://localhost:8100/health
```

**Healthy Response:**
```json
{
  "status": "healthy",
  "service": "ingestion-api",
  "version": "1.0.0",
  "timestamp": "2026-01-27T18:30:00Z",
  "dependencies": {
    "postgresql": "connected",
    "redis": "connected",
    "kafka": "connected"
  },
  "metrics": {
    "jobs_queued": 5,
    "jobs_processing": 2,
    "jobs_completed_24h": 1243
  }
}
```

## Webhook Integration

When a job completes (success or failure), the service sends a POST request to the provided `callback_url`:

**Webhook Payload:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "tenant_id": "tenant-uuid",
  "result": {
    "extracted_text": "Full document text...",
    "metadata": {
      "pages": 156,
      "word_count": 45123,
      "language": "en"
    },
    "entities": [
      {
        "type": "date",
        "value": "2024-01-17",
        "confidence": 0.95
      }
    ]
  },
  "completed_at": "2026-01-27T18:05:00Z"
}
```

**Webhook Headers:**
```http
X-RegEngine-Signature: sha256=<hmac_signature>
X-RegEngine-Job-ID: 550e8400-e29b-41d4-a716-446655440000
Content-Type: application/json
```

## Format Extractors

### PDF Extractor

**Features:**
- Text extraction via PyPDF2
- Table extraction via pdfplumber
- OCR fallback for scanned documents
- Metadata extraction (author, creation date, etc.)

**Configuration:**
```python
{
  "ocr_enabled": true,
  "extract_tables": true,
  "extract_images": false,
  "dpi": 300  # For OCR
}
```

### DOCX Extractor

**Features:**
- Paragraph and heading extraction
- Table parsing
- Style preservation
- Comment extraction

### HTML Extractor

**Features:**
- Article extraction (removes nav/footer)
- Link preservation
- Metadata tags (Open Graph, Schema.org)

## Job Queue Architecture

### Kafka Topics

| Topic | Purpose | Retention |
|-------|---------|-----------|
| `regengine.ingestion.jobs` | New ingestion jobs | 7 days |
| `regengine.ingestion.results` | Completed results | 30 days |
| `regengine.ingestion.dlq` | Failed jobs (dead letter) | 90 days |

### Worker Configuration

```python
# app/workers/config.py
WORKER_CONFIG = {
    "max_concurrent_jobs": 5,
    "job_timeout_seconds": 300,
    "retry_attempts": 3,
    "retry_backoff_seconds": [60, 300, 900],  # 1min, 5min, 15min
}
```

## Error Handling

### Common Errors

| Error Code | Description | Resolution |
|------------|-------------|------------|
| `FILE_TOO_LARGE` | Exceeds MAX_FILE_SIZE_MB | Reduce file size or contact admin |
| `UNSUPPORTED_FORMAT` | File type not supported | Convert to PDF/DOCX |
| `OCR_FAILED` | OCR processing error | Check image quality |
| `EXTRACTION_TIMEOUT` | Processing exceeded timeout | Retry with smaller file |
| `KAFKA_UNAVAILABLE` | Message queue down | Check Kafka cluster health |

### Error Response Format

```json
{
  "error": "FILE_TOO_LARGE",
  "detail": "File size 150MB exceeds limit of 100MB",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-01-27T18:00:00Z",
  "retry_possible": false
}
```

## Performance Optimization

### Upload Optimization

- **Chunked Upload:** For files > 10MB, use chunked multipart upload
- **Compression:** Compress files before upload if possible
- **Async Processing:** Don't wait for completion, use webhooks

### Worker Scaling

```bash
# Scale workers horizontally
docker-compose up --scale ingestion-worker=5
```

### Redis Caching

Job status is cached in Redis with 5-minute TTL to reduce database queries.

## Monitoring

### Prometheus Metrics

Available at `/metrics`:

- `regengine_ingestion_jobs_total` - Total jobs processed
- `regengine_ingestion_jobs_duration_seconds` - Processing time histogram
- `regengine_ingestion_errors_total` - Error count by type
- `regengine_ingestion_queue_size` - Current queue depth

### Recommended Alerts

- Queue depth > 100 jobs
- Processing time > 5 minutes (p95)
- Error rate > 5%
- Worker availability < 80%

## Troubleshooting

### Kafka Connection Issues

```bash
# Check Kafka availability
docker-compose ps kafka

# View Kafka logs
docker-compose logs kafka

# Test connection
kafka-topics.sh --list --bootstrap-server localhost:9092
```

### Redis Connection Issues

```bash
# Test Redis
redis-cli -h localhost -p 6379 ping

# Check job queue
redis-cli -h localhost -p 6379 LLEN regengine:jobs
```

### OCR Not Working

```bash
# Check Tesseract installation
tesseract --version

# Test OCR on sample image
tesseract sample.png output.txt
```

### High Memory Usage

- Reduce `max_concurrent_jobs` in worker config
- Enable streaming for large PDFs
- Increase worker memory limits in docker-compose

## Related Documentation

- [Platform Architecture](../../docs/architecture/overview.md)
- [API Authentication](../../docs/auth/jwt_integration.md)
- [Kafka Setup Guide](../../docs/infrastructure/kafka.md)

## Contributing

See: [CONTRIBUTING.md](../../CONTRIBUTING.md)

## License

Proprietary - RegEngine Platform  
Copyright © 2026 RegEngine Inc.
