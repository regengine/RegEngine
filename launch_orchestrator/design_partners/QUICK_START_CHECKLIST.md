# RegEngine Design Partner - Quick Start Checklist

Use this checklist to get up and running in your first hour with RegEngine.

---

## ☐ Pre-Flight (5 minutes)

- [ ] Received API key via secure channel
- [ ] Joined #regengine-design-partners Slack channel
- [ ] Added bi-weekly check-in meetings to calendar (Wednesdays)
- [ ] Reviewed design partner agreement terms

---

## ☐ Environment Verification (10 minutes)

### Test API Connectivity

```bash
curl -X GET "https://sandbox.regengine.ai/health" \
  -H "X-RegEngine-API-Key: YOUR_API_KEY"
```

**Expected response**: `{"status": "healthy", "version": "1.0.0"}`

- [ ] ✅ Health check returns 200 OK
- [ ] ✅ API key accepted (no 401 error)

### Check Rate Limits

```bash
curl -I -X GET "https://sandbox.regengine.ai/health" \
  -H "X-RegEngine-API-Key: YOUR_API_KEY"
```

Look for headers:
- `X-RateLimit-Limit: 60`
- `X-RateLimit-Remaining: 59`

- [ ] ✅ Rate limit headers present

---

## ☐ First API Call (15 minutes)

### Query Pre-Loaded Data

```bash
# List available jurisdictions
curl -X GET "https://sandbox.regengine.ai/jurisdictions" \
  -H "X-RegEngine-API-Key: YOUR_API_KEY"

# Get obligations from US SEC
curl -X GET "https://sandbox.regengine.ai/obligations?jurisdiction=United%20States&limit=5" \
  -H "X-RegEngine-API-Key: YOUR_API_KEY"
```

- [ ] ✅ Retrieved list of jurisdictions (US, UK, EU)
- [ ] ✅ Retrieved at least 5 obligations from US SEC

---

## ☐ Test Ingestion (20 minutes)

### Ingest a Sample Document

```bash
curl -X POST "https://sandbox.regengine.ai/ingest/url" \
  -H "X-RegEngine-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.sec.gov/rules/final/2023/example.pdf",
    "jurisdiction": "United States",
    "source_type": "sec_release",
    "effective_date": "2024-01-15"
  }'
```

**Expected response**: Document ID and processing status

- [ ] ✅ Document accepted for ingestion
- [ ] ✅ Received document ID

### Wait for Processing (3-5 minutes)

```bash
curl -X GET "https://sandbox.regengine.ai/documents/{DOCUMENT_ID}/status" \
  -H "X-RegEngine-API-Key: YOUR_API_KEY"
```

- [ ] ✅ Status changed from "processing" to "completed"

### Query Extracted Obligations

```bash
curl -X GET "https://sandbox.regengine.ai/obligations?document_id={DOCUMENT_ID}" \
  -H "X-RegEngine-API-Key: YOUR_API_KEY"
```

- [ ] ✅ Retrieved obligations extracted from your document

---

## ☐ Explore Advanced Features (10 minutes)

### Cross-Jurisdiction Comparison

```bash
curl -X GET "https://sandbox.regengine.ai/opportunities/arbitrage?j1=United%20States&j2=United%20Kingdom&concept=capital_requirements" \
  -H "X-RegEngine-API-Key: YOUR_API_KEY"
```

- [ ] ✅ Retrieved regulatory differences between US and UK

### Provenance Tracking

```bash
# Get an obligation ID from previous query, then:
curl -X GET "https://sandbox.regengine.ai/provenance/{OBLIGATION_ID}" \
  -H "X-RegEngine-API-Key: YOUR_API_KEY"
```

- [ ] ✅ Retrieved source document + page number for obligation

---

## ☐ Post-Setup (5 minutes)

- [ ] Bookmarked API documentation: https://docs.regengine.ai
- [ ] Posted introduction in Slack channel
- [ ] Identified primary use case to validate (change monitoring / gap analysis / multi-jurisdiction)
- [ ] Scheduled 30-minute planning session with your team

---

## Troubleshooting

### Issue: "Invalid API Key" (401 error)

**Solution**:
1. Verify you're using the correct API key (starts with `dp_sandbox_`)
2. Check that header is `X-RegEngine-API-Key` (case-sensitive)
3. Ensure no extra whitespace in API key
4. Contact us in Slack if issue persists

### Issue: "Rate Limit Exceeded" (429 error)

**Solution**:
1. Default limit is 60 requests/minute
2. Implement exponential backoff in your client
3. If you need higher limits, request via Slack

### Issue: Document Ingestion Stuck on "Processing"

**Solution**:
1. Check document size (max 50MB)
2. Verify URL is publicly accessible (not behind auth)
3. Wait up to 10 minutes for large PDFs
4. Contact support if stuck > 15 minutes

### Issue: No Obligations Extracted from Document

**Possible causes**:
- Document is not regulatory text (e.g., marketing material)
- OCR failed (document is image-based with poor quality)
- Jurisdiction/language not supported yet

**Next steps**: Share document URL in Slack for manual review

---

## Next Steps

Once you've completed this checklist:

1. **Review ONBOARDING_GUIDE.md** for Week 1-8 detailed plan
2. **Join tomorrow's office hours** (optional, Tuesdays 2-3pm ET)
3. **Start integrating** with your primary use case
4. **Share feedback** in Slack as you go

---

## Quick Reference

| Resource | URL |
|----------|-----|
| API Docs | https://docs.regengine.ai |
| Sandbox API | https://sandbox.regengine.ai |
| Support Slack | #regengine-design-partners |
| Support Email | support@regengine.ai |
| Status Page | https://status.regengine.ai |

---

**Estimated time to complete**: 60 minutes

**Questions?** Post in Slack or email support@regengine.ai

---

**Version**: 1.0
**Last Updated**: 2025-11-19
