# RegEngine Content Ingestion Guide

This guide explains how to ingest regulatory documents and extract provisions using RegEngine's domain-specific extractors.

## Overview

RegEngine supports automated ingestion and extraction of regulatory content from multiple frameworks:

- **NYDFS Part 500**: NY Department of Financial Services cybersecurity requirements
- **DORA**: EU Digital Operational Resilience Act (placeholder)
- **SEC Regulation SCI**: Securities market systems compliance (placeholder)

## Quick Start

### 1. Ingest a Regulatory Document

```bash
# Ingest NYDFS Part 500 from local file
python scripts/ingest_document.py \
  --file docs/regulations/NYDFS_Part500.pdf \
  --jurisdiction US-NY \
  --title "NYDFS Part 500 Cybersecurity Requirements" \
  --document-type REGULATION \
  --effective-date 2017-03-01 \
  --extract \
  --extractor nydfs
```

### 2. Load Demo Data

```bash
# Load complete demo dataset for a tenant
python scripts/demo/load_demo_data.py \
  --tenant-id 550e8400-e29b-41d4-a716-446655440000 \
  --framework nist
```

## Domain-Specific Extractors

### NYDFS Part 500 Extractor

The NYDFS extractor is optimized for New York cybersecurity regulations.

**Features**:
- Section reference detection (§ 500.XX)
- Obligation type classification (MUST, SHOULD, MAY)
- Timeframe extraction (hours, days, annually, quarterly)
- Confidence scoring based on regulatory language patterns

**Example Usage**:
```python
from services.nlp.app.extractors import NYDFSExtractor
from uuid import uuid4

extractor = NYDFSExtractor()

text = """
§ 500.02 Cybersecurity Program. Each Covered Entity shall maintain a
cybersecurity program designed to protect the confidentiality, integrity
and availability of the Covered Entity's Information Systems.
"""

extractions = extractor.extract_obligations(
    text=text,
    document_id=uuid4(),
    tenant_id=uuid4(),
)

for ext in extractions:
    print(f"Provision: {ext.provision_text[:80]}...")
    print(f"Confidence: {ext.confidence_score:.2f}")
    print(f"Thresholds: {ext.thresholds}")
```

**Extracted Information**:
- Provision text
- Section reference (§ 500.XX)
- Obligation type (RECORDKEEPING, REPORTING, CONDUCT, etc.)
- Quantitative thresholds (timeframes, frequencies)
- Confidence score (0.0-1.0)
- Provision hash (SHA-256)

### DORA Extractor (Placeholder)

Placeholder for EU Digital Operational Resilience Act extraction.

**Planned Features**:
- Article and chapter parsing
- ICT risk framework identification
- Third-party provider requirements
- Incident reporting thresholds

### SEC Regulation SCI Extractor (Placeholder)

Placeholder for SEC systems compliance extraction.

**Planned Features**:
- Rule-based parsing (Rule 1000, 1001, etc.)
- Systems capacity requirements
- Change management procedures
- Incident notification timeframes

## Demo Data

The demo data loader creates a complete compliance environment:

### Controls (NIST CSF Example)

- **ID.AM-1**: Physical Devices and Systems Inventory
- **ID.AM-2**: Software Platforms and Applications Inventory
- **ID.RA-1**: Asset Vulnerabilities Identified
- **PR.AC-1**: Identity and Credential Management
- **PR.AC-4**: Access Permissions Management
- **PR.DS-1**: Data-at-Rest Protection
- **DE.CM-1**: Network Monitoring
- **DE.AE-3**: Event Data Aggregation
- **RS.CO-2**: Incident Reporting
- **RC.RP-1**: Recovery Plan Execution

### Products

- **Crypto Trading Platform**: Trading platform with order matching and custody
- **Digital Asset Wallet**: Non-custodial wallet with multi-signature support
- **DeFi Lending Protocol**: Decentralized lending and borrowing protocol

### Frameworks Supported

- **NIST CSF**: Cybersecurity Framework (10 sample controls)
- **SOC 2**: Trust Services Criteria (8 sample controls)
- **ISO 27001**: Information Security Management (8 sample controls)

## Extraction Pipeline

### 1. Document Ingestion

```
Document (PDF/Text) →
  Content Hashing (SHA-256) →
    Text Extraction →
      Storage (S3/Database)
```

### 2. NLP Extraction

```
Document Text →
  Domain-Specific Extractor →
    Provision Identification →
      Obligation Classification →
        Threshold Extraction →
          Confidence Scoring →
            ExtractionPayload
```

### 3. HITL Routing

