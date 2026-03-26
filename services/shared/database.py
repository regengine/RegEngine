import os
import random
import time
import threading
import asyncio
import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from contextlib import contextmanager, asynccontextmanager
from prometheus_client import Gauge, CollectorRegistry, REGISTRY

logger = structlog.get_logger("shared.database")

# Prometheus Metrics — guard against duplicate registration on re-import
def _safe_gauge(name: str, description: str) -> Gauge:
    """Return existing Gauge if already registered, else create a new one."""
    try:
        return Gauge(name, description)
    except ValueError:
        # Already registered — return the existing collector
        return REGISTRY._names_to_collectors.get(name, Gauge(name, description, registry=None))

db_circuit_breaker_state = _safe_gauge("db_circuit_breaker_state", "0=closed, 1=open, 2=half_open")
db_pool_checkedout = _safe_gauge("db_pool_checkedout", "Active connections")
db_pool_overflow = _safe_gauge("db_pool_overflow", "Overflow connections")

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
_DEV_DATABASE_URL = "postgresql://regengine:regengine@postgres:5432/regengine"
from shared.env import is_production
_is_prod = is_production()
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    if _is_prod:
        raise ValueError(
            "DATABASE_URL environment variable must be set in production. "
            "Refusing to start with default credentials."
        )
    logger.warning(
        "database_url_default",
        msg="DATABASE_URL not set — using dev default. Do NOT use in production.",
    )
    DATABASE_URL = _DEV_DATABASE_URL
engine = create_engine(
    DATABASE_URL,
    pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
    pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
    pool_pre_ping=True,
    pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),
)

db_pool_checkedout.set_function(lambda: engine.pool.checkedout())
db_pool_overflow.set_function(lambda: engine.pool.overflow())

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
circuit_breaker = CircuitBreaker()

@contextmanager
def get_db():
    """Sync session generator with bulkhead, circuit breaker, and retry logic.

    The circuit breaker wraps a lightweight health-check query so that
    persistent DB failures trip the breaker.  The *session* itself is
    yielded directly — callers execute queries on it as normal.
    """
    with sync_bulkhead:
        db = SessionLocal()
        try:
            # Validate the connection through the circuit breaker
            retry_with_jitter(
                lambda: circuit_breaker.call(
                    lambda: db.execute(text("SELECT 1"))
                )
            )
            yield db
        finally:
            db.close()

@asynccontextmanager
async def get_db_async():
    """Async session generator with bulkhead, circuit breaker, and retry logic."""
    async with async_bulkhead:
        db = SessionLocal()
        try:
            retry_with_jitter(
                lambda: circuit_breaker.call(
                    lambda: db.execute(text("SELECT 1"))
                )
            )
            yield db
        finally:
            db.close()
