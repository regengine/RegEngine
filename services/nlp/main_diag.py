import sys
from pathlib import Path
import os
import importlib.util

print(f"DEBUG: CWD={os.getcwd()}")
_SERVICES_DIR = Path(__file__).resolve().parent.parent
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

# Check for 'app' spec
spec = importlib.util.find_spec("app")
print(f"DEBUG: app spec={spec}")

if spec:
    print(f"DEBUG: app origin={spec.origin}")
    print(f"DEBUG: app submodule_search_locations={spec.submodule_search_locations}")

try:
    import app
    print(f"DEBUG: app module={app}")
    print(f"DEBUG: app __path__={getattr(app, '__path__', 'No path')}")
    from app.config import settings
    print("DEBUG: SUCCESS")
except Exception as e:
    print(f"DEBUG: FAILURE: {e}")
    # print(f"DEBUG: sys.modules['app']={sys.modules.get('app')}")

from fastapi import FastAPI
api_app = FastAPI()
