import asyncio
import os
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine
import sys

# DSNs — loaded from environment variables
SYNC_DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/postgres?sslmode=require",
)
ASYNC_DSN = os.environ.get(
    "DATABASE_URL_ASYNC",
    SYNC_DSN.replace("postgresql://", "postgresql+asyncpg://").replace("?sslmode=require", ""),
)

def test_sync():
    print(f"Testing SYNC connection to: {SYNC_DSN.split('@')[-1]}")
    try:
        engine = create_engine(SYNC_DSN)
        with engine.connect() as conn:
            row = conn.execute(text("SELECT version();")).fetchone()
            if row is None:
                print("SYNC FAILURE: query returned no rows")
                return
            print(f"SYNC SUCCESS: {row[0]}")
    except Exception as e:
        print(f"SYNC FAILURE: {e}")

async def test_async():
    print(f"Testing ASYNC connection to: {ASYNC_DSN.split('@')[-1]}")
    try:
        # Note: We inject ssl=require manually as we did in the patch
        engine = create_async_engine(ASYNC_DSN, connect_args={"ssl": "require"})
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version();"))
            row = result.fetchone()
            if row is None:
                print("ASYNC FAILURE: query returned no rows")
                return
            print(f"ASYNC SUCCESS: {row[0]}")
    except Exception as e:
        print(f"ASYNC FAILURE: {e}")

if __name__ == "__main__":
    test_sync()
    asyncio.run(test_async())
