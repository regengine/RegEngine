#!/usr/bin/env bash
set -euo pipefail

# FSMA-only runtime: keep local stack small during pilot work.
# --remove-orphans stops non-FSMA services from previous full-stack runs.
docker compose -f docker-compose.fsma.yml up -d --remove-orphans

echo "FSMA stack started: postgres, redis, admin-api, ingestion-service"
