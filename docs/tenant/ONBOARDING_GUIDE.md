# RegEngine Tenant Onboarding Guide

Welcome to RegEngine! This guide will help you get started with RegEngine's regulatory compliance platform.

## Table of Contents

1. [Overview](#overview)
2. [Getting Your API Key](#getting-your-api-key)
3. [Quick Start](#quick-start)
4. [Core Concepts](#core-concepts)
5. [Step-by-Step Tutorial](#step-by-step-tutorial)
6. [API Reference](#api-reference)
7. [Best Practices](#best-practices)
8. [Support](#support)

## Overview

RegEngine is a multi-tenant regulatory intelligence platform that helps you:

- **Define Internal Controls**: Map your compliance frameworks (NIST CSF, SOC2, ISO27001, etc.)
- **Track Products**: Manage products requiring regulatory compliance
- **Map to Regulations**: Link controls to specific regulatory provisions
- **Identify Gaps**: Discover unmapped compliance requirements
- **Maintain Audit Trail**: All actions are logged for compliance

## Getting Your API Key

Your administrator will provide you with an API key. This key:

- Is unique to your organization (tenant)
- Provides automatic data isolation
- Should be kept secret and secure
- Can be revoked if compromised

**API Key Format**: `rge_<random_string>`

**Important**: Never commit API keys to version control or share them publicly.

## Quick Start

### 1. Test Your API Key

```bash
curl -X GET "https://api.regengine.example.com/overlay/controls" \
  -H "X-RegEngine-API-Key: your_api_key_here"
```

**Expected Response**:
```json
{
  "controls": [],
  "count": 0
}
```

### 2. Create Your First Control

```bash
curl -X POST "https://api.regengine.example.com/overlay/controls" \
  -H "X-RegEngine-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "control_id": "AC-001",
    "title": "Access Control Policy",
    "description": "Comprehensive access control policy for all systems",
    "framework": "NIST CSF"
  }'
```

**Expected Response**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_id": "your-tenant-id",
  "control_id": "AC-001",
  "title": "Access Control Policy",
  "description": "Comprehensive access control policy for all systems",
  "framework": "NIST CSF",
  "created_at": "2025-11-22T12:00:00Z"
}
```

### 3. Create a Product

```bash
curl -X POST "https://api.regengine.example.com/overlay/products" \
  -H "X-RegEngine-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "product_name": "Crypto Trading Platform",
    "description": "Institutional cryptocurrency trading and custody",
    "product_type": "TRADING",
    "jurisdictions": ["US", "EU", "UK"]
  }'
```

## Core Concepts

### Tenant Controls

**Tenant Controls** represent your internal compliance controls. They can be from any framework:

- **NIST CSF**: Cybersecurity Framework controls
- **SOC2**: Service Organization Controls
- **ISO27001**: Information security controls
- **GDPR**: Data protection controls
- **Custom**: Your organization's internal controls

**Example**:
```json
{
  "control_id": "DM-042",
  "title": "Data Minimization",
  "description": "Minimize personal data collection and retention",
  "framework": "GDPR"
}
```

### Customer Products

**Customer Products** are the products/services your organization offers that require compliance:

- Trading platforms
- Lending services
- Custody solutions
- Payment processors
- etc.

Each product tracks which jurisdictions it operates in.

### Control Mappings

**Control Mappings** link your internal controls to specific regulatory provisions:

- **IMPLEMENTS**: Control fully implements the provision
- **PARTIALLY_IMPLEMENTS**: Control partially addresses the provision
- **ADDRESSES**: Control addresses the provision
- **REFERENCES**: Control references the provision

Each mapping includes a confidence score (0-1) indicating how well the control addresses the provision.

### Compliance Gap Analysis

RegEngine can analyze your products and identify:

- Regulatory provisions not yet mapped
- Coverage percentage by jurisdiction
- Unmapped requirements needing attention

## Step-by-Step Tutorial

### Scenario: Setting Up Compliance for a Crypto Trading Platform

#### Step 1: Define Your Controls

Create controls from your chosen framework (e.g., NIST CSF):

```bash
# Risk Management Control
curl -X POST "https://api.regengine.example.com/overlay/controls" \
  -H "X-RegEngine-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "control_id": "RM-001",
    "title": "Risk Assessment Process",
    "description": "Quarterly risk assessments for all trading operations",
    "framework": "NIST CSF"
  }'

# Data Protection Control
curl -X POST "https://api.regengine.example.com/overlay/controls" \
  -H "X-RegEngine-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "control_id": "DP-001",
    "title": "Customer Data Encryption",
    "description": "AES-256 encryption for all customer PII at rest and in transit",
    "framework": "ISO27001"
  }'
```

#### Step 2: Create Your Product

```bash
curl -X POST "https://api.regengine.example.com/overlay/products" \
  -H "X-RegEngine-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "product_name": "Crypto Trading Platform",
    "description": "Institutional cryptocurrency trading with custody",
    "product_type": "TRADING",
    "jurisdictions": ["US", "EU"]
  }'
```

Save the returned `id` for the next steps.

#### Step 3: Map Controls to Regulatory Provisions

```bash
# Map Risk Management control to a provision
curl -X POST "https://api.regengine.example.com/overlay/mappings" \
  -H "X-RegEngine-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "control_id": "control-uuid-from-step-1",
    "provision_hash": "provision-hash-from-regengine",
    "mapping_type": "IMPLEMENTS",
    "confidence": 0.95,
    "notes": "Our quarterly risk assessment fully implements this requirement"
  }'
```

#### Step 4: Link Controls to Products

```bash
curl -X POST "https://api.regengine.example.com/overlay/products/link-control" \
  -H "X-RegEngine-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": "product-uuid-from-step-2",
    "control_id": "control-uuid-from-step-1"
  }'
```

#### Step 5: View Compliance Coverage

```bash
# Get all requirements for your product
curl -X GET "https://api.regengine.example.com/overlay/products/{product_id}/requirements" \
  -H "X-RegEngine-API-Key: $API_KEY"
```

**Response**:
```json
{
  "product_id": "...",
  "product": {...},
  "controls": [...],
  "mappings": [...],
  "provisions": [...],
  "summary": {
    "total_controls": 2,
    "total_mappings": 1,
    "total_provisions": 1
  }
}
```

#### Step 6: Identify Compliance Gaps

```bash
# Find unmapped provisions for US jurisdiction
curl -X GET "https://api.regengine.example.com/overlay/products/{product_id}/compliance-gaps?jurisdiction=US" \
  -H "X-RegEngine-API-Key: $API_KEY"
```

**Response**:
```json
{
  "product_id": "...",
  "jurisdiction": "US",
  "total_provisions": 150,
  "mapped_provisions": 45,
  "unmapped_provisions": [...],
  "coverage_percentage": 30.0
}
```

## API Reference

### Base URL

```
https://api.regengine.example.com
```

### Authentication

All requests require the `X-RegEngine-API-Key` header:

```
X-RegEngine-API-Key: your_api_key_here
```

### Endpoints

#### Controls

- `GET /overlay/controls` - List all controls
- `GET /overlay/controls?framework=NIST+CSF` - Filter by framework
- `GET /overlay/controls/{control_id}` - Get control details
- `POST /overlay/controls` - Create a new control

#### Products

- `GET /overlay/products` - List all products
- `GET /overlay/products?product_type=TRADING` - Filter by type
- `GET /overlay/products/{product_id}/requirements` - Get regulatory requirements
- `GET /overlay/products/{product_id}/compliance-gaps?jurisdiction=US` - Gap analysis
- `POST /overlay/products` - Create a new product

#### Mappings

- `POST /overlay/mappings` - Map a control to a provision
- `POST /overlay/products/link-control` - Link a control to a product

#### Provisions

- `GET /overlay/provisions/{provision_hash}/overlays` - Get provision with tenant overlays

### Full OpenAPI Documentation

Visit `https://api.regengine.example.com/docs` for interactive API documentation.

## Best Practices

### 1. Use Meaningful Control IDs

```
✅ Good: "AC-001", "RM-042", "DP-015"
❌ Bad: "control1", "xyz", "temp"
```

### 2. Provide Detailed Descriptions

Your future self (and auditors) will thank you:

```
✅ Good: "Quarterly risk assessments covering operational, market, and compliance risks with executive review"
❌ Bad: "Risk stuff"
```

### 3. Track Confidence Scores Accurately

Be honest about how well your controls address requirements:

- **0.95-1.0**: Fully implements the provision
- **0.80-0.94**: Substantially implements with minor gaps
- **0.60-0.79**: Partially implements
- **<0.60**: Addresses but significant gaps remain

### 4. Regular Compliance Reviews

- Review gap analysis monthly
- Update mappings when controls change
- Track coverage trends over time

### 5. Organize by Framework

Group controls by their source framework for easier management:

```bash
# Get all NIST CSF controls
curl -X GET "https://api.regengine.example.com/overlay/controls?framework=NIST+CSF" \
  -H "X-RegEngine-API-Key: $API_KEY"
```

### 6. Leverage Product Types

Use appropriate product types for better organization:

- `TRADING` - Trading platforms
- `LENDING` - Lending/credit services
- `CUSTODY` - Asset custody services
- `PAYMENTS` - Payment processors
- `DERIVATIVES` - Derivatives trading
- `OTHER` - Other product types

### 7. Multi-Jurisdiction Support

When operating in multiple jurisdictions, create products for each:

```json
{
  "product_name": "Crypto Trading Platform - Global",
  "jurisdictions": ["US", "EU", "UK", "SG", "JP"]
}
```

Then use gap analysis per jurisdiction to track compliance.

## Support

### Documentation

- **API Docs**: `https://api.regengine.example.com/docs`
- **GitHub**: `https://github.com/regengine/regengine`

### Common Issues

**Issue**: "API key is not associated with a tenant"
**Solution**: Contact your administrator to ensure the API key has a tenant_id assigned.

**Issue**: "Rate limit exceeded"
**Solution**: Wait for the rate limit window to reset (see `X-RateLimit-Reset` header) or reduce request frequency.

**Issue**: "Control not found"
**Solution**: Ensure you're using the correct UUID (not the control_id) when referencing controls.

### Getting Help

For technical support:
1. Check the API documentation at `/docs`
2. Review this onboarding guide
3. Contact your RegEngine administrator
4. File an issue on GitHub

## Next Steps

1. ✅ Get your API key
2. ✅ Test authentication
3. ✅ Create your first control
4. ✅ Create your first product
5. ✅ Map a control to a provision
6. ✅ Link control to product
7. ✅ View compliance requirements
8. ✅ Run gap analysis

**You're ready to use RegEngine!**

Continue building out your compliance framework and tracking coverage across all your products and jurisdictions.
