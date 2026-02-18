import os
import random
import time
import threading
import asyncio
import structlog
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from contextlib import contextmanager, asynccontextmanager
from prometheus_client import Gauge

logger = structlog.get_logger("shared.database")

# Prometheus Metrics
db_circuit_breaker_state = Gauge("db_circuit_breaker_state", "0=closed, 1=open, 2=half_open")
db_pool_checkedout = Gauge("db_pool_checkedout", "Active connections")
db_pool_overflow = Gauge("db_pool_overflow", "Overflow connections")

# Resilience Parameters
BULKHEAD_LIMIT = int(os.getenv("DB_BULKHEAD_LIMIT", "20"))
sync_bulkhead = threading.Semaphore(BULKHEAD_LIMIT)
async_bulkhead = asyncio.Semaphore(BULKHEAD_LIMIT)

class CircuitBreaker:
    def __init__(self, failure_threshold=5, base_recovery=30, backoff_factor=2):
        self.failure_threshold = failure_threshold
        self.base_recovery = base_recovery
        self.backoff_factor = backoff_factor
        self.failure_count = 0
        self.last_failure = 0
        self.state = "CLOSED"

    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            elapsed = time.time() - self.last_failure
            recovery = self.base_recovery * (self.backoff_factor ** self.failure_count)
            if elapsed > recovery:
                self.state = "HALF_OPEN"
                db_circuit_breaker_state.set(2)
            else:
                db_circuit_breaker_state.set(1)
                raise Exception(f"Circuit breaker OPEN (cooling for {int(recovery - elapsed)}s)")
        try:
            result = func(*args, **kwargs) if callable(func) else func
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
            self.failure_count = 0
            db_circuit_breaker_state.set(0)
            return result
        except OperationalError:
            self.failure_count += 1
            self.last_failure = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                db_circuit_breaker_state.set(1)
            raise

def retry_with_jitter(func, max_retries=3, base_delay=0.1):
    """Execute function with exponential backoff and 20% jitter."""
    for attempt in range(max_retries):
        try:
            return func()
        except OperationalError:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt) * (1 + random.uniform(-0.2, 0.2))
            logger.warning("database_retry", attempt=attempt+1, delay=delay)
            time.sleep(delay)

# Engine initialization
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://regengine:regengine@postgres:5432/regengine")
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600
)

db_pool_checkedout.set_function(lambda: engine.pool.checkedout())
db_pool_overflow.set_function(lambda: engine.pool.overflow())

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
circuit_breaker = CircuitBreaker()

@contextmanager
def get_db():
    """Sync session generator with bulkhead, circuit breaker, and retry logic."""
    with sync_bulkhead:
        db = SessionLocal()
        try:
            yield retry_with_jitter(lambda: circuit_breaker.call(db))
        finally:
            db.close()

@asynccontextmanager
async def get_db_async():
    """Async session generator with bulkhead, circuit breaker, and retry logic."""
    async with async_bulkhead:
        db = SessionLocal()
        try:
            # Note: Underlying logic is still sync as SQLAlchemy engine here is sync
            yield retry_with_jitter(lambda: circuit_breaker.call(db))
        finally:
            db.close()
