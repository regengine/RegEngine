# RegEngine Demo Dataset

This directory contains sample regulatory documents and scripts to demonstrate RegEngine's capabilities.

## Dataset Overview

The demo dataset includes regulatory documents from three jurisdictions:
- **United States (SEC)** - Securities and Exchange Commission regulations
- **European Union (MiFID)** - Markets in Financial Instruments Directive
- **United Kingdom (FCA)** - Financial Conduct Authority rules

## Contents

- `documents/` - Sample regulatory documents in JSON format
- `load_demo_data.sh` - Script to load demo data into RegEngine
- `demo_queries.sh` - Example queries demonstrating RegEngine capabilities

## Quick Start

### 1. Ensure RegEngine is running

```bash
# For local development
docker-compose up -d

# Wait for services to be healthy
bash scripts/init-demo-keys.sh
```

### 2. Load demo data

```bash
cd demo
bash load_demo_data.sh
```

### 3. Run demo queries

```bash
bash demo_queries.sh
```

## Demo Scenarios

### Scenario 1: Regulatory Arbitrage Detection

Identify threshold differences between US and EU capital requirements.

```bash
curl "http://localhost:8300/opportunities/arbitrage?j1=US&j2=EU&concept=capital+adequacy" \
  -H "X-RegEngine-API-Key: $API_KEY"
```

### Scenario 2: Gap Analysis

Find regulatory concepts present in EU but not in US regulations.

```bash
curl "http://localhost:8300/opportunities/gaps?j1=EU&j2=US" \
  -H "X-RegEngine-API-Key: $API_KEY"
```

### Scenario 3: Cross-Border Compliance

Identify requirements that differ across all three jurisdictions.

```bash
# Query provided in demo_queries.sh
bash demo_queries.sh compliance-comparison
```

## Document Structure

Each document follows this structure:

```json
{
  "id": "sec-capital-req-2024",
  "title": "SEC Capital Adequacy Requirements",
  "jurisdiction": "US",
  "effective_date": "2024-01-01",
  "source_url": "https://example.com/regulation.pdf",
  "body": "Full text of the regulation..."
}
```

## Expected Outputs

After loading the demo dataset, you should be able to:

1. **Detect 15+ obligation extractions** across documents
2. **Identify 8+ threshold differences** between jurisdictions
3. **Find 5+ regulatory gaps** (concepts in one jurisdiction but not others)
4. **Visualize regulatory lineage** with source citations

## Extending the Dataset

To add your own regulations:

1. Create a JSON file in `documents/` following the template
2. Run `bash load_demo_data.sh` to ingest
3. Wait 30-60 seconds for NLP processing
4. Query via the Opportunity API

## Data Sources

Demo documents are simplified summaries based on publicly available regulations:
- US SEC: [sec.gov](https://www.sec.gov/rules)
- EU MiFID: [eur-lex.europa.eu](https://eur-lex.europa.eu)
- UK FCA: [fca.org.uk/handbook](https://www.handbook.fca.org.uk)

**Note**: These are demo examples only, not legal documents. For production use, ingest official regulatory sources.
