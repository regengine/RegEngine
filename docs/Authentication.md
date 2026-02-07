# Authentication

## Overview

RegEngine uses API‑key based authentication for all FSMA endpoints. The key is **never stored in plain text** – only a SHA‑256 hash is persisted in the PostgreSQL `api_keys` table (shared via `shared/api_key_store.py`).

## Generating a New Key

```bash
# From the project root
python scripts/create_api_key.py [--tenant TENANT_ID] [--name "Key Name"]
```

The script prints:
- **Raw key** – the value you must pass in the `X‑API‑KEY` header when calling the API. **Store this securely**; it will not be recoverable from the database.
- **Key hash** – the SHA‑256 hash you need to insert into the database.
- **Key ID**, **Tenant ID**, **Name**, and **Created‑at** timestamp.

## Inserting the Key Manually (PostgreSQL)

```sql
INSERT INTO api_keys (
    key_id,
    key_hash,
    key_prefix,
    name,
    tenant_id,
    created_at,
    enabled
) VALUES (
    '<key_id>',
    '<key_hash>',
    substr('<raw_key>', 1, 12),
    '<name>',
    '<tenant_id>',
    now(),
    true
);
```
Replace the placeholders with the values printed by `create_api_key.py`.

## Rotating a Key
1. Generate a new key with a new name/tenant if needed.
2. Insert the new key as above.
3. Re‑configure any clients to use the new raw key.
4. (Optional) Revoke the old key via the admin API:
   ```bash
   curl -X POST -H "X‑API‑KEY: <admin‑key>" \
        http://localhost:8200/admin/api-keys/revoke/<old_key_id>
   ```

## Using the Key in Requests
All FSMA endpoints require the header:
```
X-API-KEY: <raw_key>
```
If the header is missing or the key is invalid you will receive **401 Unauthorized**.

## Security Recommendations
- Store the raw key in a secret manager (e.g., AWS Secrets Manager, HashiCorp Vault).
- Rotate keys at least every 90 days.
- Limit each key to a single tenant and minimal scopes.
- Enable audit logging (already provided by `shared/api_key_store.py`).
