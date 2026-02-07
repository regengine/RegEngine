# Tenant Documentation

Welcome to the RegEngine tenant documentation! This directory contains guides and examples for using RegEngine's self-service API.

## Getting Started

1. **[Onboarding Guide](./ONBOARDING_GUIDE.md)** - Start here! Complete guide to getting set up with RegEngine
2. **[API Examples](./API_EXAMPLES.md)** - Code examples in Python, TypeScript, and cURL

## Quick Links

- **Interactive API Docs**: `https://api.regengine.example.com/docs` (Swagger UI)
- **Alternative Docs**: `https://api.regengine.example.com/redoc` (ReDoc)
- **GitHub**: `https://github.com/regengine/regengine`

## What is RegEngine?

RegEngine is a multi-tenant regulatory intelligence platform that helps you:

- **Define Internal Controls**: Map your compliance frameworks (NIST CSF, SOC2, ISO27001, GDPR, etc.)
- **Track Products**: Manage products requiring regulatory compliance
- **Map to Regulations**: Link controls to specific regulatory provisions
- **Identify Gaps**: Discover unmapped compliance requirements
- **Maintain Audit Trail**: All actions logged for compliance

## Core Concepts

### Tenant Controls
Your internal compliance controls from any framework (NIST CSF, SOC2, ISO27001, custom, etc.)

### Customer Products
Products/services you offer that require regulatory compliance (trading platforms, lending, custody, etc.)

### Control Mappings
Links between your controls and specific regulatory provisions with confidence scores

### Compliance Gaps
Regulatory provisions not yet addressed by your controls

## API Overview

### Base URL
```
https://api.regengine.example.com
```

### Authentication
All requests require an API key:
```
X-RegEngine-API-Key: your_api_key_here
```

### Main Endpoints

**Controls**:
- `GET /overlay/controls` - List controls
- `POST /overlay/controls` - Create control
- `GET /overlay/controls/{id}` - Get control details

**Products**:
- `GET /overlay/products` - List products
- `POST /overlay/products` - Create product
- `GET /overlay/products/{id}/requirements` - Get requirements
- `GET /overlay/products/{id}/compliance-gaps` - Gap analysis

**Mappings**:
- `POST /overlay/mappings` - Map control to provision
- `POST /overlay/products/link-control` - Link control to product

**Provisions**:
- `GET /overlay/provisions/{hash}/overlays` - Get provision overlays

## Quick Start Example

```bash
# Set your API key
export API_KEY="your_api_key_here"
export BASE_URL="https://api.regengine.example.com"

# Create a control
curl -X POST "$BASE_URL/overlay/controls" \
  -H "X-RegEngine-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "control_id": "AC-001",
    "title": "Access Control Policy",
    "description": "Comprehensive access control policy",
    "framework": "NIST CSF"
  }'

# Create a product
curl -X POST "$BASE_URL/overlay/products" \
  -H "X-RegEngine-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "product_name": "Trading Platform",
    "description": "Crypto trading platform",
    "product_type": "TRADING",
    "jurisdictions": ["US", "EU"]
  }'
```

## Python Example

```python
import requests

API_KEY = "your_api_key_here"
BASE_URL = "https://api.regengine.example.com"

headers = {
    "X-RegEngine-API-Key": API_KEY,
    "Content-Type": "application/json"
}

# List all controls
response = requests.get(f"{BASE_URL}/overlay/controls", headers=headers)
controls = response.json()
print(f"Total controls: {controls['count']}")
```

## Documentation Files

| File | Description |
|------|-------------|
| [ONBOARDING_GUIDE.md](./ONBOARDING_GUIDE.md) | Complete getting started guide |
| [API_EXAMPLES.md](./API_EXAMPLES.md) | Code examples in multiple languages |
| [README.md](./README.md) | This file - documentation overview |

## Support

### Documentation
- **Interactive API Docs**: `/docs` endpoint (Swagger UI)
- **Alternative Docs**: `/redoc` endpoint (ReDoc)
- **GitHub**: https://github.com/regengine/regengine

### Common Questions

**Q: How do I get an API key?**
A: Contact your RegEngine administrator to have a tenant-specific API key created for you.

**Q: Can I use the same API key for multiple products?**
A: Yes! Your API key is tenant-scoped, so all your products, controls, and mappings are automatically isolated.

**Q: What frameworks are supported?**
A: Any framework! Common ones include NIST CSF, SOC2, ISO27001, GDPR, PCI-DSS, but you can use custom frameworks too.

**Q: How do I find provision hashes to map to?**
A: Use the provision search endpoint (documentation coming soon) or contact support for assistance.

**Q: Is there a rate limit?**
A: Yes, see the `X-RateLimit-*` headers in API responses for your current limits and usage.

## Next Steps

1. ✅ Read the [Onboarding Guide](./ONBOARDING_GUIDE.md)
2. ✅ Get your API key from your administrator
3. ✅ Try the [API Examples](./API_EXAMPLES.md)
4. ✅ Visit the interactive docs at `/docs`
5. ✅ Build your compliance framework!

## Feedback

We'd love to hear from you! If you have questions, suggestions, or find issues:

1. Check the documentation first
2. Contact your administrator
3. File an issue on GitHub
4. Join our community discussions

---

**Happy compliance tracking!** 🎯
