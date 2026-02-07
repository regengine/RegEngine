# RegEngine Aerospace Compliance Service

AS9102 FAI (First Article Inspection) vault and configuration baseline tracking for AS9100 compliance with 30-year lifecycle support.

## ✈️ Regulatory Standards

- **AS9100 Rev D** - Aerospace Quality Management System
- **AS9102 Rev B** - First Article Inspection (FAI)
- **AS9145** - Advanced Product Quality Planning (APQP)
- **NADCAP** - Special Process Accreditation (Heat Treat, Welding, NDT, Chemical)

## 🚀 Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export AEROSPACE_DATABASE_URL="postgresql://postgres:postgres@localhost:5432/regengine_aerospace"
export AEROSPACE_PORT=8009

# Run service
python -m app.main
```

### Docker

```bash
# Build image
docker build -t regengine/aerospace:latest .

# Run container
docker run -p 8009:8009 \
  -e AEROSPACE_DATABASE_URL="postgresql://postgres:postgres@host.docker.internal:5432/regengine_aerospace" \
  regengine/aerospace:latest
```

## 📡 API Endpoints

### FAI Vault

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/aerospace/fai` | POST | Create AS9102 FAI report |
| `/v1/aerospace/fai/{id}` | GET | Retrieve FAI report |
| `/v1/aerospace/fai/{id}/approve` | PATCH | Update approval status |

### Configuration Baselines

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/aerospace/config-baseline` | POST | Create configuration baseline |
| `/v1/aerospace/config-baseline/{id}` | GET | Retrieve baseline |

### NADCAP Evidence

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/aerospace/nadcap-evidence` | POST | Record special process evidence |
| `/v1/aerospace/dashboard` | GET | Dashboard metrics |

## 🔒 Security

- **API Key Authentication**: Required via `X-RegEngine-API-Key` header
- **Cryptographic Integrity**: SHA-256 hashing for FAI reports and baselines
- **30-Year Retention**: Designed for aerospace part lifecycle requirements

## 📊 Database Schema

### `fai_reports`
AS9102 First Article Inspection reports.

**AS9102 Forms:**
- **Form 1**: Part Number Accountability
- **Form 2**: Product Accountability
- **Form 3**: Characteristic Accountability

**Key Fields:**
- `part_number` - Manufacturer part number
- `drawing_revision` - Engineering drawing revision
- `form1_data`, `form2_data`, `form3_data` - JSON AS9102 forms
- `content_hash` - SHA-256 of all forms
- `inspection_method` - ACTUAL | DELTA | BASELINE

### `configuration_baselines`
30-year configuration tracking for aerospace assemblies.

**Purpose:**
- Track exact component revisions used in each assembly
- Support field service decades after production
- Maintain part genealogy for recalls and investigations

**Key Fields:**
- `assembly_id` - Assembly identifier
- `serial_number` - Unique serial number
- `baseline_data` - JSON list of components with part numbers and revisions
- `baseline_hash` - SHA-256 of configuration
- `lifecycle_status` - ACTIVE | MAINTENANCE | RETIRED

### `nadcap_evidence`
NADCAP special process evidence vault.

**Process Types:**
- **HEAT_TREAT**: Pyrometry logs, temperature/time/atmosphere
- **WELDING**: Parameters, weld maps, NDT results
- **NDT**: Inspection results, technician certification
- **CHEMICAL**: Chemistry, immersion time, tank cert

**Key Fields:**
- `process_type` - Type of NADCAP process
- `process_parameters` - JSON parameters (temp, time, etc.)
- `process_results` - JSON results (hardness, etc.)
- `content_hash` - SHA-256 for immutability

## 📈 AS9102 Inspection Methods

| Method | Description | Use Case |
|--------|-------------|----------|
| **ACTUAL** | Full characteristic inspection | New part, first build |
| **DELTA** | Incremental changes only | Engineering change, process change |
| **BASELINE** | Comparison to approved FAI | Re-verification after suspension |

## 💡 Example Usage

### Create FAI Report

```bash
curl -X POST http://localhost:8009/v1/aerospace/fai \
  -H "X-RegEngine-API-Key: demo-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "part_number": "123-456-789",
    "part_name": "Turbine Blade Assembly",
    "drawing_number": "DWG-123456",
    "drawing_revision": "C",
    "customer_name": "Boeing",
    "inspection_method": "ACTUAL",
    "inspection_date": "2026-01-28T20:00:00Z",
    "inspector_name": "Jane Smith",
    "form1_data": {
      "organization": "Acme Aerospace",
      "part_number": "123-456-789",
      "drawing_revision": "C"
    },
    "form2_data": [{
      "characteristic": "Overall Length",
      "specification": "10.000 +/- 0.005",
      "actual": "10.002",
      "result": "ACCEPT"
    }],
    "form3_data": [{
      "characteristic_number": "1",
      "measurement_result": "10.002",
      "accept_reject": "ACCEPT"
    }]
  }'
```

### Create Configuration Baseline