```
ExtractionPayload →
  Confidence Check →
    High (≥0.85): graph.update topic (auto-approve) →
    Low (<0.85): nlp.needs_review topic (human review)
```

### 4. Graph Population

```
Approved Provisions →
  Graph Consumer →
    Neo4j (reg_global or reg_tenant_<uuid>) →
      Provision Nodes →
        Relationships to Documents
```

## Validation Tests

Run the test suite to validate extractors:

```bash
# Test NYDFS extractor
pytest tests/nlp/test_nydfs_extractor.py -v

# Test all NLP extractors
pytest tests/nlp/ -v
```

**Test Coverage**:
- Cybersecurity program extraction
- CISO requirement detection
- Annual certification requirements
- Incident notification timeframes
- Obligation type classification
- Threshold extraction (days, hours, years)
- Confidence scoring
- Provision hash generation
- Section reference detection

## API Endpoints for Provisions

Once provisions are extracted and stored, query them via API:

```bash
# Get provision by hash
curl -H "X-RegEngine-API-Key: $API_KEY" \
  https://api.regengine.example.com/overlay/provisions/{hash}/overlays

# Get regulatory requirements for a product
curl -H "X-RegEngine-API-Key: $API_KEY" \
  https://api.regengine.example.com/overlay/products/{id}/requirements

# Get compliance gaps
curl -H "X-RegEngine-API-Key: $API_KEY" \
  https://api.regengine.example.com/overlay/products/{id}/compliance-gaps
```

## Confidence Scoring

Confidence scores are calculated based on multiple factors:

**Base Score**: 0.70 (NYDFS content has established patterns)

**Boosters**:
- Strong obligation language ("shall", "must"): +0.15
- Weaker obligation language ("should"): +0.08
- Section reference present: +0.10
- Quantitative thresholds: +0.05 per threshold (max +0.10)

**Penalties**:
- Very short (<10 words) or very long (>100 words): -0.10

**Range**: 0.0 - 1.0

**HITL Threshold**: Extractions with confidence < 0.85 go to human review

## Adding New Extractors

To add a new regulatory framework:

1. **Create Extractor Class**:
   ```python
   # services/nlp/app/extractors/my_framework_extractor.py
   from services.nlp.app.extractors import NYDFSExtractor

   class MyFrameworkExtractor:
       JURISDICTION = "MY-JURISDICTION"
       FRAMEWORK = "My Framework"

       def extract_obligations(self, text, document_id, tenant_id):
           # Implementation here
           pass
   ```

2. **Add to Module**:
   ```python
   # services/nlp/app/extractors/__init__.py
   from .my_framework_extractor import MyFrameworkExtractor

   __all__ = [..., "MyFrameworkExtractor"]
   ```

3. **Register in Ingestion Script**:
   ```python
   # scripts/ingest_document.py
   EXTRACTORS = {
       ...
       "my_framework": MyFrameworkExtractor,
   }
   ```

4. **Create Tests**:
   ```python
   # tests/nlp/test_my_framework_extractor.py
   class TestMyFrameworkExtractor:
       def test_extraction(self):
           # Test cases
           pass
   ```

## Best Practices

1. **Start with High-Quality Sources**: Use official regulatory publications (EUR-Lex, SEC.gov, etc.)

2. **Validate Extractions**: Always review initial extractions to tune confidence thresholds

3. **Use Domain Extractors**: Domain-specific extractors significantly improve accuracy

4. **Monitor Confidence Scores**: Track low-confidence rates to identify areas for improvement

5. **Leverage HITL**: Human review is essential for high-stakes compliance work

6. **Test Thoroughly**: Use comprehensive test suites to validate extraction quality

## Troubleshooting

### Low Extraction Count

**Problem**: Extractor returns very few provisions

**Solutions**:
- Check if document text extraction is working (PDF parsing)
- Review extractor patterns - may need tuning for specific document format
- Lower confidence threshold temporarily to see what's being filtered

### Low Confidence Scores

**Problem**: All extractions have low confidence

**Solutions**:
- Review extraction patterns - may not match regulatory language
- Check if section references are being detected
- Tune confidence scoring algorithm

### Missing Thresholds

**Problem**: Timeframes and quantitative requirements not extracted

**Solutions**:
- Add more threshold patterns to extractor
- Check if threshold text format matches patterns
- Review regex patterns for edge cases

## Support

For questions about content ingestion:

1. Review this documentation
2. Check test cases in `tests/nlp/`
3. Review extractor source code in `services/nlp/app/extractors/`
4. File an issue on GitHub

---

**Version**: 1.0
**Last Updated**: 2025-11-22
