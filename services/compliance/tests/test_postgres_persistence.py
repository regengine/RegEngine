import sys
from pathlib import Path

# Add service directory to path for imports to work
service_dir = Path(__file__).parent.parent
_to_remove = [key for key in sys.modules if key == 'app' or key.startswith('app.') or key == 'main']
for key in _to_remove:
    del sys.modules[key]
sys.path.insert(0, str(service_dir))

# The test_analysis_and_audit_persist_to_postgres function was removed because
# it depended entirely on the /v1/models route which has been deleted.
# The model registration step was required before fair-lending analysis and
# audit export could run, making the entire test flow unreachable.
