import asyncio
import os
import sys
from uuid import uuid4

# Ensure app is in path
sys.path.append("/app")

from shared.api_key_store import get_db_key_store

async def bootstrap():
    print("Bootstrapping Auth...")
    store = await get_db_key_store()
    
    # Create a persistent Tenant ID for testing
    # Using the one referenced in docs/router mocks for consistency
    tenant_id = "40e74bc9-4087-4612-8d94-215347138a68"
    
    # create_key returns APIKeyCreateResponse with .raw_key
    key_resp = await store.create_key(
        name="Remediation-Bootstrap-Key",
        tenant_id=tenant_id,
        billing_tier="ENTERPRISE",
        created_by="system-bootstrap"
    )
    
    print(f"BOOTSTRAP_SUCCESS: {key_resp.raw_key}")
    print(f"TENANT_ID: {tenant_id}")
    
    await store.close()

if __name__ == "__main__":
    asyncio.run(bootstrap())
