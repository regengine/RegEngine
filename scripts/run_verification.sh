#!/bin/bash
# Step-by-step FSMA verification: seed V1, ingest live content, check lineage.
#
# Each stage runs only after the previous stage has been verified:
# the stage command must exit zero AND a readiness poll must observe the
# expected evidence (the run's document in the Admin API) before advancing.
# Polls have deadlines and fail loudly instead of sleeping a fixed time.
set -euo pipefail

RUN_ID="${1:-$(date +%s)}"
ADMIN_API_URL="${ADMIN_API_URL:-http://localhost:8400}"
SEED_TIMEOUT_SECS="${SEED_TIMEOUT_SECS:-120}"
LIVE_TIMEOUT_SECS="${LIVE_TIMEOUT_SECS:-180}"
POLL_INTERVAL_SECS="${POLL_INTERVAL_SECS:-5}"

echo "Starting Verification Run: $RUN_ID"

# Poll the Admin API until a document for this run appears, or give up
# after the deadline. Emits nothing on success; explains itself on failure.
wait_for_run_document() {
  local run_id="$1"
  local timeout_secs="$2"
  local deadline=$(( $(date +%s) + timeout_secs ))
  echo "Waiting up to ${timeout_secs}s for run ${run_id} evidence..."
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if curl -fsS --max-time 10 "${ADMIN_API_URL}/pcos/authorities?limit=1000" 2>/dev/null \
      | grep -q -F "run=${run_id}"; then
      echo "Evidence observed for run ${run_id}."
      return 0
    fi
    sleep "$POLL_INTERVAL_SECS"
  done
  echo "ERROR: timed out after ${timeout_secs}s waiting for run ${run_id} evidence." >&2
  return 1
}

echo "----------------------------------------"
echo "Step 1: Seeding V1 Data (Old World)"
if ! python3 scripts/seed_v1_data.py "$RUN_ID"; then
  echo "ERROR: Step 1 failed (seed V1 data). Aborting before live verification." >&2
  exit 1
fi
if ! wait_for_run_document "$RUN_ID" "$SEED_TIMEOUT_SECS"; then
  echo "ERROR: Step 1 verification failed (seeded document never appeared). Aborting." >&2
  exit 1
fi

echo "----------------------------------------"
echo "Step 2: Live Verification (New World Ingestion)"
if ! python3 scripts/verify_live_freshness.py "$RUN_ID"; then
  echo "ERROR: Step 2 failed (live verification). Aborting before lineage check." >&2
  exit 1
fi
if ! wait_for_run_document "$RUN_ID" "$LIVE_TIMEOUT_SECS"; then
  echo "ERROR: Step 2 verification failed (live document never appeared). Aborting." >&2
  exit 1
fi

echo "----------------------------------------"
echo "Step 3: Lineage Verification"
if ! python3 scripts/verify_compliance_lineage.py "$RUN_ID"; then
  echo "ERROR: Step 3 failed (lineage verification)." >&2
  exit 1
fi

echo "----------------------------------------"
echo "FULL VERIFICATION SUCCESSFUL"
