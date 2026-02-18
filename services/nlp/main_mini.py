from pathlib import Path
import sys
import os

# Standardized path discovery
_SERVICES_DIR = Path(__file__).resolve().parent.parent
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

import shared.paths
shared.paths.ensure_shared_importable()

from shared.logging import setup_logging
logger = setup_logging()

# TEST IMPORT
try:
    # Rename the directory import if needed? No, let's keep the name but avoid variable clash
    import app.config as app_config
    settings = app_config.settings
    print(f"SUCCESS: imported app.config, settings={settings}")
except Exception as e:
    print(f"FAILURE: {e}")
    # print(f"sys.modules keys: {[k for k in sys.modules.keys() if 'app' in k]}")
    raise

from fastapi import FastAPI
# Rename the variable to avoid shadowing the package name 'app'
api_app = FastAPI(title="Mini NLP")

@api_app.get("/health")
def health():
    return {"status": "ok"}
