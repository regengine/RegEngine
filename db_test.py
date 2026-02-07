import asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine
import sys

# DSNs
SYNC_DSN = "postgresql://postgres:trj.qxe_wxh6QGB%40auq@db.magbeerafyxmyuqmbfgv.supabase.co:5432/postgres?sslmode=require"
ASYNC_DSN = "postgresql+asyncpg://postgres:trj.qxe_wxh6QGB%40auq@db.magbeerafyxmyuqmbfgv.supabase.co:5432/postgres"

def test_sync():
    print(f"Testing SYNC connection to: {SYNC_DSN.split('@')[-1]}")
    try:
        engine = create_engine(SYNC_DSN)
        with engine.connect() as conn:
            ver = conn.execute(text("SELECT version();")).fetchone()[0]
            print(f"SYNC SUCCESS: {ver}")
    except Exception as e:
        print(f"SYNC FAILURE: {e}")

async def test_async():
    print(f"Testing ASYNC connection to: {ASYNC_DSN.split('@')[-1]}")
    try:
        # Note: We inject ssl=require manually as we did in the patch
        engine = create_async_engine(ASYNC_DSN, connect_args={"ssl": "require"})
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version();"))
            ver = result.fetchone()[0]
            print(f"ASYNC SUCCESS: {ver}")
    except Exception as e:
        print(f"ASYNC FAILURE: {e}")

if __name__ == "__main__":
    test_sync()
    asyncio.run(test_async())
