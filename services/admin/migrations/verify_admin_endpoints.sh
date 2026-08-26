#!/usr/bin/env bash
set -euo pipefail

# Manual high-assurance admin verification. Capture a short-lived opaque
# session from a WebAuthn/SSO-authenticated staff browser and pass only the
# cookie value to this process. Never persist it in this repository.
BASE_URL="${ADMIN_BASE_URL:-http://localhost:8400/v1}"
STAFF_SESSION_COOKIE="${REGENGINE_STAFF_SESSION_COOKIE:-}"

if [ -z "$STAFF_SESSION_COOKIE" ]; then
  echo "REGENGINE_STAFF_SESSION_COOKIE is required (WebAuthn/SSO sysadmin session)."
  exit 2
fi

case "$BASE_URL" in
  http://localhost:*|http://127.0.0.1:*|http://[::1]:*|https://*)
    ;;
  *)
    echo "Refusing to send __Host-regengine_session over non-HTTPS to $BASE_URL"
    exit 2
    ;;
esac

cookie_header="__Host-regengine_session=$STAFF_SESSION_COOKIE"

echo "1. Verifying unauthenticated rejection..."
unauthenticated_status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/admin/keys")
if [ "$unauthenticated_status" != "401" ]; then
  echo "Expected 401, got $unauthenticated_status"
  exit 1
fi

echo "2. Verifying high-assurance staff key listing..."
authenticated_status=$(curl -s -o /dev/null -w "%{http_code}" \
  "$BASE_URL/admin/keys" \
  -H "Cookie: $cookie_header")
if [ "$authenticated_status" != "200" ]; then
  echo "Expected 200, got $authenticated_status"
  exit 1
fi

echo "3. Verifying tenant-scoped review queue read..."
review_status=$(curl -s -o /dev/null -w "%{http_code}" \
  "$BASE_URL/admin/review/flagged-extractions?status=PENDING" \
  -H "Cookie: $cookie_header")
if [ "$review_status" != "200" ]; then
  echo "Expected 200, got $review_status"
  exit 1
fi

echo "Admin session and review permissions verified."
