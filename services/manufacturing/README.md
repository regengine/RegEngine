# RegEngine Manufacturing Compliance Service

NCR (Non-Conformance Report) engine and CAPA tracking for ISO 9001/14001/45001 triple certification compliance.

## 🏭 Regulatory Standards

- **ISO 9001:2015** - Quality Management System
- **ISO 14001:2015** - Environmental Management
- **ISO 45001:2018** - Occupational Health & Safety
- **8D Problem Solving** - Supplier quality management

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment
export MANUFACTURING_DATABASE_URL="postgresql://postgres:postgres@localhost:5432/regengine_manufacturing"
export MANUFACTURING_PORT=8010

# Run service
python -m app.main
```

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/manufacturing/ncr` | POST | Create NCR |
| `/v1/manufacturing/ncr/{id}` | GET | Get NCR details |
| `/v1/manufacturing/capa` | POST | Create CAPA |
| `/v1/manufacturing/supplier-issue` | POST | Record supplier issue (8D) |
| `/v1/manufacturing/audit-finding` | POST | Record audit finding |
| `/v1/manufacturing/dashboard` | GET | Dashboard metrics |

## 📊 Key Features

- **NCR Management**: Track non-conformances with root cause analysis
- **CAPA Tracking**: Corrective/preventive actions with effectiveness verification
- **8D Problem Solving**: Supplier quality issue management
- **ISO Audit Findings**: Internal and external audit tracking
- **Triple Cert Support**: ISO 9001 + 14001 + 45001

See full documentation at `/docs`
