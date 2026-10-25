import { API_BASE } from '@/lib/api-base';

/**
 * Code samples for `POST /webhooks/ingest`.
 *
 * No sample carries an example record: a lot code, supplier, or quantity
 * printed in the docs reads as real data, and an accepted lot is permanent.
 * The body below is a skeleton of angle-bracket field descriptions to fill
 * with your own records. `{{EVENT_TIMESTAMP}}` / `{{EVENT_DATE}}` stay
 * placeholders so no page can ship a timestamp that goes stale (events older
 * than 90 days are rejected); each sample swaps them for a clock expression
 * in its own language.
 */
const TIMESTAMP_PLACEHOLDER = '"{{EVENT_TIMESTAMP}}"';
const DATE_PLACEHOLDER = '"{{EVENT_DATE}}"';

/** The two values RegEngine issues, as placeholders. Shown above the call in the quickstart and developers page. */
export const INGEST_ENV_SETUP = [
  'export REGENGINE_API_KEY="rge_live_..."      # from RegEngine', // pragma: allowlist secret
  'export REGENGINE_SIGNING_SECRET="..."       # from RegEngine', // pragma: allowlist secret
].join('\n');

/** Request-body skeleton: field names are real, every value is a `<...>` description to replace with your own record. */
const INGEST_BODY_SKELETON = {
  source: '<your source system id>',
  events: [
    {
      cte_type: 'receiving',
      traceability_lot_code: '<the lot code you assigned>',
      product_description: '<product name>',
      quantity: '<number greater than 0>',
      unit_of_measure: '<cases | lbs | kg | pallets | each>',
      location_name: '<your facility name>',
      timestamp: '{{EVENT_TIMESTAMP}}',
      kdes: {
        receive_date: '{{EVENT_DATE}}',
        receiving_location: '<where the lot arrived>',
        immediate_previous_source: '<who sent it to you>',
        reference_document: '<your ASN or receipt id>',
        tlc_source_reference: '<the lot reference your supplier gave you>',
      },
    },
  ],
};

/** The skeleton as text, with each quoted placeholder replaced by `timestamp` / `date` verbatim. */
export function ingestSamplePayload(timestamp: string, date: string, payload: object = INGEST_BODY_SKELETON): string {
  return JSON.stringify(payload, null, 2)
    .split(TIMESTAMP_PLACEHOLDER)
    .join(timestamp)
    .split(DATE_PLACEHOLDER)
    .join(date);
}

/** The signed `curl` call for one payload: builds the clock values, signs the exact bytes, sends them with --data-binary. */
function signedCurl(payload: object): string {
  return `NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TODAY=$(date -u +%Y-%m-%d)

BODY=$(cat <<EOF
${ingestSamplePayload('"$NOW"', '"$TODAY"', payload)}
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
}

export const INGEST_CURL_SAMPLE = signedCurl(INGEST_BODY_SKELETON);

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

/** What a 200 looks like when the event is accepted. Values are `<...>` descriptions of what the API returns, not example records. */
export const INGEST_RESPONSE_SAMPLE = `{
  "accepted": 1,
  "rejected": 0,
  "total": 1,
  "events": [
    {
      "traceability_lot_code": "<the lot code you sent>",
      "cte_type": "receiving",
      "status": "accepted",
      "event_id": "<event UUID>",
      "sha256_hash": "<event hash>",
      "chain_hash": "<chain hash>",
      "errors": []
    }
  ],
  "ingestion_timestamp": "<server time, ISO 8601>",
  "ingestion_run_id": null
}`;
