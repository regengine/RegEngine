# RegEngine Automotive Compliance Service

PPAP (Production Part Approval Process) vault and LPA (Layered Process Audit) tracking for IATF 16949 compliance.

## 🚗 Regulatory Standards

- **IATF 16949:2016** - Automotive Quality Management System
- **AIAG PPAP Manual** - 4th Edition (18 required elements)
- **VDA Volume 2** - German OEM requirements
- **ISO 9001:2015** - Quality Management System foundation

## 🚀 Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export AUTOMOTIVE_DATABASE_URL="postgresql://postgres:postgres@localhost:5432/regengine_automotive"
export AUTOMOTIVE_PORT=8008

# Run service
python -m app.main
```

### Docker

```bash
# Build image
docker build -t regengine/automotive:latest .

# Run container
docker run -p 8008:8008 \
  -e AUTOMOTIVE_DATABASE_URL="postgresql://postgres:postgres@host.docker.internal:5432/regengine_automotive" \
  regengine/automotive:latest
```

## 📡 API Endpoints

### PPAP Vault

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/automotive/ppap` | POST | Initialize PPAP submission |
| `/v1/automotive/ppap/{id}/element` | POST | Upload PPAP element (1-18) |
| `/v1/automotive/ppap/{id}` | GET | Retrieve PPAP with element status |
| `/v1/automotive/ppap/{id}/approve` | PATCH | Update approval status |

### Layered Process Audit (LPA)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/automotive/lpa` | POST | Record LPA audit result |
| `/v1/automotive/dashboard` | GET | Dashboard metrics |

## 🔒 Security

- **API Key Authentication**: Required via `X-RegEngine-API-Key` header
- **Cryptographic Integrity**: SHA-256 hashing for all PPAP elements
- **Version Control**: Automatic versioning on element re-upload

## 📊 Database Schema

### `ppap_submissions`
PPAP submission tracking with OEM approval workflow.

**Key Fields:**
- `part_number` - Supplier part number
- `submission_level` - PPAP level (1-5 per AIAG manual)
- `oem_customer` - Target OEM (Ford, GM, Toyota, etc.)
- `approval_status` - PENDING | APPROVED | REJECTED | INTERIM

### `ppap_elements`
18 PPAP elements with cryptographic tracking.

**18 Required Elements:**
1. Design Records
2. Engineering Change Documents
3. Customer Engineering Approval
4. DFMEA (Design FMEA)
5. Process Flow Diagram
6. PFMEA (Process FMEA)
7. Control Plan
8. MSA (Measurement System Analysis)
9. Dimensional Results
10. Material/Performance Test Results
11. Initial Process Studies
12. Qualified Laboratory Documentation
13. Appearance Approval Report (AAR)
14. Sample Production Parts
15. Master Sample
16. Checking Aids
17. Customer-Specific Requirements
18. Part Submission Warrant (PSW)

**Key Fields:**
- `element_type` - One of the 18 PPAP elements
- `content_hash` - SHA-256 for file integrity
- `version` - Incremental version number

### `lpa_audits`
Layered Process Audit records.

**LPA Layers:**
- `EXECUTIVE` - Strategic process audits
- `MANAGEMENT` - Tactical process verification
- `FRONTLINE` - Operational checks by supervisors

**Key Fields:**
- `layer` - Audit layer
- `result` - PASS | FAIL | NA
- `corrective_action` - Action plan for failures

## 📈 PPAP Submission Levels

| Level | Requirements | Use Case |
|-------|-------------|----------|
| **1** | PSW only | No changes, continued production |
| **2** | PSW + limited data | Minor tooling/process changes |
| **3** | PSW + complete data | New part, major changes, customer request |
| **4** | PSW + data at supplier | Same as Level 3, stored at supplier |
| **5** | PSW + data at designated location | Same as Level 3, stored at customer-specified location |

## 💡 Example Usage

### Create PPAP Submission

```bash
curl -X POST http://localhost:8008/v1/automotive/ppap \
  -H "X-RegEngine-API-Key: demo-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "part_number": "ABC-12345",
    "part_name": "Brake Caliper Assembly",
    "submission_level": 3,
    "oem_customer": "Ford Motor Company",
    "customer_part_number": "F81Z-2552-AA",
    "submission_date": "2026-01-28T20:00:00Z"
  }'
```

