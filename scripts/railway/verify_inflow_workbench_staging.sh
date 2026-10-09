#!/usr/bin/env bash
set -euo pipefail

# Verifies the Inflow Workbench production path after a Railway staging deploy.
# Required:
#   DATABASE_URL   Railway Postgres URL
#   INGESTION_URL  Public ingestion-service URL, for example https://...up.railway.app
# Optional:
#   REGENGINE_API_KEY  Added as X-RegEngine-API-Key when set
#   TENANT_ID          UUID tenant to use for the smoke run

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required" >&2
  exit 2
fi

if [[ -z "${INGESTION_URL:-}" ]]; then
  echo "INGESTION_URL is required" >&2
  exit 2
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "psql is required" >&2
  exit 2
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required" >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 2
fi

TENANT_ID="${TENANT_ID:-11111111-1111-4111-8111-111111111111}"
INGESTION_URL="${INGESTION_URL%/}"
AUTH_ARGS=()
if [[ -n "${REGENGINE_API_KEY:-}" ]]; then
  AUTH_ARGS=(-H "X-RegEngine-API-Key: ${REGENGINE_API_KEY}")
fi
RUN_ID=""

# Print a truncated, secret-redacted copy of a response body to stderr, so
# full error payloads (which can echo credentials or connection details)
# never land in logs verbatim.
print_error_body() {
  local file=$1
  local max_bytes=${2:-2000}
  python3 - "$file" "$max_bytes" >&2 <<'PY'
import re
import sys

path, limit = sys.argv[1], int(sys.argv[2])
try:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        body = fh.read()
except OSError as exc:
    print(f"(could not read error body: {exc})")
    raise SystemExit

truncated = len(body) > limit
body = body[:limit]
body = re.sub(
    r"(?i)((?:api[_-]?key|x-regengine-api-key|client[_-]?secret|passwd|password|token)[\"']?\s*[:=]\s*[\"']?)([^\"'\s,};&]+)",
    r"\1[REDACTED]",
    body,
)
body = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", body)
print(body)
if truncated:
    print(f"(error body truncated to {limit} bytes)")
PY
}

# Best-effort removal of synthetic verifier rows. The runs and commit
# decision tables are append-only by schema design (BEFORE UPDATE OR DELETE
# triggers), so those probe rows are retained as audit evidence; the fix
# items table permits deletion and is cleaned here. Never fails the run.
cleanup_probe_rows() {
  if [[ -z "${RUN_ID:-}" ]]; then
    return 0
  fi
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -v tenant_id="$TENANT_ID" -v run_id="$RUN_ID" -tAc "
    SELECT set_config('app.tenant_id', :'tenant_id', true);
    DELETE FROM fsma.inflow_workbench_fix_items
    WHERE tenant_id = :'tenant_id'::uuid AND run_id = :'run_id';
  " > /dev/null 2>&1 || echo "warning: probe cleanup for run ${RUN_ID} failed; synthetic fix items may remain" >&2
}

echo "==> Checking Inflow Workbench tables"
tables_ready="$(
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -tAc "
    SELECT
      to_regclass('fsma.inflow_workbench_runs') IS NOT NULL
      AND to_regclass('fsma.inflow_workbench_fix_items') IS NOT NULL
      AND to_regclass('fsma.inflow_workbench_commit_decisions') IS NOT NULL;
  " | tr -d '[:space:]'
)"
if [[ "$tables_ready" != "t" ]]; then
  echo "Inflow Workbench tables are missing. Apply Alembic v073 / V067 SQL first." >&2
  exit 1
fi

echo "==> Checking append-only and no-truncate triggers"
trigger_count="$(
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -tAc "
    SELECT count(*)
    FROM pg_trigger
    WHERE tgname IN (
      'trg_inflow_runs_append_only',
      'trg_inflow_commit_decisions_append_only',
      'trg_inflow_runs_no_truncate',
      'trg_inflow_commit_decisions_no_truncate'
    );
  " | tr -d '[:space:]'
)"
if [[ "$trigger_count" != "4" ]]; then
  echo "Expected 4 Inflow Workbench evidence triggers, found ${trigger_count}." >&2
  exit 1
