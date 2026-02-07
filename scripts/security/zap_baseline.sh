#!/usr/bin/env bash
set -euo pipefail

if [ -z "${ZAP_TARGET:-}" ]; then
  echo "ERROR: ZAP_TARGET is not set. Add it as a GitHub Secret."
  exit 1
fi

mkdir -p artifacts/zap

echo "Starting ZAP baseline scan against: $ZAP_TARGET"

set +e
docker run --rm -t \
  -v "$(pwd)/artifacts/zap:/zap/wrk:rw" \
  ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py \
    -t "$ZAP_TARGET" \
    -r zap_report.html \
    -J zap_report.json \
    -w zap_warnings.md \
    -x zap_report.xml

EXIT_CODE=$?
set -e

echo "ZAP baseline completed with exit code: $EXIT_CODE"
echo "Reports saved to artifacts/zap/"

# Exit code 0 = pass (no alerts)
# Exit code 1 = warnings only (acceptable for baseline)
# Exit code 2+ = failures (real findings — fail CI)
if [ "$EXIT_CODE" -gt 1 ]; then
  echo "FAIL: ZAP found HIGH or above alerts. Review artifacts/zap/zap_report.html"
  exit 1
fi

echo "PASS: ZAP baseline scan completed within acceptable thresholds."
exit 0
