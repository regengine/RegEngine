# ============================================================
# stripe_billing subpackage
#
# Split from the original 1186-line stripe_billing.py module.
# Re-exports ALL public symbols so that existing imports continue
# to work unchanged:
#   - from app.stripe_billing import router as billing_router
#   - from app import stripe_billing; stripe_billing.router
# ============================================================
"""
Stripe Billing Router.

Manages Stripe checkout sessions, subscription status, and webhook processing
for RegEngine's FSMA-first pricing tiers.
"""

import stripe  # noqa: F401 — tests monkeypatch stripe_billing.stripe.*
from shared.funnel_events import emit_funnel_event  # noqa: F401 — tests monkeypatch stripe_billing.emit_funnel_event

from . import customers as _customers_mod  # noqa: F401
from . import helpers as _helpers_mod  # noqa: F401
from . import plans as _plans_mod  # noqa: F401
from . import routes as _routes_mod  # noqa: F401
from . import state as _state_mod  # noqa: F401
from . import webhooks as _webhooks_mod  # noqa: F401

from .routes import (
    router,
    create_checkout,
    create_portal_session_for_tenant,
    create_portal_session_legacy,
    get_invoice_pdf,
    get_subscription,
    list_invoices,
    list_plans,
    stripe_webhook_legacy,
    stripe_webhooks,
)
from .models import (
    BillingPortalRequest,
    BillingPortalResponse,
    CheckoutRequest,
    CheckoutResponse,
    InvoiceListResponse,
    InvoicePdfResponse,
    InvoiceSummary,
    SubscriptionStatus,
)
from .plans import (
    DEFAULT_CANCEL_URL,
    DEFAULT_PORTAL_RETURN_URL,
    DEFAULT_SUCCESS_URL,
    PLANS,
    PLAN_ALIASES,
    _normalize_billing_period,
    _normalize_plan_id,
    _resolve_price_id,
)
from .state import (
    _customer_lookup_key,
    _find_tenant_id,
    _get_subscription_mapping,
    _redis_client,
    _session_lookup_key,
    _store_subscription_mapping,
    _subscription_lookup_key,
    _tenant_subscription_key,
)
from .helpers import (
    _coerce_int,
    _coerce_optional_int,
    _configure_stripe,
    _enforce_admin_or_operator,
    _extract_invoice_period_end,
    _extract_paid_at,
    _format_period_end,
    _normalize_scope,
    _principal_role,
    _resolve_tenant_context,
    _stripe_get,
)
from .customers import (
    _create_customer_for_tenant,
    _create_portal_session,
    _create_tenant_via_admin,
    _ensure_customer_mapping,
    _get_existing_customer_id,
    _record_checkout_session_hint,
)
from .webhooks import (
    _handle_checkout_completed,
    _handle_stripe_event,
    _process_stripe_webhook,
    _update_subscription_status,
)

__all__ = [
    # Router
    "router",
    # Route functions
    "create_checkout",
    "create_portal_session_for_tenant",
    "create_portal_session_legacy",
    "get_invoice_pdf",
    "get_subscription",
    "list_invoices",
    "list_plans",
    "stripe_webhook_legacy",
    "stripe_webhooks",
    # Models
    "BillingPortalRequest",
    "BillingPortalResponse",
    "CheckoutRequest",
    "CheckoutResponse",
    "InvoiceListResponse",
    "InvoicePdfResponse",
    "InvoiceSummary",
    "SubscriptionStatus",
    # Plans
    "DEFAULT_CANCEL_URL",
    "DEFAULT_PORTAL_RETURN_URL",
    "DEFAULT_SUCCESS_URL",
    "PLANS",
    "PLAN_ALIASES",
    # State
    "_customer_lookup_key",
    "_find_tenant_id",
    "_get_subscription_mapping",
    "_redis_client",
    "_session_lookup_key",
    "_store_subscription_mapping",
    "_subscription_lookup_key",
    "_tenant_subscription_key",
    # Helpers
    "_coerce_int",
    "_coerce_optional_int",
    "_configure_stripe",
    "_enforce_admin_or_operator",
    "_extract_invoice_period_end",
    "_extract_paid_at",
    "_format_period_end",
    "_normalize_scope",
    "_principal_role",
    "_resolve_tenant_context",
    "_stripe_get",
    # Plans (functions)
    "_normalize_billing_period",
    "_normalize_plan_id",
    "_resolve_price_id",
    # Customers
    "_create_customer_for_tenant",
    "_create_portal_session",
    "_create_tenant_via_admin",
    "_ensure_customer_mapping",
    "_get_existing_customer_id",
    "_record_checkout_session_hint",
    # Webhooks
    "_handle_checkout_completed",
    "_handle_stripe_event",
    "_process_stripe_webhook",
    "_update_subscription_status",
    # Re-exported third-party (for test monkeypatching)
    "stripe",
    "emit_funnel_event",
]