```bash
curl -X POST http://localhost:8009/v1/aerospace/config-baseline \
  -H "X-RegEngine-API-Key: demo-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "assembly_id": "ASSY-1000",
    "assembly_name": "Flight Control Module",
    "serial_number": "FCM-2026-001",
    "manufacturing_date": "2026-01-28T20:00:00Z",
    "baseline_data": [
      {
        "part_number": "PART-001",
        "revision": "B",
        "serial_number": "SN-001",
        "quantity": 1
      },
      {
        "part_number": "PART-002",
        "revision": "A",
        "serial_number": "SN-002",
        "quantity": 2
      }
    ]
  }'
```

### Record NADCAP Heat Treat Evidence

```bash
curl-X POST http://localhost:8009/v1/aerospace/nadcap-evidence \
  -H "X-RegEngine-API-Key: demo-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "process_type": "HEAT_TREAT",
    "part_number": "123-456-789",
    "lot_number": "LOT-2026-01",
    "process_date": "2026-01-28T20:00:00Z",
    "operator_name": "John Doe",
    "equipment_id": "FURNACE-001",
    "process_parameters": {
      "temperature_f": 1850,
      "time_minutes": 240,
      "atmosphere": "Vacuum",
      "quench_medium": "Oil"
    },
    "process_results": {
      "hardness_hrc": 58,
      "pyrometry_offset_f": 2,
      "pass_fail": "PASS"
    },
    "nadcap_certification_number": "NAD-12345",
    "certification_expiry": "2027-01-28T00:00:00Z"
  }'
```

## 🔄 Roadmap

**Current Status**: Phase 1 Complete (Backend buildout)

**Next Steps:**
1. **Phase 2**: Part genealogy graph (Neo4j integration)
2. **Phase 3**: AS9145 APQP integration
3. **Phase 4**: Supplier FAI portal
4. **Phase 5**: Frontend dashboard (`/verticals/aerospace/dashboard/`)

## 📝 Compliance Notes

### FAI Retention
- **Minimum**: Life of part + 1 year (AS9102)
- **Aerospace Standard**: 30+ years for traceability
- **Current**: No auto-deletion (manual archival after retirement)

### Configuration Baseline Use Cases
- **Manufacturing**: Exact BOM for each serial number
- **Field Service**: Identify correct replacement parts
- **Investigations**: Trace defects back to specific components
- **Recalls**: Identify affected serial numbers

### NADCAP Requirements
- **Accreditation**: Must be NADCAP-accredited for special processes
- **Audit Frequency**: Every 12-24 months depending on process
- **Evidence Requirements**: Pyrometry logs, equipment calibration, operator training
- **Retention**: Minimum 5 years, typically part lifetime

## 🛠️ Architecture

```
┌─────────────────────────────────────────────┐
│      Aerospace Compliance Service            │
│                                              │
│  ┌────────────────────────────────────────┐ │
│  │  FastAPI Application (:8009)           │ │
│  │                                        │ │
│  │  • POST /v1/aerospace/fai              │ │
│  │  • GET  /v1/aerospace/fai/:id          │ │
│  │  • PATCH /v1/aerospace/fai/:id/approve │ │
│  │  • POST /v1/aerospace/config-baseline  │ │
│  │  • GET  /v1/aerospace/config-baseline/:id │ │
│  │  • POST /v1/aerospace/nadcap-evidence  │ │
│  │  • GET  /v1/aerospace/dashboard        │ │
│  └────────────────┬───────────────────────┘ │
│                   │                          │
│  ┌────────────────▼───────────────────────┐ │
│  │  SQLAlchemy Models                     │ │
│  │  • FAIReport (AS9102 Forms 1/2/3)      │ │
│  │  • ConfigurationBaseline (30-year)     │ │
│  │  • NADCAPEvidence                      │ │
│  └────────────────┬───────────────────────┘ │
└───────────────────┼──────────────────────────┘
                    │
                    │ PostgreSQL
                    │
      ┌─────────────▼─────────────┐
      │   PostgreSQL Database     │
      │   (regengine_aerospace)   │
      │                           │
      │  • fai_reports            │
      │  • configuration_baselines│
      │  • nadcap_evidence        │
      └───────────────────────────┘
```

## 📚 Related Documentation

- [Vertical Equality Audit](../../../.gemini/antigravity/brain/efd6355a-7c66-41ce-b4ef-1eee328fe32e/vertical_representation_equality_audit.md)
- [Implementation Plan](../../../.gemini/antigravity/brain/efd6355a-7c66-41ce-b4ef-1eee328fe32e/vertical_equality_implementation_plan.md)
- [AS9102 Standard](https://www.sae.org/standards/content/as9102b/)

## 🤝 Contributing

This service follows the RegEngine vertical equality standard. All changes must maintain:
- ≥85% equality score vs. FSMA baseline
- Cryptographic immutability for FAI reports and baselines
- 30-year retention compliance
- Comprehensive API documentation
- Unit test coverage ≥80%
