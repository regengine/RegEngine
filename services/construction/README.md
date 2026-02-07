# RegEngine Construction Compliance Service

BIM version control and OSHA safety tracking for ISO 9001/14001/45001/19650 quad certification.

## 🏗️ Standards

- **ISO 19650** - BIM Information Management
- **OSHA 1926** - Safety Standards for Construction
- **ISO 9001/14001/45001** - Quality/Environment/Safety

## 🚀 Quick Start

```bash
pip install -r requirements.txt
export CONSTRUCTION_DATABASE_URL="postgresql://..."
python -m app.main
```

## 📡 Endpoints

- `POST /v1/construction/bim-change` - Track BIM changes
- `POST /v1/construction/osha-inspection` - Record safety inspections
- `GET /v1/construction/dashboard` - Metrics

Full docs at `/docs`
