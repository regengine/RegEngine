"""
API key authentication for Automotive service.

Delegates to the shared RegEngine auth module for consistent
API key validation across all services.
"""

import sys
from pathlib import Path

# Ensure shared module is importable
_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_SERVICES_DIR))

from shared.auth import require_api_key, optional_api_key, APIKey  # noqa: F401

# Re-export for backward compatibility — routes can continue to use:
#   from .auth import require_api_key
__all__ = ["require_api_key", "optional_api_key", "APIKey"]
