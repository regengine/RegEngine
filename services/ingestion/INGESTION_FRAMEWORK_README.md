# RegEngine Ingestion Framework

A production-grade regulatory document ingestion system with cryptographic verification, complete audit trails, and multi-source support.

**"Verify our math, don't trust our claims."**

## Features

### ✅ Implemented & Tested

- **Document Parsing**: Automatic format detection and text extraction
  - HTML parser (BeautifulSoup)
  - XML parser (lxml)
  - PDF parser (pdfminer.six)
  - Plain text with encoding detection
  
- **Federal Register Adapter**: Complete API integration
  - Rate limiting and robots.txt compliance
  - Bulk document fetching
  - Metadata extraction
  
- **Storage System**:
  - Filesystem storage with hierarchical structure
  - Content-hash based deduplication (SHA-256)
  - Document retrieval by storage key
  
- **PostgreSQL Integration**:
  - Complete database schema (documents, jobs, audit_log)
  - Database manager with CRUD operations
  - Search with filters (vertical, source type)
  - Migration scripts
  
- **Cryptographic Verification**:
  - Dual-hash system (SHA-256 + SHA-512)
  - Content integrity verification
  - Text content hashing
  
- **Audit System**:
  - JSONL file-based audit trail
  - PostgreSQL audit logging
  - Complete provenance tracking
  
- **CLI Interface**:
  - `ingest`: Document ingestion with progress
  - `init-db`: Database schema initialization
  - `search`: Query documents with filters
  - `status`: Job status from audit logs
  - `verify`: Cryptographic integrity verification

### 🚧 Planned (Not Yet Implemented)

- **Additional Source Adapters**:
  - ⏳ eCFR (Code of Federal Regulations)
  - ⏳ FDA/openFDA  
  - ⏳ Generic web crawler
  
- **Cloud Storage**:
  - ⏳ S3 backend for production deployments
  
- **Advanced Features**:
  - ⏳ Connection pooling
  - ⏳ Parallel workers
  - ⏳ Job queue integration.txt

## Quick Start

### Installation

```bash
cd services/ingestion
pip install -r requirements.txt
```

### Configuration

```bash
# Copy example config
cp config/regengine.example.yaml regengine.yaml

# Or use environment variables
export REGENGINE_DB_HOST=localhost
export REGENGINE_DB_NAME=regengine
export REGENGINE_DB_USER=regengine
export REGENGINE_DB_PASSWORD=yourpassword
```

### Run Your First Ingestion

```bash
# Ingest Federal Register documents for FSMA vertical
python -m regengine_ingestion.cli ingest \
  --source federal_register \
  --vertical fsma \
  --max-documents 10

# Check job status
python -m regengine_ingestion.cli status --job-id <job-id>
```

## Python API

```python
from regengine_ingestion import (
    create_engine_local,
    IngestionConfig,
    SourceType
)

# Create engine
engine = create_engine_local(data_path="./data")

# Option 1: Use convenience methods
result = engine.ingest_federal_register(
    vertical="fsma",
    max_documents=100
)

# Option 2: Full configuration control
config = IngestionConfig(
    source_type=SourceType.FEDERAL_REGISTER,
    vertical="fsma",
    max_documents=100,
    parallel_workers=4,
    source_config={"agencies": ["FDA"]}
)
result = engine.run_job(config)

# Check results
print(f"Processed: {result.documents_processed}")
print(f"Succeeded: {result.documents_succeeded}")
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Ingestion Engine                         │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Sources    │  │   Parsers    │  │   Storage    │      │
│  ├──────────────┤  ├──────────────┤  ├──────────────┤      │
│  │ Fed Register │  │ PDF Parser   │  │ PostgreSQL   │      │
│  │ eCFR         │  │ HTML Parser  │  │ (metadata)   │      │
│  │ FDA/openFDA  │  │ XML Parser   │  │              │      │
│  │ Web Crawler  │  │ Text Parser  │  │ S3/Filesystem│      │
│  └──────────────┘  └──────────────┘  │ (documents)  │      │
│                                       └──────────────┘      │
├─────────────────────────────────────────────────────────────┤
│                     Audit Logger                            │
│  (Complete provenance chain for every operation)            │
└─────────────────────────────────────────────────────────────┘
```

## Source Adapters

### Federal Register
```bash
python -m regengine_ingestion.cli ingest \
  --source federal_register \
  --vertical fsma \
  --date-from 2024-01-01 \
  --agencies FDA,EPA
```

## Verification

Every document includes cryptographic hashes for verification:

```python
from regengine_ingestion import StorageManager

# Retrieve document
storage = StorageManager(Path("./data"))
content = storage.retrieve_document(storage_key)

# Verify hash
import hashlib
computed_hash = hashlib.sha256(content).hexdigest()
assert computed_hash == doc.hash.content_sha256
print("✓ Document integrity verified")
```

CLI verification:
```bash
python -m regengine_ingestion.cli verify --document-id <id>
```

## Verticals

| Vertical   | CFR Titles | Primary Sources |
|------------|------------|-----------------|
| FSMA       | 21         | FDA, Federal Register, eCFR |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REGENGINE_DB_HOST` | PostgreSQL host | localhost |
| `REGENGINE_DB_PORT` | PostgreSQL port | 5432 |
| `REGENGINE_DB_NAME` | Database name | regengine |
| `REGENGINE_DB_USER` | Database user | regengine |
| `REGENGINE_DB_PASSWORD` | Database password | (empty) |
| `REGENGINE_DATA_PATH` | Local data directory | ./data |
| `REGENGINE_FDA_API_KEY` | openFDA API key | (optional) |

## Development

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run tests
pytest tests/

# Format code
black regengine_ingestion/
```

## License

Proprietary - RegEngine Inc.

## Support

- Documentation: https://docs.regengine.io
- Email: support@regengine.io
