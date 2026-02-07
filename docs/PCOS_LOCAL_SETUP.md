# PCOS Local Development Setup

## Prerequisites

- Docker & Docker Compose
- Node.js 18+ (for frontend)
- Python 3.11+ (for backend development)

## Quick Start

### 1. Start Infrastructure

```bash
# From project root
docker compose up -d postgres redis
```

### 2. Run Migrations

```bash
cd services/admin
flyway -configFiles=flyway.conf migrate
```

### 3. Start Backend API

```bash
cd services/admin
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 4. Start Frontend

```bash
cd frontend
npm install
npm run dev
```

Access the app at `http://localhost:5173`

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection | `postgresql://regengine:regengine@localhost:5432/regengine_admin` |
| `REDIS_URL` | Redis connection | `redis://localhost:6379/0` |
| `AUTH_SECRET_KEY` | JWT signing key | *(required)* |

---

## PCOS API Endpoints

Base URL: `http://localhost:8000/pcos`

See [PCOS_API_REFERENCE.md](./PCOS_API_REFERENCE.md) for full documentation.

**Health check:**
```bash
curl http://localhost:8000/pcos/health
```

---

## Running Tests

```bash
cd services/admin
pytest tests/test_pcos_api_endpoints.py -v
```

---

## Frontend Components

Import PCOS components:

```tsx
import {
  ComplianceDashboard,
  BudgetAnalysis,
  PaperworkStatusGrid,
  AuditPackDownload,
} from '@/components/pcos';
```

See component source at `frontend/src/components/pcos/`
