"""
API key authentication for Aerospace service.

SEC-AER-001 REMEDIATION: Replaced local presence-only validation
with delegation to shared RegEngine auth module for proper HMAC-based
key validation, rate limiting, and expiry checks.

Follows the same pattern as gaming/app/auth.py.
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
