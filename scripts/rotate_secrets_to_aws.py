#!/usr/bin/env python3
"""Prepare a deployable secrets bundle from local environment values.

This script reads secrets from environment variables or a local .env file,
validates required values, and optionally writes a JSON bundle for upload to
your deployment platform's variable manager.

Usage:
    python scripts/rotate_secrets_to_aws.py --environment production
    python scripts/rotate_secrets_to_aws.py --environment staging --output secrets.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


REQUIRED_SECRETS = (
    "POSTGRES_PASSWORD",
    "NEO4J_PASSWORD",
    "ADMIN_MASTER_KEY",
    "OBJECT_STORAGE_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
)


def load_environment(env_file: str) -> None:
    """Load environment variables from a .env file when available."""
    if load_dotenv is None:
        print("WARNING: python-dotenv is not installed; using current shell environment only.")
        return

    env_path = Path(env_file)
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded environment from {env_file}")
    else:
        print(f"{env_file} not found; using current shell environment only")


def build_secret_payload(environment: str) -> dict[str, str]:
    """Collect platform secrets and return a normalized payload."""
    payload = {
        "ENVIRONMENT": environment,
        "POSTGRES_USER": os.getenv("POSTGRES_USER", "postgres"),
        "POSTGRES_PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "POSTGRES_HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "POSTGRES_PORT": os.getenv("POSTGRES_PORT", "5432"),
        "POSTGRES_DB": os.getenv("POSTGRES_DB", "regengine"),
        "NEO4J_URI": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        "NEO4J_USER": os.getenv("NEO4J_USER", "neo4j"),
        "NEO4J_PASSWORD": os.getenv("NEO4J_PASSWORD", ""),
        "KAFKA_BOOTSTRAP_SERVERS": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        "KAFKA_USERNAME": os.getenv("KAFKA_USERNAME", ""),
        "KAFKA_PASSWORD": os.getenv("KAFKA_PASSWORD", ""),
        "KAFKA_SECURITY_PROTOCOL": os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
        "OBJECT_STORAGE_ACCESS_KEY_ID": os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID", ""),
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY", ""),
        "OBJECT_STORAGE_REGION": os.getenv("OBJECT_STORAGE_REGION", "us-east-1"),
        "OBJECT_STORAGE_ENDPOINT_URL": os.getenv("OBJECT_STORAGE_ENDPOINT_URL", ""),
        "ADMIN_MASTER_KEY": os.getenv("ADMIN_MASTER_KEY", ""),
    }
    return payload


def validate_payload(payload: dict[str, str]) -> list[str]:
    """Return missing required secret keys."""
    return [name for name in REQUIRED_SECRETS if not payload.get(name)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare RegEngine secrets for platform deployment")
    parser.add_argument("--environment", required=True, choices=["production", "staging", "dev"])
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--output", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("RegEngine Secrets Bundle Preparation")
    print("=" * 60)
    print(f"Environment: {args.environment}")
    print(f"Dry Run: {args.dry_run}")
    print("=" * 60)

    load_environment(args.env_file)
    payload = build_secret_payload(args.environment)
    missing = validate_payload(payload)

    if missing:
        print("\nERROR: Missing required secret values:")
        for key in missing:
            print(f"  - {key}")
        sys.exit(1)

    print("\nAll required secrets are present.")

    if args.dry_run:
        print("\nDry run complete. No files written.")
        print("Keys prepared:")
        for key in sorted(payload.keys()):
            print(f"  - {key}")
        return

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nWrote secrets bundle to {output_path}")
    else:
        print("\nNo output file specified. Use --output to write JSON.")

    print("\nNext steps:")
    print("1. Upload values to Railway Variables (or your managed secret store)")
    print("2. Verify production startup with REGENGINE_ENV=production")
    print("3. Remove local .env from deployment hosts")


if __name__ == "__main__":
    main()
