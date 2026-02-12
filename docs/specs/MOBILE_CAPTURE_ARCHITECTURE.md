# Mobile Supply Chain Data Capture: Architecture Specification

## Executive Summary
The "Top Tier" standard for field documentation combines **deterministic scanning** (for identification) with **probabilistic AI analysis** (for condition/context). Relying solely on photographing and NLP parsing is error-prone and slow. The best-in-class approach represents a "Hybrid Capture" workflow.

## 1. The "Better Way": Deterministic Identification
For identifying *what* an item is (SKU, Lot, Serial), computer vision/OCR is inferior to barcode scanning.

*   **Technology**: GS1-128 (UCC/EAN-128) & GS1 DataMatrix scanning.
*   **Implementation**: 
    *   **Frontend**: `html5-qrcode` or `ZXing` (Open Source) / Scandit (Enterprise) running in a PWA.
    *   **Data**: Instantly captures GTIN, Batch/Lot, Expiry Date, and Serial Number (SGTIN) without NLP guesswork.
    *   **Why**: 100% accuracy, <100ms processing time, works offline.

## 2. The "Photo" Role: Proof & Unstructured Data
Photography is essential for *condition*, *proof of location*, and *unstructured labels* (e.g., hand-written logs, damaged labels).

*   **Best-in-Class Parsing**: **Multimodal LLMs** (GPT-4o, Gemini 1.5 Pro).
    *   Traditional OCR (Tesseract/Textract) loses layout context.
    *   Multimodal LLMs "see" the image like a human, understanding that "02/24" near a "Best By" label is a date, not a quantity.
*   **Frontend Features**:
    *   **Edge Detection**: Auto-crop document boundaries (OpenCV.js).
    *   **Perspective Correction**: Flatten the image for better analysis.
    *   **Image Compression**: WebP format to reduce upload size.

## 3. Recommended Architecture

### Frontend (Field Operator PWA)
A mobile-first view in the RegEngine Next.js app (`/mobile/capture`).

*   **Mode A: Fast Scan (Inventory/Receiving)**
    *   Continuous video feed scanning for barcodes.
    *   Beep/Haptic feedback on successful scan.
    *   Batch mode (scan 10 items -> submit).

*   **Mode B: smart Camera (Documentation)**
    *   "Docs" mode: Auto-crops BOLs/Invoices.
    *   "Evidence" mode: Captures photo + GPS + Timestamp + User ID.

### Backend (RegEngine Services)
*   **Ingestion Service**: Add `ImageParser` triggered by MIME type (`image/jpeg`, `image/webp`).
*   **NLP Service**: Upgrade to support Multimodal inputs.
    *   *Input*: Image URL/Base64.
    *   *Model*: GPT-4o / Gemini 1.5.
    *   *Prompt*: "Extract the following JSON schema: { date, origin, condition, handwriting_text }."

## 4. Implementation roadmap

### Phase 1: Barcode Foundation (The "Better Way")
1.  Add `html5-qrcode` to Frontend.
2.  Create `/mobile/scan` route.
3.  Parsing logic for GS1 Application Identifiers (AIs).

### Phase 2: Multimodal Ingestion (The "Photo" Way)
1.  Update `ingestion-service` to accept image uploads.
2.  Implement `services/ingestion/parsers/image_llm_parser.py`.
3.  Connect to OpenAI/Gemini Vision API.

### Phase 3: Offline Sync
1.  Service Worker caching for the PWA.
2.  IndexedDB storage for offline scans.
3.  Background Sync API for uploading when connectivity is restored.
