import os
import sys
import inspect
import asyncio
from unittest.mock import MagicMock, Mock

# Add current dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock dependencies
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

# Mock env vars
os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ["NEO4J_USER"] = "neo4j"
os.environ["NEO4J_PASSWORD"] = "password"
os.environ["NEO4J_DATABASE"] = "neo4j"

def check_async(name, func):
    if not func:
        print(f"{name}: NOT FOUND")
        return False
    is_async = inspect.iscoroutinefunction(func)
    print(f"{name}: {'ASYNC' if is_async else 'SYNC'} - {'PASS' if is_async else 'FAIL'}")
    return is_async

def check_class_async(cls, methods):
    if not cls:
        print(f"Class not found")
        return False
    all_pass = True
    print(f"\nClass: {cls.__name__}")
    for method_name in methods:
        method = getattr(cls, method_name, None)
        if not method:
             print(f"  {method_name}: NOT FOUND")
             all_pass = False
             continue
        if not check_async(f"  {method_name}", method):
            all_pass = False
    return all_pass

async def main():
    print("Verifying Async Migration...\n")
    
    try:
        from .neo4j_utils import Neo4jClient
        from .fsma_utils import trace_forward, trace_backward
        from .fsma_recall import create_mock_recall, MockRecallEngine
        from .fsma_routes import trace_forward_endpoint, create_recall_drill
        from .overlay_writer import OverlayWriter
        from .overlay_resolver import OverlayResolver
        from .routers.labels import initialize_label_batch
    except ImportError as e:
        print(f"ImportError during load: {e}")
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
             print(f"Fallback ImportError: {e2}")
             return

    # Check Neo4jClient methods
    if not check_class_async(Neo4jClient, ['upsert_provision', 'create_tenant_database', 'close']):
        print("Neo4jClient failed")

    # Check fsma_utils
    print("\nModule: fsma_utils")
    check_async("trace_forward", trace_forward)
    check_async("trace_backward", trace_backward)

    # Check fsma_recall
    print("\nModule: fsma_recall")
    check_async("create_mock_recall", create_mock_recall)
    check_class_async(MockRecallEngine, ['execute_drill', 'execute_scheduled_drill'])

    # Check fsma_routes
    print("\nModule: fsma_routes")
    check_async("trace_forward_endpoint", trace_forward_endpoint)
    check_async("create_recall_drill", create_recall_drill)

    # Check Overlay modules
    print("\nModule: OverlayWriter")
    check_class_async(OverlayWriter, ['create_jurisdiction_node', 'create_tenant_control', 'get_control'])
    
    print("\nModule: OverlayResolver")
    check_class_async(OverlayResolver, ['get_regulatory_requirements'])

    # Check labels
    print("\nModule: routers.labels")
    check_async("initialize_label_batch", initialize_label_batch)

if __name__ == "__main__":
    asyncio.run(main())
