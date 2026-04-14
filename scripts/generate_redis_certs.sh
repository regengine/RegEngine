#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# generate_redis_certs.sh — Generate self-signed TLS certs for Redis (#999)
#
# For local dev only. In production, use provider-managed TLS (Railway,
# Upstash, etc.) and set REDIS_URL=rediss://...
#
# Usage:
#   ./scripts/generate_redis_certs.sh
#   CERT_DIR=./certs/redis ./scripts/generate_redis_certs.sh
# ---------------------------------------------------------------------------
set -euo pipefail

CERT_DIR="${CERT_DIR:-./certs/redis}"
mkdir -p "${CERT_DIR}"

echo "==> Generating Redis TLS certificates in ${CERT_DIR}..."

# Generate CA
openssl genrsa -out "${CERT_DIR}/ca.key" 4096 2>/dev/null
openssl req -new -x509 -days 3650 -key "${CERT_DIR}/ca.key" \
    -out "${CERT_DIR}/ca.crt" -subj "/CN=RegEngine-Redis-CA" 2>/dev/null

# Generate server cert
openssl genrsa -out "${CERT_DIR}/redis.key" 2048 2>/dev/null
openssl req -new -key "${CERT_DIR}/redis.key" \
    -out "${CERT_DIR}/redis.csr" -subj "/CN=redis" 2>/dev/null
openssl x509 -req -days 3650 -in "${CERT_DIR}/redis.csr" \
    -CA "${CERT_DIR}/ca.crt" -CAkey "${CERT_DIR}/ca.key" \
    -CAcreateserial -out "${CERT_DIR}/redis.crt" 2>/dev/null

rm -f "${CERT_DIR}/redis.csr" "${CERT_DIR}/ca.srl"
chmod 600 "${CERT_DIR}"/*.key

echo "==> Redis TLS certs generated:"
ls -la "${CERT_DIR}"
echo ""
echo "Run 'docker compose up -d redis' to start Redis with TLS."
echo "Clients should use rediss://redis:6379 (note the double 's')."
