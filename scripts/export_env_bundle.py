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
  Full values are only ever written to a pipe. If stdout is a terminal the
  run is refused, and ``--allow-tty`` shows a masked preview (short prefix
  plus fingerprint) instead of the values.

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
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from services.shared.secret_redaction import mask_secret  # noqa: E402

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


# Payload entries that are not credentials and may be shown in the clear.
NON_SECRET_KEYS = frozenset(
    {
        "ENVIRONMENT",
        "POSTGRES_USER",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "NEO4J_URI",
        "NEO4J_USER",
        "KAFKA_BOOTSTRAP_SERVERS",
        "KAFKA_SECURITY_PROTOCOL",
        "OBJECT_STORAGE_REGION",
        "OBJECT_STORAGE_ENDPOINT_URL",
    }
)


def mask_payload(payload: dict[str, str]) -> dict[str, str]:
    """Return a display-safe copy: credential values become prefix + fingerprint."""
    return {
        name: value if name in NON_SECRET_KEYS else mask_secret(value)
        for name, value in payload.items()
    }


def validate_payload(payload: dict[str, str]) -> list[str]:
    """Return missing required secret keys."""
    return [name for name in REQUIRED_SECRETS if not payload.get(name)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the local RegEngine secret set. Does NOT rotate "
            "credentials and does NOT contact AWS."
        )
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
        help=(
            "When stdout is a terminal, show a masked preview of the bundle "
            "instead of refusing. Full values are never printed to a terminal."
        ),
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
    missing = validate_payload(payload)

    if missing:
        print("\nERROR: Missing required secret values:", file=sys.stderr)
        for key in missing:
            print(f"  - {key}", file=sys.stderr)
        sys.exit(1)

    print("\nAll required secrets are present.", file=sys.stderr)
    print("Keys validated (names only; values are never printed here):", file=sys.stderr)
    for key in sorted(payload.keys()):
        print(f"  - {key}", file=sys.stderr)

    if args.emit_bundle:
        stdout_is_tty = sys.stdout.isatty()
        try:
            stdout_mode = os.fstat(sys.stdout.fileno()).st_mode
            stdout_is_pipe = stat.S_ISFIFO(stdout_mode)
        except (OSError, AttributeError, ValueError):
            stdout_is_pipe = False

        if stdout_is_tty:
            if not args.allow_tty:
                print(
                    "\nERROR: refusing to print secrets to a terminal.\n"
                    "Pipe stdout somewhere, or pass --allow-tty for a masked preview.",
                    file=sys.stderr,
                )
                sys.exit(2)
            json.dump(mask_payload(payload), sys.stdout, indent=2)
            sys.stdout.write("\n")
            print(
                "\nMasked preview only. Pipe stdout to a secret manager to emit full values.",
                file=sys.stderr,
            )
            return

        # Regular-file redirects (> bundle.json) are not pipes. Refuse to
        # write full credentials there; documentation says stdout is for piping.
        if not stdout_is_pipe:
            print(
                "\nERROR: refusing to write full secret values to a non-pipe stdout.\n"
                "Pipe into a secret manager, or pass --allow-tty for a masked preview "
                "on a terminal.",
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
