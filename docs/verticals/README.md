# RegEngine - Multi-Vertical Compliance Platform

**Developer-first compliance APIs for regulated industries**

---

## Overview

RegEngine provides compliance infrastructure as code across four regulated verticals:

1. **[Energy](./energy/)** - Grid compliance (NERC CIP-013)
2. **[Finance](./finance/)** - Financial reporting (SEC, SOX 404)
3. **[Technology](./technology/)** - Security compliance (SOC 2, ISO 27001)
4. **[Nuclear](./nuclear/)** - Nuclear regulatory (10 CFR / NRC)

**Common Architecture**: All verticals share the same compliance core:
- Immutable evidence preservation
- Cryptographic verification
- Chain-of-custody tracking
- Audit trail generation
- Legal hold support

---

## Quick Links

### Documentation
- [Energy Vertical](./energy/README.md)
- [Finance Vertical](./finance/README.md)
- [Technology Vertical](./technology/README.md)
- [Nuclear Vertical](./nuclear/README.md)

### Developer Pages
- [Energy API](/verticals/energy)
- [Finance API](/verticals/finance)
- [Technology API](/verticals/technology)
- [Nuclear API](/verticals/nuclear)

### General Documentation
- [Architecture](../architecture/README.md)
- [Compliance](../compliance/RTM.md)
- [Operations](../OPERATIONS.md)

---

## Vertical Comparison

| Feature | Energy | Finance | Technology | Nuclear |
|---------|--------|---------|------------|---------|
| **Framework** | NERC CIP-013 | SEC, SOX 404 | SOC 2, ISO 27001 | 10 CFR (NRC) |
| **Primary Use** | Grid cybersecurity | Filing verification | Control verification | Evidence preservation |
| **Retention** | Utility-defined | 7 years | Audit cycle | License life + 3 years |
| **Inspection** | NERC audits | SEC review | SOC 2 audit | NRC inspection |
| **Criticality** | High | High | High | Critical |

---

## Getting Started

### 1. Choose Your Vertical
Navigate to the vertical that matches your industry:
```bash
# Energy
cd docs/verticals/energy

# Finance  
cd docs/verticals/finance

# Technology
cd docs/verticals/technology

# Nuclear
cd docs/verticals/nuclear
```

### 2. Read Vertical README
Each vertical has a dedicated README with:
- Regulatory framework overview
- Architecture details
- API documentation
- Getting started guide

### 3. Get API Key
Visit [/api-keys](/api-keys) to generate credentials for your vertical.

### 4. Install SDK
```bash
# Energy
npm install @regengine/energy-sdk

# Finance
npm install @regengine/finance-sdk

# Technology
npm install @regengine/security-sdk

# Nuclear
npm install @regengine/nuclear-sdk
```

---

## Shared Infrastructure

All verticals run on the same compliance core:

### Database Layer
- PostgreSQL with immutability triggers
- Chain integrity constraints
- Retention policy enforcement

### API Layer
- FastAPI (Python)
- RESTful endpoints
- OpenAPI documentation

### Frontend
- Next.js 14
- TypeScript
- Tailwind CSS

### Authentication
- OAuth 2.0 / SAML
- Service account support
- Role-based access control

---

## Development

### Adding a New Vertical

1. **Create Documentation**:
   ```bash
   mkdir -p docs/verticals/[name]
   touch docs/verticals/[name]/README.md
   ```

2. **Create Frontend Page**:
   ```bash
   mkdir -p frontend/src/app/verticals/[name]
   touch frontend/src/app/verticals/[name]/page.tsx
   ```

3. **Create Backend Module**:
   ```bash
   mkdir -p services/admin/app/verticals/[name]
   touch services/admin/app/verticals/[name]/__init__.py
   ```

4. **Document Regulatory Framework**:
   - Create compliance matrix
   - Map regulations to features
   - Define retention requirements
   - Establish inspection procedures

---

## Compliance Alignment

| Vertical | Primary Regulations | Documentation |
|----------|-------------------|---------------|
| **Energy** | NERC CIP-013-1 | [Energy Docs](./energy/) |
| **Finance** | SEC 17 CFR, SOX 404 | [Finance Docs](./finance/) |
| **Technology** | SOC 2, ISO 27001 | [Technology Docs](./technology/) |
| **Nuclear** | 10 CFR 50/73/72 | [Nuclear Docs](./nuclear/) - [CFR Matrix](./nuclear/cfr_traceability_matrix.md) |

---

## Contributing

When adding features to a vertical:

1. **Understand Regulatory Context**: Read the vertical's compliance docs first
2. **Preserve Core Guarantees**: Immutability, attribution, retention
3. **Document CFR/Regulatory Alignment**: Map features to specific requirements
4. **Test Inspection Scenarios**: Verify auditor workflows

---

## Commercial Positioning

Each vertical has approved claims for external communication:

- **Energy**: [Approved Claims](./energy/approved_claims.md) (TBD)
- **Finance**: [Approved Claims](./finance/approved_claims.md) (TBD)
- **Technology**: [Approved Claims](./technology/approved_claims.md) (TBD)
- **Nuclear**: [Approved Claims](./nuclear/approved_claims.md)

**General Positioning**:
> "RegEngine provides compliance infrastructure for regulated industries. We preserve evidence immutably, support inspection and discovery, and help organizations meet recordkeeping obligations—but we do not ensure safety, guarantee compliance, or replace programs."

---

## Support

- **Documentation**: [docs.regengine.co](https://docs.regengine.co)
- **GitHub**: [github.com/regengine](https://github.com/regengine)
- **Contact**: support@regengine.co

---

**Last Updated**: 2026-01-25  
**Version**: 1.0  
**Verticals**: 4 (Energy, Finance, Technology, Nuclear)
