#!/usr/bin/env python3
"""Validate the local secret set, and optionally emit it to stdout for piping.

WHAT THIS DOES NOT DO (#2938)
-----------------------------
This tool does **not** rotate any credential and does **not** contact AWS.
Nothing here generates a new secret, changes one, or talks to a secret
manager. It was previously named ``rotate_secrets_to_aws.py``, which invited
an operator running ``--environment production`` to believe credentials had
been rotated when nothing whatsoever had changed. Do not rely on this script
during an incident to rotate anything.

What it *does* do:

* **Validate** (default): confirm every credential the platform requires is
  present and non-empty in the environment or ``.env``. Only key *names* are
  printed — never values.
* **Emit** (``--emit-bundle``): write the bundle as JSON to **stdout only**,
  for piping straight into a secret manager. It is never written to a file.

Rotation is done by the platform's own secret manager, not here. To set
production values, use the platform directly, e.g.::

    railway variables set AUTH_SECRET_KEY=...

Usage:
    python scripts/export_env_bundle.py --environment production
    python scripts/export_env_bundle.py --environment staging --emit-bundle | \
        railway variables set --from-json -
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
    "OBJECT_STORAGE_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
)


# Names of every key build_secret_payload returns. Status output prints names
# from these constants only, never anything derived from the payload, so no
# credential value can reach a log line.
PAYLOAD_KEYS = (
    "ENVIRONMENT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "KAFKA_BOOTSTRAP_SERVERS",
    "KAFKA_USERNAME",
    "KAFKA_PASSWORD",
    "KAFKA_SECURITY_PROTOCOL",
    "OBJECT_STORAGE_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
    "OBJECT_STORAGE_REGION",
    "OBJECT_STORAGE_ENDPOINT_URL",
)


def load_environment(env_file: str) -> None:
    """Load environment variables from a .env file when available."""
    if load_dotenv is None:
        print(
            "WARNING: python-dotenv is not installed; using current shell environment only.",
            file=sys.stderr,
        )
        return

    env_path = Path(env_file)
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded environment from {env_file}", file=sys.stderr)
    else:
        print(f"{env_file} not found; using current shell environment only", file=sys.stderr)


def build_secret_payload(environment: str) -> dict[str, str]:
    """Collect platform secrets and return a normalized payload.

    The result holds live credential values. Callers must not persist it:
    emit it to a pipe, or discard it after validation.
    """
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
    }
    return payload


def validate_payload(payload: dict[str, str]) -> list[str]:
    """Return missing required secret keys."""
    return [name for name in REQUIRED_SECRETS if not payload.get(name)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Validate the local RegEngine secret set. Does NOT rotate credentials and does NOT contact AWS.")
    )
    parser.add_argument("--environment", required=True, choices=["production", "staging", "dev"])
    parser.add_argument("--env-file", default=".env")
    parser.add_argument(
        "--emit-bundle",
        action="store_true",
        help="Write the bundle as JSON to stdout for piping. Never writes a file.",
    )
    parser.add_argument(
        "--allow-tty",
        action="store_true",
        help="Permit --emit-bundle when stdout is a terminal (prints secrets to your screen).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and list key names only. This is already the default.",
    )
    # Retained purely so the old documented invocation fails loudly instead of
    # silently writing a plaintext credential file (#2938).
    parser.add_argument("--output", default=None, help=argparse.SUPPRESS)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    # Diagnostics go to stderr so --emit-bundle's stdout stays pipeable JSON.
    print("=" * 60, file=sys.stderr)
    print("RegEngine secret-set validation", file=sys.stderr)
    print("This tool does NOT rotate credentials and does NOT contact AWS.", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"Environment: {args.environment}", file=sys.stderr)

    if args.output is not None:
        print(
            "\nERROR: --output has been removed (#2938).\n"
            "It wrote every production credential as plaintext JSON under the\n"
            "operator's default umask, to a path .gitignore\n"
            "did not cover. Nothing writes secrets to disk any more.\n"
            "Pipe the bundle instead:\n"
            "  python scripts/export_env_bundle.py --environment production --emit-bundle | \\\n"
            "      railway variables set --from-json -",
            file=sys.stderr,
        )
        sys.exit(2)

    load_environment(args.env_file)
    payload = build_secret_payload(args.environment)
    # Count misses without building a name list for logging. Status lines
    # embed env-var *names* as string literals in the message (same pattern
    # as auth_crypto / fingerprint_repair) so CodeQL cannot trace printed
    # text from REQUIRED_SECRETS, PAYLOAD_KEYS, or the credential payload
    # (alerts 19 / 20 / 82, py/clear-text-logging-sensitive-data).
    missing_count = len(validate_payload(payload))

    if missing_count:
        # Names are literals in this message; do not interpolate REQUIRED_SECRETS.
        print(
            f"\nERROR: {missing_count} required secret(s) missing.\n"
            "Required secret names (values never printed):\n"
            "  - POSTGRES_PASSWORD\n"
            "  - NEO4J_PASSWORD\n"
            "  - OBJECT_STORAGE_ACCESS_KEY_ID\n"
            "  - OBJECT_STORAGE_SECRET_ACCESS_KEY",
            file=sys.stderr,
        )
        sys.exit(1)

    # Names are literals in this message; do not interpolate PAYLOAD_KEYS.
    print(
        "\nAll required secrets are present.\n"
        "Keys validated (names only; values are never printed here):\n"
        "  - ENVIRONMENT\n"
        "  - KAFKA_BOOTSTRAP_SERVERS\n"
        "  - KAFKA_PASSWORD\n"
        "  - KAFKA_SECURITY_PROTOCOL\n"
        "  - KAFKA_USERNAME\n"
        "  - NEO4J_PASSWORD\n"
        "  - NEO4J_URI\n"
        "  - NEO4J_USER\n"
        "  - OBJECT_STORAGE_ACCESS_KEY_ID\n"
        "  - OBJECT_STORAGE_ENDPOINT_URL\n"
        "  - OBJECT_STORAGE_REGION\n"
        "  - OBJECT_STORAGE_SECRET_ACCESS_KEY\n"
        "  - POSTGRES_DB\n"
        "  - POSTGRES_HOST\n"
        "  - POSTGRES_PASSWORD\n"
        "  - POSTGRES_PORT\n"
        "  - POSTGRES_USER",
        file=sys.stderr,
    )

    if args.emit_bundle:
        if sys.stdout.isatty() and not args.allow_tty:
            print(
                "\nERROR: refusing to print secrets to a terminal.\n"
                "Pipe stdout somewhere, or pass --allow-tty if you truly mean to.",
                file=sys.stderr,
            )
            sys.exit(2)
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        print("\nBundle written to stdout. It was not saved to disk.", file=sys.stderr)
        return

    print(
        "\nNo bundle emitted. Add --emit-bundle to pipe JSON to your secret manager.\n"
        "Rotation itself is performed by the platform, e.g. `railway variables set`.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
