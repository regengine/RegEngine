"""Password-reset / password-change router stub.

#1374 — The authoritative ``POST /auth/change-password`` implementation lives
in :mod:`services.admin.app.auth_routes`. A second implementation used to live
here and was silently shadowed because ``main.py`` mounts ``auth_router``
before ``password_reset_router``, so FastAPI resolved the path to
``auth_routes.change_password`` and this function never ran.

Behavior divergences that the dead copy hid:
  * Rate limit: 5/min (auth_routes) vs 3/min here.
  * Audit logging: auth_routes logs ``password.change``; this copy didn't.
  * Supabase sync: auth_routes syncs Supabase; this copy didn't.

The dead implementation has been removed. The router object is kept so
``main.py`` does not need to change, and so the module import remains a no-op.
Future password-reset endpoints can be registered here without conflict.
"""

from fastapi import APIRouter

# Empty router — intentionally registers no routes. See module docstring.
router = APIRouter(prefix="/auth", tags=["auth"])
