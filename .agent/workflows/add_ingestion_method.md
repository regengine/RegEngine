---
description: How to add a new generic ingestion method
---

# How to Add a New Ingestion Method

Follow this workflow to add a new ingestion method (e.g., File Upload, Crawler) to the generic `/ingest` page.

## 1. Backend Implementation
Ensure the backend `ingestion-service` has an endpoint to handle the new method.
- Example: `POST /ingest/file`

## 2. API Proxy (Frontend)
Create a Next.js API route to proxy the request to the backend. This avoids CORS issues and hides backend URLs.
- Path: `frontend/src/app/_api/ingest/[method]/route.ts`
- Ensure it handles `Multipart/Form-Data` if uploading files.

## 3. API Client Update
Update `frontend/src/lib/api-client.ts` to add a method for the new ingestion type.
- Example: `ingestFile(apiKey, file)`

## 4. Hook Creation
Update `frontend/src/hooks/use-api.ts` to expose a React Query mutation hook.
- Example: `useIngestFile()`

## 5. UI Update
Update `frontend/src/app/ingest/page.tsx`:
- Import the new hook.
- Add a new Tab to the `Tabs` component.
- Implement the form/input for the new method.
- Update `handleSubmit` to switch between methods based on the active tab.

## 6. Validation
- Verify the new method handles errors gracefully.
- Ensure the Job ID is returned and tracking starts.
