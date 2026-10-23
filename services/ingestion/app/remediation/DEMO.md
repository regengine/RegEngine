# Supplier remediation slice — demo sequence

The slice is mounted in the monolith behind `_router_enabled("remediation")`
(always-on unless listed in `DISABLED_ROUTERS`). All buyer endpoints need an
API key with `remediation.read` / `remediation.write` / `remediation.export`
scopes (or a wildcard key); supplier endpoints are token-scoped and
unauthenticated. Tenants must have UUID ids.

## Data-free checks (no server needed)

The current tests cover empty and header-only uploads. Row-level integration
coverage requires real supplier data:

```bash
cd services/ingestion && pytest tests/remediation -q
```

## Curl sequence (running monolith)

Use an actual supplier manifest with a row that needs correction, and set
`SUPPLIER_ORG` and `SUPPLIER_EMAIL` from that supplier's records.

```bash
BASE=http://localhost:8000        # monolith
AUTH="X-RegEngine-API-Key: $API_KEY"

# 1. Supplier CSV arrives; RegEngine preserves bytes + SHA-256, validates,
#    stages rows, and opens exception + remediation cases for defects.
curl -sf -X POST "$BASE/api/v1/remediation/manifests" -H "$AUTH" \
  -F "file=@path/to/your-supplier-manifest.csv" \
  -F "supplier_org=$SUPPLIER_ORG" | tee /tmp/upload.json
RUN=$(jq -r .ingestion_run_id /tmp/upload.json)
CASE=$(jq -r '.records[] | select(.blocking) | .remediation_case_id' /tmp/upload.json)

# 2. Buyer view: per-row status, provenance, failure reasons.
curl -sf "$BASE/api/v1/remediation/manifests/$RUN" -H "$AUTH" | jq .

# 3. Valid rows release immediately; the defective row stays staged.
curl -sf -X POST "$BASE/api/v1/remediation/manifests/$RUN/release" -H "$AUTH" -d '{}' \
  -H 'Content-Type: application/json' | jq .

# 4. Issue the scoped correction link (token shown exactly once; only its
#    hash is stored). A notification entry lands in the outbox, queued for
#    email delivery by the drainer (delivery.py).
curl -sf -X POST "$BASE/api/v1/remediation/cases/$CASE/link" -H "$AUTH" \
  -H 'Content-Type: application/json' \
  -d "{\"supplier_email\": \"$SUPPLIER_EMAIL\"}" | tee /tmp/link.json
TOKEN=$(jq -r .token /tmp/link.json)
curl -sf "$BASE/api/v1/remediation/outbox" -H "$AUTH" | jq '.notifications[0]'

# 5. Supplier opens the link. In a browser that is the self-contained form
#    page at $BASE/api/v1/remediation/supplier/form#<token> — the token
#    rides in the URL FRAGMENT, which browsers never send to the server,
#    so it cannot land in access logs. The API equivalent (non-consuming):
curl -sf -X POST "$BASE/api/v1/remediation/supplier/context" \
  -H 'Content-Type: application/json' -d "{\"token\": \"$TOKEN\"}" | jq .

# 6. … explicitly starts the SINGLE-USE 30-minute correction session
#    (a second exchange fails; recovery = buyer reissues the link) …
SESSION=$(curl -sf -X POST "$BASE/api/v1/remediation/supplier/exchange" \
  -H 'Content-Type: application/json' -d "{\"token\": \"$TOKEN\"}" | jq -r .session_token)

# 7. … and submits the attested correction. RegEngine appends the patch,
#    revalidates only this record, and releases it on pass.
curl -sf -X POST "$BASE/api/v1/remediation/supplier/session/corrections" \
  -H "Authorization: Bearer $SESSION" -H 'Content-Type: application/json' -d '{
    "changes": {"kdes.tlc_source_reference": "YOUR_TLC_SOURCE_REFERENCE"},
    "actor_name": "YOUR_NAME",
    "actor_role": "YOUR_ROLE",
    "reason": "TLC source omitted from our export",
    "attestation": {"text": "I attest this correction is accurate.", "accepted": true}
  }' | jq .

# 8. Evidence bundle: original bytes + accepted CSV + hash manifest.
#    Re-download and compare record hashes — they are identical.
curl -sf "$BASE/api/v1/remediation/manifests/$RUN/evidence" -H "$AUTH" -o /tmp/evidence.zip
unzip -p /tmp/evidence.zip manifest.json | jq '.records[].record_hash'

# 9. Metrics — the pilot headline number.
curl -sf "$BASE/api/v1/remediation/metrics" -H "$AUTH" \
  | jq '{resolved_without_buyer_intervention_rate, supplier_corrections_submitted}'
```
