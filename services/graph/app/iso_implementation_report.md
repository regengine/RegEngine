Graph Service Tenant Isolation - Implementation Report
======================================================
Date: 2026-02-01

Summary
-------
Successfully implemented tenant isolation across the Graph Service by enforcing `tenant_id` resolution from JWTs and routing database operations to tenant-specific Neo4j databases (`reg_tenant_{hex_id}`).

Key Changes
-----------

1. **API Endpoints (Tenant-Aware Routing)**
   - **Routes**: `/provisions/by-request` now queries tenant DB.
   - **Labels**: `initialize_label_batch` instantiates `Neo4jClient` with tenant DB.
   - **Traceability**: Forward/Backward/Timeline endpoints use `get_current_tenant_id` -> Tenant DB.
   - **Compliance**: Export (CSV) and Gap Analysis endpoints use Tenant DB.
   - **Science**: Mass Balance endpoints use Tenant DB.
   - **Metrics**: Data Quality and Dashboard endpoints use Tenant DB.

2. **Recall Service (Architecture Refactor)**
   - Refactored `get_recall_engine` to a **Singleton** pattern to persist drill state in-memory.
   - Updated `MockRecallEngine` to dynamically bind `trace_forward` / `trace_backward` functions with the request's `tenant_id`.
   - Recall drills now execute traces against the correct Tenant DB.

3. **Ingestion (Consumer)**
   - **New Format**: `GraphEvent` processing uses `tenant_id` to route to Tenant DB (verified).
   - **Legacy Format**: Fixed a bug where `tenant_id` was undefined in the `except ValidationError` block. Added logic to extract `tenant_id` from message and route legacy upserts to Tenant DB (where applicable) or fallback to Global with explicit `database=` selection.

4. **Arbitrage Service**
   - **Decision**: Remained on **Global DB**. Arbitrage detection (`/graph/arbitrage`, `/graph/gaps`) relies on Compliance Framework definitions (Reference Data), which are shared globally.

5. **Fixes**
   - Corrected `fsma_routes.py` to export `fsma_router` instead of `router`, resolving an `ImportError` in `main.py`.
   - Validated all imports via script.

Verification
------------
- **Static Analysis**: All modified files import correctly.
- **Isolation Logic**: `Neo4jClient.get_tenant_database_name(tenant_id)` is used in all user-data paths.
- **Reference Data**: Global DB is used only for `Arbitrage` and `Identifiers` (stateless/validation).

Next Steps
----------
- Deploy updated Graph Service.
- Run integration tests to verify End-to-End isolation (Ingest -> Graph -> API).
