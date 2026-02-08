
import asyncio
import os
import uuid
from sqlalchemy import text
from shared.api_key_store import DatabaseAPIKeyStore

# Read DATABASE_URL from environment — do NOT hardcode credentials
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get(
    "ADMIN_DATABASE_URL",
    ""
)
if not DATABASE_URL:
    print("❌ DATABASE_URL or ADMIN_DATABASE_URL must be set in the environment.")
    print("   Example: export DATABASE_URL='postgresql+psycopg://app_user:password@postgres:5432/regengine_admin'")
    exit(1)

os.environ["DATABASE_URL"] = DATABASE_URL

async def debug_rls():
    print("Initializing Store...")
    store = DatabaseAPIKeyStore()
    
    tenant_id = "11111111-1111-1111-1111-111111111111"
    
    print(f"Attempting to create key for tenant: {tenant_id}")
    
    try:
        async with store._session() as session:
            # 1. Set Context
            print("Setting context...")
            await store._set_context(session, tenant_id)
            
            # 2. Verify Context
            result = await session.execute(text("SELECT current_setting('app.tenant_id', true)"))
            current_setting = result.scalar()
            print(f"Current app.tenant_id in DB: {current_setting}")
            
            if current_setting != tenant_id:
                print("❌ Context mismatch!")
            else:
                print("✅ Context matches.")

            # 3. Attempt Key Creation (Raw Insert logic simulation)
            from shared.api_key_store import APIKeyModel
            from datetime import datetime, timezone
            
            key_id = f"debug_{uuid.uuid4().hex[:8]}"
            new_key = APIKeyModel(
                key_id=key_id,
                key_hash="debug_hash",
                key_prefix="debug",
                name="Debug Key",
                tenant_id=tenant_id,
                created_at=datetime.now(timezone.utc),
                enabled=True
            )
            
            print("Adding to session...")
            session.add(new_key)
            
            print("Flushing...")
            await session.flush()
            print("✅ Flush successful (RLS passed).")
            
    except Exception as e:
        print(f"❌ Operation Failed: {e}")
    finally:
        await store.close()

if __name__ == "__main__":
    asyncio.run(debug_rls())