# ── Monkeypatch propagation ─────────────────────────────────────
# Tests written against the original single-file module do e.g.
#   monkeypatch.setattr(stripe_billing, "_redis_client", fake)
# With the package split, that only sets the attribute on *this*
# __init__ module.  The submodules that actually call the function
# still see their own binding via the submodule object.
#
# We replace sys.modules[__name__] with a thin subclass of
# types.ModuleType whose __setattr__ forwards patches into the
# canonical submodule so existing tests keep working unmodified.
import sys as _sys
import types as _types

_ATTR_TO_SUBMODULE = {
    # state.py
    "_redis_client": _state_mod,
    "_tenant_subscription_key": _state_mod,
    "_subscription_lookup_key": _state_mod,
    "_customer_lookup_key": _state_mod,
    "_session_lookup_key": _state_mod,
    "_store_subscription_mapping": _state_mod,
    "_get_subscription_mapping": _state_mod,
    "_find_tenant_id": _state_mod,
    # helpers.py
    "_configure_stripe": _helpers_mod,
    "_format_period_end": _helpers_mod,
    "_stripe_get": _helpers_mod,
    "_coerce_int": _helpers_mod,
    "_coerce_optional_int": _helpers_mod,
    "_extract_invoice_period_end": _helpers_mod,
    "_extract_paid_at": _helpers_mod,
    "_normalize_scope": _helpers_mod,
    "_principal_role": _helpers_mod,
    "_enforce_admin_or_operator": _helpers_mod,
    "_resolve_tenant_context": _helpers_mod,
    # plans.py
    "_normalize_plan_id": _plans_mod,
    "_normalize_billing_period": _plans_mod,
    "_resolve_price_id": _plans_mod,
    # customers.py
    "_create_tenant_via_admin": _customers_mod,
    "_create_portal_session": _customers_mod,
    "_create_customer_for_tenant": _customers_mod,
    "_ensure_customer_mapping": _customers_mod,
    "_get_existing_customer_id": _customers_mod,
    "_record_checkout_session_hint": _customers_mod,
    # webhooks.py
    "_handle_checkout_completed": _webhooks_mod,
    "_update_subscription_status": _webhooks_mod,
    "_handle_stripe_event": _webhooks_mod,
    "_process_stripe_webhook": _webhooks_mod,
}


class _PatchableModule(_types.ModuleType):
    """Module subclass that propagates setattr to canonical submodules."""

    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        submod = _ATTR_TO_SUBMODULE.get(name)
        if submod is not None:
            setattr(submod, name, value)
        # emit_funnel_event lives in shared.funnel_events; routes.py and
        # webhooks.py call it through that module, so patch it there too.
        if name == "emit_funnel_event":
            from shared import funnel_events as _fe_mod
            setattr(_fe_mod, name, value)


# Swap module class so future setattr() calls propagate patches.
_this = _sys.modules[__name__]
_this.__class__ = _PatchableModule
