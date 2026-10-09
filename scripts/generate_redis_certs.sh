#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# generate_redis_certs.sh — Generate self-signed TLS certs for Redis (#999)
#
# For local dev only. In production, use provider-managed TLS (Railway,
# Upstash, etc.) and set REDIS_URL=rediss://...
#
# The keys below are unencrypted dev-only material. Never commit them: the
# default directory (./certs/redis) is covered by the `certs/` rule in
# .gitignore, and the script refuses to write to any location inside this
# repo that is not gitignored.
#
# Usage:
#   ./scripts/generate_redis_certs.sh
#   CERT_DIR=./certs/redis ./scripts/generate_redis_certs.sh
# ---------------------------------------------------------------------------
set -euo pipefail

CERT_DIR="${CERT_DIR:-./certs/redis}"
mkdir -p "${CERT_DIR}"
chmod 700 "${CERT_DIR}"

if ! command -v openssl >/dev/null 2>&1; then
    echo "error: openssl not found on PATH; install OpenSSL and retry." >&2
    exit 1
fi

# Local-only guard: when CERT_DIR resolves inside this repo's working tree,
# it must be gitignored so unencrypted private keys can never be committed.
# Paths outside the repo (for example under /tmp) are inherently local-only
# and are allowed without the gitignore check.
if command -v git >/dev/null 2>&1 && git rev-parse --show-toplevel >/dev/null 2>&1; then
    REPO_ROOT="$(git rev-parse --show-toplevel)"
    ABS_CERT_DIR="$(cd "${CERT_DIR}" && pwd -P)"
    case "${ABS_CERT_DIR}" in
        "${REPO_ROOT}"/*)
            if ! git check-ignore -q "${ABS_CERT_DIR}/redis.key" >/dev/null 2>&1; then
                echo "error: CERT_DIR='${CERT_DIR}' is inside the repo but not gitignored." >&2
                echo "error: refusing to write unencrypted private keys to a tracked location." >&2
                exit 1
            fi
            ;;
    esac
fi

echo "==> Generating Redis TLS certificates in ${CERT_DIR}..."
echo "    NOTE: these keys are unencrypted and for local dev only; never commit them." >&2

# Generate CA (openssl errors are surfaced, never silenced, so a failed
# cert aborts here instead of looking fine until Redis will not start).
openssl genrsa -out "${CERT_DIR}/ca.key" 4096
openssl req -new -x509 -days 3650 -key "${CERT_DIR}/ca.key" \
    -out "${CERT_DIR}/ca.crt" -subj "/CN=RegEngine-Redis-CA"

# Generate server cert
openssl genrsa -out "${CERT_DIR}/redis.key" 2048
openssl req -new -key "${CERT_DIR}/redis.key" \
    -out "${CERT_DIR}/redis.csr" -subj "/CN=redis"
openssl x509 -req -days 3650 -in "${CERT_DIR}/redis.csr" \
    -CA "${CERT_DIR}/ca.crt" -CAkey "${CERT_DIR}/ca.key" \
    -CAcreateserial -out "${CERT_DIR}/redis.crt"

rm -f "${CERT_DIR}/redis.csr" "${CERT_DIR}/ca.srl"
chmod 600 "${CERT_DIR}"/*.key

# Verify the artifacts now, while the failure is cheap and attributable,
# instead of surfacing later as "Redis will not start".
openssl x509 -in "${CERT_DIR}/ca.crt" -noout -subject
openssl x509 -in "${CERT_DIR}/redis.crt" -noout -subject
openssl verify -CAfile "${CERT_DIR}/ca.crt" "${CERT_DIR}/redis.crt"
KEY_MODULUS="$(openssl rsa -in "${CERT_DIR}/redis.key" -modulus -noout)"
CERT_MODULUS="$(openssl x509 -in "${CERT_DIR}/redis.crt" -modulus -noout)"
if [ "${KEY_MODULUS}" != "${CERT_MODULUS}" ]; then
    echo "error: redis.key does not match redis.crt; certificates are unusable." >&2
    exit 1
fi

echo "==> Redis TLS certs generated:"
ls -la "${CERT_DIR}"
echo ""
echo "Run 'docker compose up -d redis' to start Redis with TLS."
echo "Clients should use rediss://redis:6379 (note the double 's')."
