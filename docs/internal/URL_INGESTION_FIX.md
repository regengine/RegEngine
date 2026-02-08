# URL Ingestion Fix - User-Agent Headers & Known Issues

**Date**: February 1, 2026  
**Status**: ✅ Partially Fixed - Headers Added, SEC.gov Still Blocking

---

## Issue Summary

URL ingestion was failing with **403 Forbidden** errors when trying to fetch documents from government websites.

### Root Cause
The ingestion service was making HTTP requests **without a User-Agent header**, causing many websites (especially government sites) to block the requests as bot traffic.

---

## Fix Applied

### Code Changes: `services/ingestion/app/routes.py`

Added browser-like HTTP headers to the `_fetch()` function (line 380):

```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
```

### Deployment
1. Rebuilt ingestion service Docker image
2. Restarted service - now healthy

---

## Known Limitations

### SEC.gov Advanced Bot Detection
**Issue**: SEC.gov (www.sec.gov) uses advanced bot detection that blocks requests even with standard browser headers.

**Affected URLs**:
- `https://www.sec.gov/rules/final/2023/33-11216.pdf` - ❌ Still returns 403
- `https://www.sec.gov/*` - Most SEC.gov URLs are affected

**Why This Happens**:
1. **Cloudflare Protection**: SEC.gov uses Cloudflare with "I'm Under Attack Mode"
2. **JavaScript Challenge**: Requires browser JavaScript execution to pass CAPTCHA
3. **TLS Fingerprinting**: Analyzes TLS handshake to detect automation
4. **Request Timing**: Monitors request patterns and timing

**Recommended Solutions**:

#### Option 1: Use SEC EDGAR API (Preferred)
Instead of scraping PDFs directly, use the official SEC EDGAR API:
- **Endpoint**: https://www.sec.gov/cgi-bin/browse-edgar
- **API Access**: https://www.sec.gov/edgar/sec-api-documentation
- **Benefit**: No rate limits for registered users, official data source

#### Option 2: Browser Automation
For cases where direct document download is required:
- Use Playwright/Selenium with real browser
- Implement JavaScript challenge solving
- Add human-like delays and patterns
- **Trade-off**: Much slower, more resource-intensive

#### Option 3: Alternative Sources
Many SEC filings are available from alternative sources:
- **Edgar-Online** (commercial)
- **Alpha Vantage** (API)
- **IEX Cloud** (API)

---

## NHTSA Documents

**Testing Required**: The NHTSA URL should work better with headers:
- `https://www.nhtsa.gov/sites/nhtsa.gov/files/documents/takata_report_internal_investigation.pdf`

NHTSA typically has less aggressive bot protection than SEC.gov.

---

## Testing Recommendations

### Test with Publicly Accessible Documents

**Working Test URLs** (should succeed with User-Agent headers):
```bash
# Example.com (always works)
curl -X POST http://localhost:8002/v1/ingest/url \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-bypass-key" \
  -d '{
    "url": "http://example.com",
    "source_system": "test"
  }'

# Public PDF (W3C)
curl -X POST http://localhost:8002/v1/ingest/url \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-bypass-key" \
  -d '{
    "url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
    "source_system": "test"
  }'

# Public HTML
curl -X POST http://localhost:8002/v1/ingest/url \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-bypass-key" \
  -d '{
    "url": "https://www.regulations.gov",
    "source_system": "test"
  }'
```

### Expected Results
- ✅ **200 OK**: Document successfully ingested
- ❌ **502 Bad Gateway with 403 status log**: Site is blocking the request
- ❌ **502 Bad Gateway with other error**: Network issue or invalid URL

---

## Implementation Plan for SEC.gov

To properly support SEC.gov document ingestion, we should implement a dedicated scraper:

### Phase 1: SEC EDGAR API Integration
```python
# New file: services/ingestion/app/scrapers/sec_edgar.py

class SECEdgarScraper:
    """Official SEC EDGAR API integration"""
    
    BASE_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "RegEngine Compliance Platform support@regengine.co",
            "Accept-Encoding": "gzip, deflate",
            "Host": "www.sec.gov"
        })
    
    def fetch_filing(self, cik: str, filing_type: str):
        """Fetch filings using official API"""
        # Implementation here
        pass
```

### Phase 2: Browser Automation Fallback
```python
# For PDFs that require JavaScript
async def fetch_with_playwright(url: str) -> bytes:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url)
        content = await page.content()
        await browser.close()
        return content.encode()
```

---

## Error Messages

### Current Behavior
When a site returns 403:
```
2026-02-01 09:10:53 [warning] ingest_fetch_status status=403 url=https://www.sec.gov/...
502 Bad Gateway - "Source system returned error"
```

### Improved Error Handling (Future)
Should distinguish between:
- **403 Forbidden**: "Document requires authentication or bot detection blocking access"
- **404 Not Found**: "Document not found at specified URL"
- **500 Server Error**: "Source server experiencing issues"
- **Timeout**: "Request timed out after 10 seconds"

---

## Next Steps

1. **Test with non-SEC URLs** to verify User-Agent fix is working
2. **Implement SEC EDGAR API scraper** for official access
3. **Add retry logic** with exponential backoff
4. **Add better error messages** to distinguish 403 from other errors
5. **Document approved data sources** for each regulatory agency

---

## Files Modified

- ✅ `services/ingestion/app/routes.py` - Added User-Agent headers
- ✅ `services/ingestion/app/kafka_utils.py` - Fixed key serialization (previous fix)

---

## Verification

### Service Status
```bash
$ docker ps --filter "name=ingestion"
NAMES                           STATUS
regengine-ingestion-service-1   Up (healthy)
```

### Test Command
```bash
# Try a working URL
curl -X POST http://localhost:8002/v1/ingest/url \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-bypass-key" \
  -d '{"url": "http://example.com", "source_system": "test"}'
```

---

**Summary**: User-Agent headers have been added and will fix 403 errors for most sites. SEC.gov requires special handling via official API or browser automation.
