import { API_BASE } from '@/lib/api-base';
import ingestReceiving from './ingest-receiving.json';

/**
 * Code samples for `POST /webhooks/ingest`, all rendered from one payload.
 *
 * `ingest-receiving.json` keeps two placeholders instead of dates, so no page
 * can ship a timestamp that goes stale (events older than 90 days are
 * rejected). Each sample below swaps them for a time expression in its own
 * language. `tests/docs/test_ingest_samples_validate.py` fills the same
 * placeholders with "now minus 1 hour" and runs the payload through the
 * backend's real ingest checks.
 */
const TIMESTAMP_PLACEHOLDER = '"{{EVENT_TIMESTAMP}}"';
const DATE_PLACEHOLDER = '"{{EVENT_DATE}}"';

/** The two values RegEngine issues, as placeholders. Shown above the call in the quickstart and developers page. */
export const INGEST_ENV_SETUP = [
  'export REGENGINE_API_KEY="rge_live_..."      # from RegEngine', // pragma: allowlist secret
  'export REGENGINE_SIGNING_SECRET="..."       # from RegEngine', // pragma: allowlist secret
].join('\n');

/** The shared payload as text, with each quoted placeholder replaced by `timestamp` / `date` verbatim. */
export function ingestSamplePayload(timestamp: string, date: string): string {
  return JSON.stringify(ingestReceiving, null, 2)
    .split(TIMESTAMP_PLACEHOLDER)
    .join(timestamp)
    .split(DATE_PLACEHOLDER)
    .join(date);
}

export const INGEST_CURL_SAMPLE = `NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TODAY=$(date -u +%Y-%m-%d)

BODY=$(cat <<EOF
${ingestSamplePayload('"$NOW"', '"$TODAY"')}
EOF
)

# Sign the exact bytes you send: sha256= plus the HMAC-SHA256 hex digest.
SIGNATURE="sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$REGENGINE_SIGNING_SECRET" -hex | sed 's/^.* //')"

curl -X POST ${API_BASE}/webhooks/ingest \\
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY" \\
  -H "X-Webhook-Signature: $SIGNATURE" \\
  -H "Idempotency-Key: $(uuidgen)" \\
  -H "Content-Type: application/json" \\
  --data-binary "$BODY"`;

export const INGEST_PYTHON_SAMPLE = `import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone

import requests

now = datetime.now(timezone.utc)
payload = ${ingestSamplePayload('now.strftime("%Y-%m-%dT%H:%M:%SZ")', 'now.strftime("%Y-%m-%d")')}

# Sign the exact bytes you send: sha256= plus the HMAC-SHA256 hex digest.
body = json.dumps(payload).encode()
signature = "sha256=" + hmac.new(
    os.environ["REGENGINE_SIGNING_SECRET"].encode(), body, hashlib.sha256
).hexdigest()

resp = requests.post(
    "${API_BASE}/webhooks/ingest",
    headers={
        "X-RegEngine-API-Key": os.environ["REGENGINE_API_KEY"],
        "X-Webhook-Signature": signature,
        "Idempotency-Key": str(uuid.uuid4()),
        "Content-Type": "application/json",
    },
    data=body,
)
print(resp.status_code, resp.json())`;

export const INGEST_JS_SAMPLE = `import { createHmac, randomUUID } from "node:crypto";

const now = new Date().toISOString().replace(/\\.\\d{3}Z$/, "Z");
const payload = ${ingestSamplePayload('now', 'now.slice(0, 10)')};

// Sign the exact bytes you send: sha256= plus the HMAC-SHA256 hex digest.
const body = JSON.stringify(payload);
const signature =
  "sha256=" + createHmac("sha256", process.env.REGENGINE_SIGNING_SECRET).update(body).digest("hex");

const resp = await fetch("${API_BASE}/webhooks/ingest", {
  method: "POST",
  headers: {
    "X-RegEngine-API-Key": process.env.REGENGINE_API_KEY,
    "X-Webhook-Signature": signature,
    "Idempotency-Key": randomUUID(),
    "Content-Type": "application/json",
  },
  body,
});
console.log(resp.status, await resp.json());`;

/** What a 200 looks like when the event is accepted. Hashes are shortened. */
export const INGEST_RESPONSE_SAMPLE = `{
  "accepted": 1,
  "rejected": 0,
  "total": 1,
  "events": [
    {
      "traceability_lot_code": "${ingestReceiving.events[0].traceability_lot_code}",
      "cte_type": "receiving",
      "status": "accepted",
      "event_id": "0b9c2f4e-6d1a-4c53-9a7e-5f3d8e21c7ab",
      "sha256_hash": "a3f2b891c4d5e6f7...",
      "chain_hash": "7f6e5d4c3b2a1908...",
      "errors": []
    }
  ],
  "ingestion_timestamp": "2026-10-03T14:05:12.481203+00:00",
  "ingestion_run_id": null
}`;
