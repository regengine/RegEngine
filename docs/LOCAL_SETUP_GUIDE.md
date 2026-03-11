# 🚀 RegEngine Local Setup Guide

Complete step-by-step guide to run RegEngine locally and test the entire product flow.

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [Start Backend Services](#start-backend-services)
4. [Set Up CLI Tool](#set-up-cli-tool)
5. [Create a Demo Tenant](#create-a-demo-tenant)
6. [Start Frontend Dashboard](#start-frontend-dashboard)
7. [Test the Complete Product Flow](#test-the-complete-product-flow)
8. [Run FSMA 204 Demo](#run-fsma-204-demo)
9. [Access Points & UIs](#access-points--uis)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before starting, ensure you have the following installed:

### Required Software

- **Docker Desktop** (or Docker Engine + Docker Compose)
  - Version: 20.10+ recommended
  - [Install Docker](https://docs.docker.com/get-docker/)

- **Python 3.11+**
  - Check: `python3 --version`
  - [Install Python](https://www.python.org/downloads/)

- **Node.js 18+** (for Frontend)
  - Check: `node --version`
  - [Install Node.js](https://nodejs.org/)

- **Make** (optional, for convenience commands)
  - macOS/Linux: Usually pre-installed
  - Windows: Install via [Chocolatey](https://chocolatey.org/) or use direct commands

### System Requirements

- **RAM**: 8GB minimum, 16GB recommended
- **Disk Space**: 10GB free space (for Docker images and volumes)
- **Network**: Internet connection for downloading images and models

---

## Initial Setup

### Step 1: Clone the Repository

```bash
# If you haven't already
git clone https://github.com/PetrefiedThunder/RegEngine.git
cd RegEngine
```

### Step 2: Configure Environment Variables

```bash
# Copy the example environment file
cp .env.example .env
```

### Step 3: Generate Required Secrets

Open `.env` in your text editor and set the following **REQUIRED** secrets:

```bash
# Generate Neo4j password
openssl rand -base64 32
# Copy the output and paste it as NEO4J_PASSWORD in .env

# Generate Admin Master Key
openssl rand -hex 32
# Copy the output and paste it as ADMIN_MASTER_KEY in .env
```

Your `.env` file should look like this:

```bash
# REQUIRED SECRETS
NEO4J_PASSWORD=your_generated_password_here
ADMIN_MASTER_KEY=your_generated_master_key_here

# AWS Credentials (for LocalStack - local development only)
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test

# Environment
REGENGINE_ENV=development
```

> **Note**: The AWS credentials "test/test" are ONLY for LocalStack (local S3 mock). Never use these in production.

---

## Start Backend Services

### Step 1: Start All Services

```bash
# Using Make (recommended)
make up

# OR using docker-compose directly
docker-compose up --build -d
```

This will start all backend services:
- **PostgreSQL** (port 5432) - Relational database with RLS
- **Redis** (port 6379) - Caching and rate limiting
- **Neo4j** (ports 7474, 7687) - Knowledge graph database
- **Redpanda** (port 9092) - Event streaming (Kafka-compatible)
- **LocalStack** (port 4566) - Local AWS S3 mock
- **Ollama** (port 11434) - Local LLM inference
- **Admin API** (port 8400) - Tenant management
- **Ingestion Service** (port 8000) - Document ingestion
- **NLP Service** (port 8100) - ML extraction
- **Graph Service** (port 8200) - Graph operations
- **Opportunity API** (port 8300) - Regulatory analysis
- **Compliance API** (port 8500) - Compliance evaluation
- **Kafka UI** (port 8080) - Stream monitoring

### Step 2: Wait for Services to Initialize

```bash
# Check service status
docker-compose ps

# Watch logs (optional)
docker-compose logs -f
```

**Expected startup time**: 30-90 seconds on first run (longer if pulling images)

### Step 3: Verify Services Are Healthy

```bash
# Check Admin API
curl http://localhost:8400/health

# Check Ingestion Service
curl http://localhost:8000/health

# Check NLP Service
curl http://localhost:8100/health

# Check Graph Service
curl http://localhost:8200/health
```

All should return `{"status":"ok"}` or similar.

### Step 4: Initialize LocalStack S3 Buckets

```bash
make init-local

# OR manually
aws --endpoint-url=http://localhost:4566 s3 mb s3://reg-engine-raw-data-dev
aws --endpoint-url=http://localhost:4566 s3 mb s3://reg-engine-processed-data-dev
```

---

## Set Up CLI Tool

The `regctl` CLI tool is used for tenant management and system operations.

### Step 1: Install CLI Dependencies

```bash
# From the repository root
pip install -r scripts/regctl/requirements.txt
```

### Step 2: Verify CLI Installation

```bash
python scripts/regctl/tenant.py --help
```

You should see the CLI help menu with available commands.

---

## Create a Demo Tenant

Every API request requires an API key scoped to a tenant. Let's create a demo tenant with sample data.

### Method 1: Quick Demo Script (Recommended)

```bash
./scripts/demo/quick_demo.sh
```

This will:
- Verify services are running
- Create a demo FSMA tenant
- Load sample traceability data
- Display your API key and tenant ID
- Save credentials to `.demo_env`

### Method 2: Manual CLI Creation

```bash
# Create demo FSMA tenant
python scripts/regctl/tenant.py create "Demo Foods" --demo-mode
```

### Save Your Credentials

After creation, you'll see output like:

```
✅ Tenant created successfully!

Tenant ID: 550e8400-e29b-41d4-a716-446655440000
API Key: rge_1234567890abcdef1234567890abcdef
```

**Save these values!** You'll need them for API calls and frontend access.

### Load Credentials (if using quick_demo.sh)

```bash
source .demo_env
echo $REGENGINE_API_KEY
echo $REGENGINE_TENANT_ID
```

---

## Start Frontend Dashboard

The frontend provides a modern React-based UI for compliance officers and administrators.

### Step 1: Install Frontend Dependencies

```bash
cd frontend
npm ci  # Use 'ci' for clean install based on package-lock.json
```

### Step 2: Start Development Server

```bash
npm run dev
```

The dashboard will be available at **http://localhost:3000**

### Step 3: Access Dashboard with Your Tenant

Open your browser and navigate to:

```
http://localhost:3000/dashboard?tenant=YOUR_TENANT_ID
```

Replace `YOUR_TENANT_ID` with the tenant ID from Step 5.

---

## Test the Complete Product Flow

Now let's test the entire RegEngine pipeline: **Ingestion → NLP Extraction → Graph Storage → API Query**

### Step 1: Prepare Your API Key

```bash
# Set your API key as an environment variable
export API_KEY="rge_your_api_key_here"

# OR load from .demo_env if you used quick_demo.sh
source .demo_env
export API_KEY=$REGENGINE_API_KEY
```

### Step 2: Ingest a Document

```bash
# Ingest a sample regulatory document URL
curl -X POST http://localhost:8000/ingest/url \
  -H "Content-Type: application/json" \
  -H "X-RegEngine-API-Key: $API_KEY" \
  -d '{
    "url": "https://www.federalregister.gov/api/v1/documents/2023-12345.json",
    "source_system": "Federal Register"
  }'
```

**Expected Response:**
```json
{
  "doc_id": "uuid-here",
  "status": "processing",
  "message": "Document accepted for ingestion"
}
```

### Step 3: Monitor Kafka Events

```bash
# Watch the normalized events topic
make consume-normalized

# OR manually
docker exec -it $(docker ps -qf name=redpanda) rpk topic consume ingest.normalized -n 1
```

You should see a normalized text event with the document content.

### Step 4: Check Kafka UI

Open **http://localhost:8080** in your browser to:
- View topics: `ingest.normalized`, `nlp.extracted`, `graph.update`
- Inspect messages
- Monitor consumer lag

### Step 5: Query the Knowledge Graph

After a few seconds (allow time for NLP processing), query the graph:

```bash
# List all tenant controls
curl -H "X-RegEngine-API-Key: $API_KEY" \
  http://localhost:8000/overlay/controls | jq

# List tenant products
curl -H "X-RegEngine-API-Key: $API_KEY" \
  http://localhost:8000/overlay/products | jq

# Get compliance gaps
curl -H "X-RegEngine-API-Key: $API_KEY" \
  http://localhost:8300/gaps | jq
```

### Step 6: Explore Neo4j Browser

1. Open **http://localhost:7474** in your browser
2. Login with:
   - Username: `neo4j`
   - Password: (your `NEO4J_PASSWORD` from `.env`)
3. Run Cypher queries:

```cypher
// View all tenant data
MATCH (n) RETURN n LIMIT 25;

// View controls
MATCH (c:Control) RETURN c LIMIT 10;

// View relationships
MATCH (c:Control)-[r]->(p:Product) RETURN c, r, p;
```

---

## Run FSMA 204 Demo

RegEngine includes a complete FDA Food Safety Modernization Act (FSMA) 204 compliance module for food supply chain traceability.

### Step 1: Run the Mock Recall Demo

```bash
./scripts/demo/fsma_mock_recall.sh
```

This demonstrates:
- **Forward tracing** (find all downstream products from a contaminated lot)
- **Backward tracing** (find all upstream suppliers)
- **FDA-compliant CSV export** (24-hour recall requirement)
- **Contact list generation** (notify affected facilities)

### Step 2: Test FSMA API Endpoints

```bash
# Validate a GTIN (Global Trade Item Number)
curl -X POST http://localhost:8200/v1/fsma/validate/gtin \
  -H "Content-Type: application/json" \
  -H "X-RegEngine-API-Key: $API_KEY" \
  -d '{
    "gtin": "01234567890128"
  }' | jq

# Forward trace (find downstream customers)
curl -H "X-RegEngine-API-Key: $API_KEY" \
  http://localhost:8200/v1/fsma/trace/forward/SV-20240115-001 | jq

# Backward trace (find upstream suppliers)
curl -H "X-RegEngine-API-Key: $API_KEY" \
  http://localhost:8200/v1/fsma/trace/backward/FC-20240116-A | jq

# Export FDA-compliant CSV
curl -H "X-RegEngine-API-Key: $API_KEY" \
  http://localhost:8200/v1/fsma/export/trace/SV-20240115-001
```

### Step 3: Review Generated Reports

Check the `demo_exports/` directory for generated CSV files:

```bash
ls -lh demo_exports/
cat demo_exports/fsma_recall_SV-20240115-001_*.csv
```

---

## Access Points & UIs

Here's a summary of all available endpoints and UIs:

### Backend APIs

| Service | URL | Documentation |
|---------|-----|---------------|
| **Admin API** | http://localhost:8400 | http://localhost:8400/docs |
| **Ingestion API** | http://localhost:8000 | http://localhost:8000/docs |
| **NLP Service** | http://localhost:8100 | http://localhost:8100/docs |
| **Graph Service** | http://localhost:8200 | http://localhost:8200/docs |
| **Opportunity API** | http://localhost:8300 | http://localhost:8300/docs |
| **Compliance API** | http://localhost:8500 | http://localhost:8500/docs |

### Frontend & UIs

| UI | URL | Purpose |
|----|-----|---------|
| **Frontend Dashboard** | http://localhost:3000 | Main React dashboard |
| **Neo4j Browser** | http://localhost:7474 | Knowledge graph explorer |
| **Kafka UI** | http://localhost:8080 | Event stream monitoring |

### Database Connections

| Database | Connection String |
|----------|-------------------|
| **PostgreSQL** | `postgresql://regengine:regengine@localhost:5432/regengine` |
| **Redis** | `redis://localhost:6379/0` |
| **Neo4j** | `bolt://localhost:7687` (user: `neo4j`, password: from `.env`) |

---

## Troubleshooting

### Services Won't Start

**Problem**: Docker services fail to start or are unhealthy

**Solutions**:

```bash
# Check Docker is running
docker ps

# View service logs
docker-compose logs -f admin-api
docker-compose logs -f ingestion-service

# Check environment variables are set
cat .env | grep NEO4J_PASSWORD
cat .env | grep ADMIN_MASTER_KEY

# Restart services
docker-compose down -v  # Remove volumes
docker-compose up --build -d
```

### "Missing Required Secret" Error

**Problem**: Docker Compose fails with `NEO4J_PASSWORD must be set` or similar

**Solution**:

1. Edit `.env` file
2. Generate secrets as described in [Initial Setup](#step-3-generate-required-secrets)
3. Save the file
4. Restart services: `docker-compose up -d`

### Ollama Model Not Downloading

**Problem**: NLP service fails because Llama3 model isn't available

**Solution**:

```bash
# Manually pull the model
docker exec -it $(docker ps -qf name=ollama) ollama pull llama3:8b

# Wait for download (this may take 5-10 minutes)

# Restart NLP service
docker-compose restart nlp-service
```

### Frontend Build Errors

**Problem**: `npm ci` or `npm run dev` fails

**Solutions**:

```bash
# Clear npm cache
cd frontend
rm -rf node_modules package-lock.json
npm cache clean --force

# Reinstall
npm install
npm run dev
```

### API Returns 401 Unauthorized

**Problem**: API calls return `401 Unauthorized` error

**Solutions**:

1. **Verify API key format**: Should start with `rge_`
2. **Check header**: Use `X-RegEngine-API-Key` (not `Authorization`)
3. **List your tenants**: `python scripts/regctl/tenant.py list`
4. **Create new API key**: Recreate tenant or manually generate

### Neo4j Connection Refused

**Problem**: Graph service can't connect to Neo4j

**Solutions**:

```bash
# Check Neo4j is running
docker ps | grep neo4j

# Check Neo4j logs
docker-compose logs neo4j

# Verify password in .env matches
docker exec -it $(docker ps -qf name=neo4j) cypher-shell -u neo4j -p YOUR_PASSWORD "RETURN 1;"

# Restart Neo4j
docker-compose restart neo4j
```

### Out of Disk Space

**Problem**: Docker runs out of disk space

**Solutions**:

```bash
# Remove unused Docker resources
docker system prune -a --volumes

# Check disk usage
docker system df

# Remove RegEngine volumes (WARNING: deletes all data)
docker-compose down -v
```

### Kafka Topics Not Created

**Problem**: Events aren't flowing through the system

**Solutions**:

```bash
# Check Redpanda is healthy
docker-compose logs redpanda

# List topics
docker exec -it $(docker ps -qf name=redpanda) rpk topic list

# Manually create topics
docker exec -it $(docker ps -qf name=redpanda) rpk topic create ingest.normalized
docker exec -it $(docker ps -qf name=redpanda) rpk topic create nlp.extracted
docker exec -it $(docker ps -qf name=redpanda) rpk topic create graph.update
```

### Frontend Can't Connect to Backend

**Problem**: Frontend shows "Network Error" or "Failed to fetch"

**Solutions**:

1. **Check CORS**: Ensure backend allows `localhost:3000`
2. **Verify API is running**: `curl http://localhost:8000/health`
3. **Check frontend env**: Look for `NEXT_PUBLIC_API_URL` in frontend config
4. **Browser console**: Open DevTools → Console for detailed errors

---

## Next Steps

Now that you have RegEngine running locally:

1. **Explore the API Documentation**
   - Visit http://localhost:8000/docs (Swagger UI)
   - Try the interactive API explorer

2. **Test Different Frameworks**
   - Create tenants with different control frameworks (NIST, SOC2, ISO27001)
   - Compare the data models

3. **Ingest Real Documents**
   - Try PDF documents
   - Test different source systems

4. **Build Custom Queries**
   - Learn Cypher (Neo4j query language)
   - Create compliance reports

5. **Develop New Features**
   - Add custom extractors
   - Implement new API endpoints
   - Extend the frontend

---

## Quick Reference Commands

```bash
# Start everything
make up

# Stop everything
make down

# View logs
docker-compose logs -f [service-name]

# Restart a service
docker-compose restart [service-name]

# Create tenant
python scripts/regctl/tenant.py create "Company Name" --demo-mode

# List tenants
python scripts/regctl/tenant.py list

# Test ingestion
make smoke-ingest

# Format code
make fmt

# Run tests
make pytest
```

---

## Support & Documentation

- **Project Repository**: https://github.com/PetrefiedThunder/RegEngine
- **Product Roadmap**: [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)
- **Deployment Guide**: [DEPLOYMENT.md](DEPLOYMENT.md)
- **API Authentication**: [AUTHENTICATION.md](AUTHENTICATION.md)
- **FSMA 204 Spec**: [docs/specs/FSMA_204_MVP_SPEC.md](docs/specs/FSMA_204_MVP_SPEC.md)

---

**Happy Testing! 🎉**
