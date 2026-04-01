#!/usr/bin/env bash
set -euo pipefail

# FSMA-only runtime: keep local stack small during pilot work.
# --remove-orphans stops non-FSMA services from previous full-stack runs.
ENABLE_OTEL=false docker compose up -d --remove-orphans postgres redis admin-api ingestion-service

echo "FSMA stack started: postgres, redis, admin-api, ingestion-service"
