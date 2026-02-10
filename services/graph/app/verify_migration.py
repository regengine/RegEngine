"""Verify async migration status of graph service modules.

Standalone diagnostic script — checks that all Neo4j-touching functions
are properly declared as async coroutines.

Usage:
    python -m services.graph.app.verify_migration
    # or from inside the service container:
    python verify_migration.py
"""

import asyncio
import inspect
import logging
import os
import sys
from unittest.mock import MagicMock, Mock

# ── Logging (use stdlib since this script mocks structlog) ──
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(message)s",
)
logger = logging.getLogger("verify_migration")


# Add current dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock dependencies so we can import without a live Neo4j
sys.modules["neo4j"] = MagicMock()
sys.modules["neo4j.exceptions"] = MagicMock()
sys.modules["structlog"] = MagicMock()
sys.modules["fastapi"] = MagicMock()
sys.modules["fastapi.responses"] = MagicMock()
sys.modules["pydantic"] = MagicMock()
sys.modules["pydantic_settings"] = MagicMock()
sys.modules["prometheus_client"] = MagicMock()
sys.modules["kafka"] = MagicMock()
sys.modules["kafka.errors"] = MagicMock()
sys.modules["shared"] = MagicMock()
sys.modules["shared.auth"] = MagicMock()
sys.modules["shared.fsma_validation"] = MagicMock()
sys.modules["shared.fsma_plan_builder"] = MagicMock()
sys.modules["shared.tenant_models"] = MagicMock()
sys.modules["shared.models"] = MagicMock()
sys.modules["shared.schemas"] = MagicMock()
sys.modules["shared.fsma_rules"] = MagicMock()
sys.modules["confluent_kafka"] = MagicMock()
sys.modules["confluent_kafka.schema_registry"] = MagicMock()
sys.modules["confluent_kafka.schema_registry.avro"] = MagicMock()
# Explicitly set these as None or objects to avoid further import attempts
sys.modules["shared"].tenant_models = MagicMock()
sys.modules["shared"].fsma_validation = MagicMock()
sys.modules["shared"].fsma_plan_builder = MagicMock()
sys.modules["shared"].schemas = MagicMock()
sys.modules["shared"].fsma_rules = MagicMock()

# Helper to make decorators transparent so we can inspect the underlying function
def identity_decorator(*args, **kwargs):
    def wrapper(func):
        return func
    return wrapper

mock_router = MagicMock()
mock_router.get.side_effect = identity_decorator
mock_router.post.side_effect = identity_decorator
mock_router.put.side_effect = identity_decorator
mock_router.delete.side_effect = identity_decorator
mock_router.patch.side_effect = identity_decorator

sys.modules["fastapi"].APIRouter = Mock(return_value=mock_router)
sys.modules["fastapi"].Depends = Mock()
sys.modules["fastapi"].Query = Mock(return_value=None)
sys.modules["fastapi"].Header = Mock(return_value=None)
sys.modules["fastapi"].Body = Mock(return_value=None)

# Set env vars from environment (no hardcoded credentials)
os.environ.setdefault("NEO4J_URI", os.getenv("NEO4J_URI", "bolt://neo4j:7687"))
os.environ.setdefault("NEO4J_USER", os.getenv("NEO4J_USER", "neo4j"))
os.environ.setdefault("NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD", ""))
os.environ.setdefault("NEO4J_DATABASE", os.getenv("NEO4J_DATABASE", "neo4j"))

if not os.environ.get("NEO4J_PASSWORD"):
    logger.warning("NEO4J_PASSWORD not set. Set via environment variable before running.")
    logger.warning("  export NEO4J_PASSWORD=your_password")

def check_async(name, func):
    if not func:
        logger.error("%s: NOT FOUND", name)
        return False
    is_async = inspect.iscoroutinefunction(func)
    level = logging.INFO if is_async else logging.ERROR
    status = "ASYNC" if is_async else "SYNC"
    result = "PASS" if is_async else "FAIL"
    logger.log(level, "%s: %s - %s", name, status, result)
    return is_async

def check_class_async(cls, methods):
    if not cls:
        logger.error("Class not found")
        return False
    all_pass = True
    logger.info("Class: %s", cls.__name__)
    for method_name in methods:
        method = getattr(cls, method_name, None)
        if not method:
            logger.error("  %s: NOT FOUND", method_name)
            all_pass = False
            continue
        if not check_async(f"  {method_name}", method):
            all_pass = False
    return all_pass

async def main():
    logger.info("Verifying Async Migration...\n")

    try:
        from .neo4j_utils import Neo4jClient
        from .fsma_utils import trace_forward, trace_backward
        from .fsma_recall import create_mock_recall, MockRecallEngine
        from .fsma_routes import trace_forward_endpoint, create_recall_drill
        from .overlay_writer import OverlayWriter
        from .overlay_resolver import OverlayResolver
        from .routers.labels import initialize_label_batch
    except ImportError as e:
        logger.error("ImportError during load: %s", e)
        # Fallback for manual run
        try:
             from neo4j_utils import Neo4jClient
             from fsma_utils import trace_forward, trace_backward
             from fsma_recall import create_mock_recall, MockRecallEngine
             from fsma_routes import trace_forward_endpoint, create_recall_drill
             from overlay_writer import OverlayWriter
             from overlay_resolver import OverlayResolver
             from routers.labels import initialize_label_batch
        except ImportError as e2:
             logger.error("Fallback ImportError: %s", e2)
             return

    # Check Neo4jClient methods
    if not check_class_async(Neo4jClient, ['upsert_provision', 'create_tenant_database', 'close']):
        logger.error("Neo4jClient failed")

    # Check fsma_utils
    logger.info("Module: fsma_utils")
    check_async("trace_forward", trace_forward)
    check_async("trace_backward", trace_backward)

    # Check fsma_recall
    logger.info("Module: fsma_recall")
    check_async("create_mock_recall", create_mock_recall)
    check_class_async(MockRecallEngine, ['execute_drill', 'execute_scheduled_drill'])

    # Check fsma_routes
    logger.info("Module: fsma_routes")
    check_async("trace_forward_endpoint", trace_forward_endpoint)
    check_async("create_recall_drill", create_recall_drill)

    # Check Overlay modules
    logger.info("Module: OverlayWriter")
    check_class_async(OverlayWriter, ['create_jurisdiction_node', 'create_tenant_control', 'get_control'])

    logger.info("Module: OverlayResolver")
    check_class_async(OverlayResolver, ['get_regulatory_requirements'])

    # Check labels
    logger.info("Module: routers.labels")
    check_async("initialize_label_batch", initialize_label_batch)

if __name__ == "__main__":
    asyncio.run(main())
