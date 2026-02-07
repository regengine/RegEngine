# FDA Audit Checklist - FSMA 204 Compliance

## 1. Pre-Audit System Verification
Before the scheduled audit, verify the following system states:

- [ ] **Data Retention**: Verify logs/records exist for required 2 years.
    ```sql
    SELECT min(created_at) FROM extraction_logs; -- Should be > 2 years ago (or system start)
    ```
- [ ] **Clock Synchronization**: Ensure NTP is active on all nodes (Critical for Time Arrow validation).
- [ ] **Version Control**: Generate software bill of materials (SBOM) for current deployment.

## 2. 24-Hour Recall Response Test
*Mandate: Must produce sortable spreadsheet of traceability data within 24 hours of request.*

- [ ] **Forward Trace**: Run forward trace on random sample Lot Code.
    *   `GET /v1/fsma/export/trace/{tlc}?direction=forward`
    *   Verify CSV headers match FDA template.
- [ ] **Backward Trace**: Run backward trace on random sample.
    *   `GET /v1/fsma/export/trace/{tlc}?direction=backward`
- [ ] **Verify Timestamps**: Check that `Response Time` < 24 hours (Internal SLA: 4 hours).

## 3. Data Integrity & Validation
- [ ] **Chain of Custody**: Verify no broken links in graph.
    *   Run `MATCH (n) WHERE not (n)--() RETURN n` to find orphaned nodes.
- [ ] **Mass Balance**: Run mass balance check on top 5 commodities.
    *   Ensure variance is within defined tolerance (e.g., < 2%).
- [ ] **Immutable Logs**: Extract Audit Logs for specific period.
    *   Export from `audit_events` table proving no records were deleted.

## 4. Artifact Generation Procedures

### Generating the Electronic Sortable Spreadsheet
1.  **Login** to Admin Dashboard.
2.  **Navigate** to `/trace`.
3.  **Input** the FDA-provided Traceability Lot Code (TLC).
4.  **Click** "Export CSV".
5.  **Validate** file integrity (open in Excel/Numbers).
6.  **Hash** the file (SHA-256) for non-repudiation.

### Generating the Recall Plan
1.  **Navigate** to `/compliance`.
2.  **Click** "Download Traceability Plan".
3.  **Print** physical copy as backup.

## 5. During Audit
*   **Role Assignment**:
    *   **Primary Contact**: Compliance Officer (speaks to FDA agent).
    *   **Technical Support**: Lead Engineer (drives the demo/dashboard).
*   **Protocol**:
    *   Only answer the specific questions asked.
    *   Do not volunteer extra data/system access.
    *   Record all requests in `docs/compliance/audit_requests.md`.
