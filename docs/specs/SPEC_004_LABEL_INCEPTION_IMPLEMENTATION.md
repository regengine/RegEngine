# Engineering Spec: Label Inception Module (End-to-End)
**Target:** AI Engineering Team / Autonomous Agents
**Context:** Feature Implementation (FE-104 & BE-104)
**Reference:** `docs/RFC_004_LABEL_INCEPTION_SERVICE_v1.3.md`

---

## 1. System Architecture
We are building a **synchronous Label Inception loop** where the Frontend acts as the trigger for the Backend's atomic graph write.

**Flow:**
1. **User** (Packer) inputs Batch Data in Next.js UI.
2. **Frontend** POSTs to `graph-service`.
3. **Backend** writes atomic `Lot` + `TraceEvent` to Neo4j.
4. **Backend** returns serialized ZPL/QR data.
5. **Frontend** renders a client-side PDF for printing.

---

## 2. Backend Implementation Directives (Python/FastAPI)

### Directive 2.1: Router Integration
**Context:** The router logic exists in `services/graph/app/routers/labels.py` (v1.3).
**Task:** Mount this router into the main application.

* **Target File:** `services/graph/main.py`
* **Action:**
    ```python
    from app.routers import labels
    # ... inside create_app() or main scope ...
    app.include_router(labels.router)
    ```

### Directive 2.2: Database Constraints
**Context:** Atomic serialization relies on unique constraints.
**Task:** Ensure these Cypher statements are executed on startup or via migration script.

```cypher
CREATE CONSTRAINT lot_tlc_tenant_unique IF NOT EXISTS
FOR (l:Lot) REQUIRE (l.tlc, l.tenant_id) IS UNIQUE;

CREATE INDEX lot_gtin_tenant_idx IF NOT EXISTS
FOR (l:Lot) ON (l.gtin, l.tenant_id);
```

---

## 3. Frontend Implementation Directives (React/Next.js)

### Directive 3.1: Type Definitions

**Target File:** `frontend/src/types/labels.ts`
**Requirement:** strictly match the Backend Pydantic models.

```typescript
export interface LabelBatchInitRequest {
  packer_gln: string;
  product: {
    gtin: string;
    description: string;
    plu?: string;
    expected_units: number;
  };
  traceability: {
    lot_number: string;
    pack_date: string; // YYYY-MM-DD
    grower_gln?: string;
  };
  quantity: number;
  unit_of_measure: "EA" | "LBS" | "CASE";
  packaging_level: "item" | "case" | "pallet";
}

export interface LabelResponse {
  batch_id: string;
  reserved_range: { start: number; end: number };
  labels: Array<{
    serial: string;
    qr_payload: string;
    zpl_code: string;
    packaging_level: string;
  }>;
}
```

### Directive 3.2: Label Generator Page

**Target File:** `frontend/src/app/compliance/labels/page.tsx`
**Layout:**

* Use `PageContainer` and `Card` components from `@/components/ui`.
* Title: "Traceability Label Generator".

**Component Logic:**

1. **Form:** Use `react-hook-form` + `zod` validation.
    * Fields: `GTIN` (Select from list or text), `Lot Number` (Text), `Pack Date` (Date Picker), `Quantity` (Number).
2. **Mutation:** Use `useMutation` (TanStack Query) to call `POST /labels/batch/init` then `POST /labels/serial/reserve`.
3. **State:** Manage `step` ('input' -> 'generating' -> 'preview').

### Directive 3.3: Client-Side PDF Generation

**Context:** Small farmers need a PDF they can print on standard Avery sheets (e.g., Avery 5160 or 2x2 custom).
**Library:** Use `@react-pdf/renderer` (Dynamic client-side generation).

**Component:** `frontend/src/components/labels/LabelPdfDocument.tsx`

```tsx
import { Document, Page, View, Text, Image } from '@react-pdf/renderer';
import QRCode from 'qrcode'; // Generate QR Data URL from payload

// Logic:
// 1. Map over `labels` array from API response.
// 2. For each label, generate QR image using `QRCode.toDataURL(label.qr_payload)`.
// 3. Render a View with:
//    - PLU (Large Font)
//    - Product Name (Small Font)
//    - QR Image (15mm x 15mm)
//    - Human Readable Serial (Bottom)
```

---

## 4. Integration Test Plan (Automated)

### Test Case 4.1: The "Double Click"

**Scenario:** User accidentally clicks "Generate" twice for the same Lot.
**Expected Behavior:**

* First Request: `200 OK` (Returns labels).
* Second Request: `200 OK` (Idempotent `batch/init`) OR `409 Conflict` (if strict mode enabled).
* **Critical:** Verify `next_serial` in Neo4j does not jump unexpectedly.

### Test Case 4.2: Tenant Leaks

**Scenario:** Send request with `X-Tenant-ID: tenant_a` but try to reserve serials for a Lot owned by `tenant_b`.
**Expected Behavior:** `404 Not Found` (Security by Obscurity).

---

## 5. Environment Configuration

**Backend (`.env`):**

```bash
TRACEABILITY_DOMAIN="https://trace.regengine.ai"
# Neo4j Credentials must be active
```

**Frontend (`.env.local`):**

```bash
NEXT_PUBLIC_API_URL="http://localhost:8000"
```

---

## 6. Implementation Status

This specification document was created as part of the Label Inception Module implementation.
The implementation follows these directives in order:

1. ✅ Specification document created
2. ⏳ Backend router implementation
3. ⏳ Frontend type definitions
4. ⏳ Frontend UI components
5. ⏳ Testing and validation
