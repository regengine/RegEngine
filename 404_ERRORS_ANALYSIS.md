# RegEngine - Comprehensive 404 Error Analysis
**Generated**: February 1, 2026 12:14 PST  
**Analysis Period**: Last 11+ hours of service uptime

---

## ✅ WORKING ENDPOINTS (No 404s)

### Admin API (Port 8400)
- ✅ `GET /health` → 200 OK
- ✅ `GET /v1/admin/review/hallucinations` → 200 OK (returns empty queue)

### NLP Service (Port 8001)
- ✅ `GET /health` → 200 OK
- ✅ No 404 errors in logs

### Graph Service (Port 8003)
- ✅ `GET /health` → 200 OK  
- ✅ `GET /v1/labels/health` → 200 OK
- ✅ No 404 errors in logs

### Compliance Service (Port 8005)
- ✅ No 404 errors in logs

---

## ❌ CONFIRMED 404 ERRORS

### 1. **Ingestion Service - /v1/ingest/url prefix issue**

**Endpoint**: `POST http://localhost:8002/v1/ingest/url`  
**Status**: ❌ 404 Not Found  
**Expected**: 200 OK

**Details:**
```bash
curl -X POST http://localhost:8002/v1/ingest/url \
  -H "X-RegEngine-API-Key: admin" \
  -d '{"url":"https://example.com","source_system":"test"}'

Response: {"detail":"Not Found"}
Status: 404
```

**Root Cause**: Route defined as `/ingest/url` but being accessed as `/v1/ingest/url`

**Actual Route Definition** (services/ingestion/app/routes.py:251):
```python
@router.post("/ingest/url", response_model=NormalizedEvent)
```

**Should Be**:
```python
@router.post("/v1/ingest/url", response_model=NormalizedEvent)
```

**Impact**: 
- External API calls using `/v1/ingest/url` fail
- Frontend proxies may be misconfigured
- Documentation likely references `/v1` prefix

**Occurrences in Logs**: 2+ instances
```
INFO: 140.82.114.6:45083 - "POST /v1/ingest/url HTTP/1.1" 404 Not Found
INFO: 140.82.114.6:42009 - "POST /v1/ingest/url HTTP/1.1" 404 Not Found
```

**Workaround**: Use `/ingest/url` (without `/v1` prefix)
```bash
curl -X POST http://localhost:8002/ingest/url \
  -H "X-RegEngine-API-Key: admin" \
  -d '{"url":"https://httpbin.org/html","source_system":"test"}'

✅ SUCCESS: Returns event_id and document_id
```

---

### 2. **Frontend - /api/review/items route**

**Endpoint**: `GET http://localhost:3000/api/review/items`  
**Status**: ❌ 404 Not Found (Next.js 404 page)  
**Expected**: 200 OK with JSON response

**Details:**
```bash
curl -s http://localhost:3000/api/review/items

Response: <!DOCTYPE html>...404: This page could not be found...</html>
Status: 404
```

**Root Cause**: API route located in `/src/app/_api/` (underscore prefix)

**Current Location**: `frontend/src/app/_api/review/items/route.ts`  
**Next.js Behavior**: Underscore-prefixed directories (`_api`) are treated as private/ignored

**Should Be**: `frontend/src/app/api/review/items/route.ts` (no underscore)

**Impact**:
- Frontend review page cannot load data
- Browser shows "Unable to load review queue" error
- Client-side hooks (`useReviewItems`) fail

**Alternative**: API routes in `_api` directory need to be moved to `api` directory

---

### 3. **Admin API - Early 404s (Now Fixed)**

**Endpoint**: `GET http://localhost:8400/v1/admin/review/hallucinations`  
**Status**: ✅ Now working (200 OK)  
**Historical**: Had 404 errors before router registration

**Details:**
Earlier logs show 404s:
```
INFO: 140.82.114.6:18200 - "GET /v1/admin/review/hallucinations?..." 404 Not Found
INFO: 140.82.114.6:40050 - "GET /v1/admin/review/hallucinations?..." 404 Not Found
```

**Current Status**: Now returns 200 OK
```json
{"items":[],"total":0,"page":1,"limit":10}
```

**Fix Applied**: Added `review_routes.py` and registered router in `main.py`

---

## 📊 Summary Statistics

| Service | 404 Errors | Status |
|---------|-----------|--------|
| **Ingestion** | 2+ instances | ❌ Active issue |
| **Frontend API** | Unknown (route doesn't exist) | ❌ Active issue |
| **Admin API** | 2 instances | ✅ Fixed |
| **NLP** | 0 | ✅ No issues |
| **Graph** | 0 | ✅ No issues |
| **Compliance** | 0 | ✅ No issues |

---

## 🔧 Required Fixes

### Priority 1: Ingestion Service Route Prefix

**File**: `services/ingestion/app/routes.py`

**Current** (Line 251):
```python
@router.post("/ingest/url", response_model=NormalizedEvent)
async def ingest_url(...)
```

**Fix**:
```python
@router.post("/v1/ingest/url", response_model=NormalizedEvent)
async def ingest_url(...)
```

**OR** update router prefix in main.py to add `/v1`

---

### Priority 2: Frontend API Routes Directory

**Current Structure**:
```
frontend/src/app/_api/review/items/route.ts  ❌ (underscore = ignored)
```

**Required Structure**:
```
frontend/src/app/api/review/items/route.ts  ✅ (no underscore = served)
```

**Action**: Move entire `_api` directory to `api`:
```bash
cd frontend/src/app
mv _api api
```

**Files to Move**:
- `_api/review/items/route.ts`
- `_api/review/[...path]/route.ts`
- `_api/health/route.ts`
- `_api/ingest/url/route.ts`
- `_api/ingest/file/route.ts`
- All other `_api/*` routes

---

## 🎯 Testing Commands

### Test Ingestion (Working Path):
```bash
curl -X POST http://localhost:8002/ingest/url \
  -H "Content-Type: application/json" \
  -H "X-RegEngine-API-Key: admin" \
  -d '{"url":"https://httpbin.org/html","source_system":"test"}'
```

### Test Ingestion (Broken Path):
```bash
curl -X POST http://localhost:8002/v1/ingest/url \
  -H "Content-Type: application/json" \
  -H "X-RegEngine-API-Key: admin" \
  -d '{"url":"https://httpbin.org/html","source_system":"test"}'
```

### Test Review Queue (Backend - Working):
```bash
curl -H "X-RegEngine-API-Key: admin" \
  'http://localhost:8400/v1/admin/review/hallucinations?limit=10'
```

### Test Review Queue (Frontend - Broken):
```bash
curl http://localhost:3000/api/review/items
```

---

## 📝 Verification Checklist

After fixes:
- [ ] POST `/v1/ingest/url` returns 200 OK
- [ ] POST `/ingest/url` still works (backward compatibility)
- [ ] GET `/api/review/items` returns JSON (not 404 HTML)
- [ ] Frontend review page loads without errors
- [ ] All tests pass
- [ ] API documentation updated with correct routes

---

## 🔍 Related Issues

1. **API Version Consistency**: Some routes use `/v1` prefix, others don't
2. **Frontend Route Convention**: Mix of `_api` and `api` directories suggests inconsistent patterns
3. **Documentation Sync**: API docs likely reference `/v1` routes that don't exist

---

**End of Report**
