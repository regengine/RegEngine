# RegEngine Beta Tester Guide

Welcome to the RegEngine beta program! This guide explains the platform architecture and how to get started.

---

## 🎯 What is RegEngine?

RegEngine is a **regulatory intelligence platform** that helps organizations stay compliant with complex regulations (starting with FSMA 204 food traceability). It automatically:

1. **Ingests** regulatory documents from official sources
2. **Extracts** requirements, obligations, and thresholds using AI
3. **Maps** relationships in a knowledge graph
4. **Monitors** your compliance posture in real-time
5. **Alerts** you when action is needed

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         YOUR BROWSER / APP                              │
│                    http://localhost:3000                                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           NEXT.JS FRONTEND                              │
│  Dashboard │ Compliance Status │ Alerts │ Review Queue │ Settings      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌───────────┐   ┌───────────┐   ┌───────────┐
            │ Admin API │   │Compliance │   │  Graph    │
            │  :8400    │   │   API     │   │   API     │
            │           │   │  :8500    │   │  :8200    │
            └───────────┘   └───────────┘   └───────────┘
                    │               │               │
                    └───────────────┴───────────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                ▼                   ▼                   ▼
        ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
        │  PostgreSQL  │   │    Neo4j     │   │   Redpanda   │
        │  (Tenants,   │   │ (Knowledge   │   │   (Events)   │
        │   Snapshots) │   │   Graph)     │   │              │
        └──────────────┘   └──────────────┘   └──────────────┘
```

---

## 🔑 Key Concepts

### Multi-Tenancy
Each organization is a **tenant** with isolated data. You'll receive:
- A **Tenant ID** (UUID)
- An **API Key** (starts with `rge_`)

### Compliance Snapshots
Point-in-time captures of your compliance status, cryptographically hashed for audit defense.

### Human-in-the-Loop Review
AI extractions below 85% confidence are flagged for human review before affecting your compliance score.

---

## 🚀 Quick Start

### 1. Access the Dashboard
```
http://localhost:3000
```

### 2. Select Your Tenant
Use the tenant switcher in the top-right corner.

### 3. Check Compliance Status
Navigate to **Compliance** to see your current posture.

### 4. Review Flagged Items
Go to **Review Queue** to approve/reject AI extractions.

---

## 🔌 API Access

### Base URLs

| Service | URL | Purpose |
|---------|-----|---------|
| Admin API | `http://localhost:8400` | Keys, tenants, review |
| Compliance API | `http://localhost:8500` | Checklists, validation |
| Graph API | `http://localhost:8200` | FSMA labels, tracing |
| Ingestion API | `http://localhost:8002` | Document processing |

### Authentication

Include your API key in requests:
```bash
curl -H "X-RegEngine-API-Key: rge_your_key" \
     http://localhost:8400/v1/admin/keys
```

### Example: Check Health
```bash
curl http://localhost:8400/health
# {"status": "healthy", "version": "1.0.0"}
```

### Example: List Review Items
```bash
curl -H "X-RegEngine-API-Key: YOUR_KEY" \
     "http://localhost:8400/v1/admin/review/flagged-extractions?status=PENDING"
```

---

## 📊 Data Flow

```
1. Document URL submitted
         │
         ▼
2. Ingestion Service fetches & normalizes
         │
         ▼
3. NLP Service extracts entities + obligations
         │
         ▼
4. Confidence Check
         │
    ┌────┴────┐
    ▼         ▼
≥ 85%       < 85%
    │         │
    ▼         ▼
5a. Auto    5b. Review
    Approved     Queue
    │         │
    └────┬────┘
         ▼
6. Graph Service updates knowledge graph
         │
         ▼
7. Compliance status recalculated
         │
         ▼
8. Alerts triggered if thresholds crossed
```

---

## 🛡️ Security Model

| Feature | Implementation |
|---------|----------------|
| Tenant Isolation | PostgreSQL Row-Level Security |
| API Authentication | API Keys (tenant-scoped) |
| Data Integrity | SHA-256 content hashing |
| Audit Trail | Structured logging with event types |

---

## 🐛 Reporting Issues

Found a bug? Please include:
1. **Steps to reproduce**
2. **Expected vs actual behavior**
3. **API response** (if applicable)
4. **Browser console errors** (for UI issues)

---

## 📚 Additional Resources

- **API Reference**: [http://localhost:3000/docs/api](http://localhost:3000/docs/api)
- **OpenAPI Specs**: `docs/openapi/` directory
- **Developer Portal**: [http://localhost:3000/docs](http://localhost:3000/docs)

---

*Thank you for being a beta tester! Your feedback shapes the product.* 🙏
