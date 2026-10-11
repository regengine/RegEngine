"""DEPRECATED — prefer scripts/create_test_api_key.py for test keys.

This script assumes the legacy container layout (hardcoded /app on sys.path)
and a pre-existing tenant row. The replacement works from any checkout, seeds
the tenant and its Redis billing status, defaults keys to a 30-day expiry, and
refuses to run against production. Kept only for the remediation bootstrap
flow it was written for.
"""

import asyncio
import os
import sys
from uuid import uuid4

# Ensure app is in path
sys.path.append("/app")

from shared.api_key_store import get_db_key_store


def public_key_reference(key_resp) -> str:
    """Render an API key creation response for operator stdout without secrets.

    The raw key is shown only at creation time and must never reach logs or
    terminal transcripts. Operators identify the key by its stored prefix;
    the raw value has to be captured by the caller from the response object,
    not from this script's output.
    """
    return f"key_prefix={key_resp.key_prefix}"


async def bootstrap():
    print("Bootstrapping Auth...")
    store = await get_db_key_store()

    # Create a persistent Tenant ID for testing
    # Using the one referenced in docs/router mocks for consistency
    tenant_id = "40e74bc9-4087-4612-8d94-215347138a68"

    # create_key returns APIKeyCreateResponse with .raw_key
    key_resp = await store.create_key(
        name="Remediation-Bootstrap-Key", tenant_id=tenant_id, billing_tier="ENTERPRISE", created_by="system-bootstrap"
    )

    # Never print key_resp.raw_key: it is secret material and stdout is
    # captured in CI/run logs. The raw key is available on the response
    # object to the process that minted it.
    print(f"BOOTSTRAP_SUCCESS: {public_key_reference(key_resp)}")
    print(f"TENANT_ID: {tenant_id}")

    await store.close()


if __name__ == "__main__":
    asyncio.run(bootstrap())