fi

payload_file="$(mktemp)"
response_file="$(mktemp)"
summary_file="$(mktemp)"
trap 'cleanup_probe_rows; rm -f "$payload_file" "$response_file" "$summary_file"' EXIT

python3 - "$TENANT_ID" > "$payload_file" <<'PY'
import json
import sys

tenant_id = sys.argv[1]
payload = {
    "tenant_id": tenant_id,
    "source": "railway-staging-verifier",
    "csv": "cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,ship_from_location,ship_to_location,reference_document\nshipping,TLC-STAGING-VERIFY,Romaine Lettuce,12,cases,Salinas Dock,2026-04-30T10:00:00Z,Salinas Packhouse,Bay Area DC,BOL-STAGING-VERIFY",
    "result": {
        "total_events": 1,
        "compliant_events": 1,
        "non_compliant_events": 0,
        "total_kde_errors": 0,
        "total_rule_failures": 0,
        "submission_blocked": False,
        "blocking_reasons": [],
        "duplicate_warnings": [],
        "entity_warnings": [],
        "normalizations": [],
        "events": [
            {
                "event_index": 0,
                "cte_type": "shipping",
                "traceability_lot_code": "TLC-STAGING-VERIFY",
                "product_description": "Romaine Lettuce",
                "kde_errors": [],
                "rules_evaluated": 1,
                "rules_passed": 1,
                "rules_failed": 0,
                "rules_warned": 0,
                "compliant": True,
                "blocking_defects": [],
                "all_results": [],
            }
        ],
    },
}
json.dump(payload, sys.stdout)
PY

echo "==> Saving a Workbench run through ingestion-service"
http_code="$(
  curl -sS -o "$response_file" -w "%{http_code}" \
    -X POST "${INGESTION_URL}/api/v1/inflow-workbench/runs" \
    -H "Content-Type: application/json" \
    "${AUTH_ARGS[@]}" \
    --data @"$payload_file"
)"
if [[ "$http_code" != "200" ]]; then
  echo "Save run failed with HTTP ${http_code}" >&2
  print_error_body "$response_file"
  exit 1
fi

RUN_ID="$(python3 - "$response_file" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    print(json.load(fh)["run_id"])
PY
)"
echo "Saved run: ${RUN_ID}"

echo "==> Verifying run and commit decision persisted in Postgres"
persisted_count="$(
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -v tenant_id="$TENANT_ID" -v run_id="$RUN_ID" -tAc "
    SELECT set_config('app.tenant_id', :'tenant_id', true);
    SELECT
      (
        SELECT count(*) FROM fsma.inflow_workbench_runs
        WHERE tenant_id = :'tenant_id'::uuid AND run_id = :'run_id'
      )
      +
      (
        SELECT count(*) FROM fsma.inflow_workbench_commit_decisions
        WHERE tenant_id = :'tenant_id'::uuid AND run_id = :'run_id'
      );
  " | tail -n 1 | tr -d '[:space:]'
)"
if [[ "$persisted_count" != "2" ]]; then
  echo "Expected persisted run + commit decision, found count ${persisted_count}." >&2
  exit 1
fi

echo "==> Checking readiness summary endpoint"
http_code="$(
  curl -sS -o "$summary_file" -w "%{http_code}" \
    "${INGESTION_URL}/api/v1/inflow-workbench/readiness/summary?tenant_id=${TENANT_ID}" \
    "${AUTH_ARGS[@]}"
)"
if [[ "$http_code" != "200" ]]; then
  echo "Readiness summary failed with HTTP ${http_code}" >&2
  print_error_body "$summary_file"
  exit 1
fi

python3 - "$summary_file" "$RUN_ID" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    summary = json.load(fh)

expected_run_id = sys.argv[2]
if summary.get("run_id") != expected_run_id:
    raise SystemExit(f"summary run_id mismatch: {summary.get('run_id')} != {expected_run_id}")
if not isinstance(summary.get("score"), int):
    raise SystemExit(f"summary score is not an int: {summary.get('score')!r}")
print(f"Readiness score: {summary['score']} ({summary.get('label')})")
PY

echo "Inflow Workbench staging verification passed."