**Response:**
```json
{
  "id": 1,
  "part_number": "ABC-12345",
  "submission_level": 3,
  "oem_customer": "Ford Motor Company",
  "approval_status": "PENDING",
  "elements_uploaded": 0,
  "elements_required": 18,
  "created_at": "2026-01-28T20:00:00Z"
}
```

### Upload PPAP Element

```bash
curl -X POST "http://localhost:8008/v1/automotive/ppap/1/element?element_type=CONTROL_PLAN" \
  -H "X-RegEngine-API-Key: demo-key-123" \
  -F "file=@control_plan.pdf"
```

### Record LPA Audit

```bash
curl -X POST http://localhost:8008/v1/automotive/lpa \
  -H "X-RegEngine-API-Key: demo-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "layer": "FRONTLINE",
    "part_number": "ABC-12345",
    "process_step": "Welding Station 3",
    "question": "Are all weld parameters within spec?",
    "result": "PASS",
    "auditor_name": "John Smith"
  }'
```

## 🔄 Roadmap

**Current Status**: Phase 1 Complete (Backend buildout)

**Next Steps:**
1. **Phase 2**: File storage (S3/local) integration
2. **Phase 3**: OEM multi-portal submission automation
3. **Phase 4**: 8D report integration
4. **Phase 5**: Frontend dashboard (`/verticals/automotive/dashboard/`)

## 📝 Compliance Notes

### PPAP Retention
- **Minimum**: Part lifetime + 1 year
- **Recommended**: 10+ years for liability protection

### OEM-Specific Requirements
- **Ford**: Q1 requirements + PPAP Level 3
- **GM**: BIQS system integration
- **Stellantis** (FCA): PPAP Online portal
- **Toyota**: Supplier Submission Checklist
- **Honda**: BP form submission

### LPA Best Practices
- **Frequency**: Daily (frontline), weekly (management), monthly (executive)
- **Failure Response**: Immediate stop and corrective action
- **Trend Analysis**: Track failure patterns by part/process

## 🛠️ Architecture

```
┌─────────────────────────────────────────────┐
│      Automotive Compliance Service           │
│                                              │
│  ┌────────────────────────────────────────┐ │
│  │  FastAPI Application (:8008)           │ │
│  │                                        │ │
│  │  • POST /v1/automotive/ppap            │ │
│  │  • POST /v1/automotive/ppap/:id/element│ │
│  │  • GET  /v1/automotive/ppap/:id        │ │
│  │  • PATCH /v1/automotive/ppap/:id/approve│ │
│  │  • POST /v1/automotive/lpa             │ │
│  │  • GET  /v1/automotive/dashboard       │ │
│  └────────────────┬───────────────────────┘ │
│                   │                          │
│  ┌────────────────▼───────────────────────┐ │
│  │  SQLAlchemy Models                     │ │
│  │  • PPAPSubmission                      │ │
│  │  • PPAPElement (18 types)              │ │
│  │  • LPAAudit                            │ │
│  └────────────────┬───────────────────────┘ │
└───────────────────┼──────────────────────────┘
                    │
                    │ PostgreSQL
                    │
      ┌─────────────▼─────────────┐
      │   PostgreSQL Database     │
      │   (regengine_automotive)  │
      │                           │
      │  • ppap_submissions       │
      │  • ppap_elements          │
      │  • lpa_audits             │
      └───────────────────────────┘
```

## 📚 Related Documentation

- [Vertical Equality Audit](../../../.gemini/antigravity/brain/efd6355a-7c66-41ce-b4ef-1eee328fe32e/vertical_representation_equality_audit.md)
- [Implementation Plan](../../../.gemini/antigravity/brain/efd6355a-7c66-41ce-b4ef-1eee328fe32e/vertical_equality_implementation_plan.md)
- [AIAG PPAP Manual](https://www.aiag.org/quality/automotive-core-tools/ppap)

## 🤝 Contributing

This service follows the RegEngine vertical equality standard. All changes must maintain:
- ≥85% equality score vs. FSMA baseline
- Cryptographic immutability for PPAP elements
- Comprehensive API documentation
- Unit test coverage ≥80%
