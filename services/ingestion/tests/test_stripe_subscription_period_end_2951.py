"""``current_period_end`` moved onto subscription items — #2951.

Under the API version the pinned SDK sends by default
(``2026-03-25.dahlia``) a ``Subscription`` object no longer carries a
top-level ``current_period_end``; the field lives on each subscription
item (``subscription.items.data[].current_period_end``).

Two call sites read the old location and then *write the miss back*:

* ``routes.get_subscription`` — ``mapping["current_period_end"] =
  current_period_end or ""``, i.e. a GET handler overwriting persisted
  billing state with an empty string. The renewal date the
  ``invoice.paid`` handler derived from the invoice is destroyed and the
  API returns ``current_period_end: null`` until the next invoice a month
  later.
* ``webhooks._handle_checkout_completed`` — stores an empty period end
  from the very first write.

``_update_subscription_status`` already refuses to overwrite with a
missing value (``if current_period_end is not None``), which makes the
unconditional ``or ""`` in the two call sites above the outlier within
their own module family.

This suite locks in both halves of the fix: read the field from both
shapes, and never clobber a good stored value with a falsy one.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import stripe

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.stripe_billing import (  # noqa: E402
    helpers as helpers_mod,
    routes as routes_mod,
    state as state_mod,
)

# 2027-01-15T08:00:00+00:00 — comfortably inside the ISO string we assert on.
PERIOD_END_EPOCH = 1_800_000_000
STORED_PERIOD_END = "2030-01-01T00:00:00+00:00"


@pytest.fixture(autouse=True)
def _stub_configure_stripe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(helpers_mod, "_configure_stripe", lambda: None)


# ── The extraction helper itself ───────────────────────────────────────────


class TestExtractSubscriptionPeriodEnd_Issue2951:
    def test_reads_period_end_from_subscription_item(self) -> None:
        """Current shape: the field lives only on ``items.data[]``."""
        subscription = {
            "id": "sub_new_shape",
            "status": "active",
            "items": {"data": [{"id": "si_1", "current_period_end": PERIOD_END_EPOCH}]},
        }
        assert helpers_mod._extract_subscription_period_end(subscription) == (
            helpers_mod._format_period_end(PERIOD_END_EPOCH)
        )

    def test_reads_legacy_top_level_period_end(self) -> None:
        """Older payloads (and stored webhook events) still carry it at the
        top level — that shape must keep working."""
        subscription = {"id": "sub_old_shape", "current_period_end": PERIOD_END_EPOCH}
        assert helpers_mod._extract_subscription_period_end(subscription) == (
            helpers_mod._format_period_end(PERIOD_END_EPOCH)
        )

    def test_skips_items_without_a_period_end(self) -> None:
        """A metered item may omit the field; fall through to one that has it."""
        subscription = {
            "items": {
                "data": [
                    {"id": "si_no_period"},
                    {"id": "si_real", "current_period_end": PERIOD_END_EPOCH},
                ]
            }
        }
        assert helpers_mod._extract_subscription_period_end(subscription) == (
            helpers_mod._format_period_end(PERIOD_END_EPOCH)
        )

    def test_handles_stripeobject_style_attribute_access(self) -> None:
        """The SDK hands back ``StripeObject``/``ListObject`` instances, not
        plain dicts, so attribute access must work too."""
        subscription = SimpleNamespace(
            items=SimpleNamespace(data=[SimpleNamespace(current_period_end=PERIOD_END_EPOCH)])
        )
        assert helpers_mod._extract_subscription_period_end(subscription) == (
            helpers_mod._format_period_end(PERIOD_END_EPOCH)
        )

    def test_returns_none_when_absent_everywhere(self) -> None:
        assert helpers_mod._extract_subscription_period_end({"status": "active"}) is None
        assert helpers_mod._extract_subscription_period_end({"items": {"data": []}}) is None


# ── GET /billing/subscription ──────────────────────────────────────────────


class TestGetSubscriptionPeriodEnd_Issue2951:
    @pytest.mark.asyncio
    async def test_reads_period_end_from_items_and_persists_it(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With the current Stripe shape the endpoint must return the real
        renewal date — and store it, not ``""``."""
        monkeypatch.setattr(
            state_mod,
            "_get_subscription_mapping",
            lambda _t: {
                "plan_id": "growth",
                "status": "active",
                "subscription_id": "sub_new_shape",
                "current_period_end": STORED_PERIOD_END,
            },
        )
        stored: dict[str, Any] = {}
        monkeypatch.setattr(
            state_mod,
            "_store_subscription_mapping",
            lambda _t, mapping: stored.update(mapping),
        )
        monkeypatch.setattr(
            stripe.Subscription,
            "retrieve",
            lambda _sub_id: {
                "status": "active",
                "items": {"data": [{"current_period_end": PERIOD_END_EPOCH}]},
            },
        )

        result = await routes_mod.get_subscription("tenant-2951-items", _=None)

        expected = helpers_mod._format_period_end(PERIOD_END_EPOCH)
        assert result.current_period_end == expected, (
            "period end must be read from items.data[].current_period_end under the pinned API version"
        )
        assert stored.get("current_period_end") == expected, (
            f"the refreshed value must be persisted, got {stored.get('current_period_end')!r}"
        )

    @pytest.mark.asyncio
    async def test_missing_period_end_does_not_clobber_stored_value(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A read endpoint must never destroy persisted billing state.

        When Stripe reports no period end anywhere, the value the
        ``invoice.paid`` handler derived from the invoice must survive both
        in the response and in Redis.
        """
        monkeypatch.setattr(
            state_mod,
            "_get_subscription_mapping",
            lambda _t: {
                "plan_id": "growth",
                "status": "active",
                "subscription_id": "sub_no_period",
                "current_period_end": STORED_PERIOD_END,
            },
        )
        stored: dict[str, Any] = {}
        monkeypatch.setattr(
            state_mod,
            "_store_subscription_mapping",
            lambda _t, mapping: stored.update(mapping),
        )
        monkeypatch.setattr(stripe.Subscription, "retrieve", lambda _sub_id: {"status": "active"})

        result = await routes_mod.get_subscription("tenant-2951-clobber", _=None)

        assert result.current_period_end == STORED_PERIOD_END, (
            "a GET must not return null for a tenant whose stored mapping has a renewal date"
        )
        assert stored.get("current_period_end", STORED_PERIOD_END) == STORED_PERIOD_END, (
            f"a GET must not overwrite the stored renewal date, got "
            f"{stored.get('current_period_end')!r}"
        )
