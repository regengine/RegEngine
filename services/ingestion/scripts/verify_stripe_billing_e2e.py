#!/usr/bin/env python3
"""Validate Stripe billing flow end-to-end for ingestion-service.

This script is intended for local/staging verification with Stripe test mode.
It exercises:
1) checkout session creation
2) webhook processing via Stripe CLI triggers
3) portal session creation
4) invoice listing and invoice PDF lookup

Prerequisites:
- ingestion-service running and reachable
- STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET configured on ingestion-service
- Stripe CLI installed and authenticated (`stripe login`)
- Stripe listener forwarding events to ingestion-service, for example:
    stripe listen --forward-to http://localhost:8002/api/v1/billing/webhooks
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from typing import Any, Callable, Optional

import httpx
import redis


class ValidationError(RuntimeError):
    """Raised when one of the billing validations fails."""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Stripe billing flow end-to-end")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8002",
        help="Ingestion service base URL (default: http://localhost:8002)",
    )
    parser.add_argument(
        "--tenant-id",
        required=True,
        help="Tenant ID used for billing state assertions",
    )
    parser.add_argument(
        "--customer-email",
        default="billing-e2e@regengine.test",
        help="Customer email for checkout and portal (default: billing-e2e@regengine.test)",
    )
    parser.add_argument(
        "--tenant-name",
        default="Billing E2E Tenant",
        help="Tenant display name used for portal/customer bootstrap",
    )
    parser.add_argument(
        "--plan-id",
        choices=["growth", "scale"],
        default="growth",
        help="Plan for checkout session (default: growth)",
    )
    parser.add_argument(
        "--billing-period",
        choices=["monthly", "annual"],
        default="monthly",
        help="Billing period for checkout session (default: monthly)",
    )
    parser.add_argument(
        "--redis-url",
        default="redis://localhost:6379/0",
        help="Redis URL for reading billing mapping state",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Optional X-RegEngine-API-Key for authenticated billing endpoints",
    )
    parser.add_argument(
        "--stripe-cli-bin",
        default="stripe",
        help="Stripe CLI binary path (default: stripe)",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=90,
        help="Timeout for webhook-driven state transitions (default: 90)",
    )
    return parser.parse_args()


def _require_stripe_cli(stripe_cli_bin: str) -> None:
    try:
        subprocess.run(
            [stripe_cli_bin, "--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise ValidationError(
            "Stripe CLI is not available. Install it and run `stripe login` before this script."
        ) from exc


def _headers(api_key: Optional[str], tenant_id: Optional[str] = None) -> dict[str, str]:
    result: dict[str, str] = {}
    if api_key:
        result["X-RegEngine-API-Key"] = api_key
    if tenant_id:
        result["X-Tenant-ID"] = tenant_id
    return result


def _redis_mapping(client: redis.Redis, tenant_id: str) -> dict[str, str]:
    return {str(k): str(v) for k, v in client.hgetall(f"billing:tenant:{tenant_id}").items()}


def _wait_for(
    check: Callable[[], Optional[dict[str, str]]],
    timeout_seconds: int,
    description: str,
) -> dict[str, str]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        value = check()
        if value:
            return value
        time.sleep(2)
    raise ValidationError(f"Timed out waiting for: {description}")


def _run_stripe_trigger(stripe_cli_bin: str, event_name: str, add_fields: list[str]) -> str:
    cmd = [stripe_cli_bin, "trigger", event_name]
    for field in add_fields:
        cmd.extend(["--add", field])

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise ValidationError(
            f"Stripe trigger failed for '{event_name}'. stderr: {proc.stderr.strip() or '<empty>'}"
        )
    return proc.stdout.strip()


def _post_json(
    client: httpx.Client,
    path: str,
    payload: dict[str, Any],
    headers: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    response = client.post(path, json=payload, headers=headers or {})
    if response.status_code >= 400:
        raise ValidationError(f"POST {path} failed ({response.status_code}): {response.text}")
    return response.json()


def _get_json(
    client: httpx.Client,
    path: str,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    response = client.get(path, params=params or {}, headers=headers or {})
    if response.status_code >= 400:
        raise ValidationError(f"GET {path} failed ({response.status_code}): {response.text}")
    return response.json()


def main() -> int:
    args = _parse_args()
    _require_stripe_cli(args.stripe_cli_bin)

    redis_client = redis.from_url(args.redis_url, decode_responses=True)

    base_url = args.base_url.rstrip("/")
    checkout_payload = {
        "plan_id": args.plan_id,
        "billing_period": args.billing_period,
        "tenant_id": args.tenant_id,
        "tenant_name": args.tenant_name,
        "customer_email": args.customer_email,
        "success_url": "https://regengine.co/dashboard?checkout=success",
        "cancel_url": "https://regengine.co/pricing?checkout=cancelled",
    }

    print("[1/6] Creating checkout session...")
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        checkout_response = _post_json(client, "/api/v1/billing/checkout", checkout_payload)

        session_id = str(checkout_response.get("session_id") or "")
        if not session_id:
            raise ValidationError("Checkout response missing session_id")
        print(f"      session_id={session_id}")

        mapping_after_checkout = _redis_mapping(redis_client, args.tenant_id)
        if mapping_after_checkout.get("session_id") != session_id:
            raise ValidationError(
                "Checkout session hint not persisted to Redis (session_id mismatch)."
            )

        print("[2/6] Triggering checkout.session.completed webhook via Stripe CLI...")
        _run_stripe_trigger(
            args.stripe_cli_bin,
            "checkout.session.completed",
            add_fields=[
                f"checkout_session:metadata.tenant_id={args.tenant_id}",
                f"checkout_session:metadata.plan_id={args.plan_id}",
                f"checkout_session:metadata.billing_period={args.billing_period}",
                f"checkout_session:metadata.customer_email={args.customer_email}",
            ],
        )

        mapping_after_checkout_webhook = _wait_for(
            lambda: (
                m
                if (m := _redis_mapping(redis_client, args.tenant_id)).get("subscription_id")
                and m.get("status") in {"active", "trialing"}
                else None
            ),
            timeout_seconds=args.timeout_seconds,
            description="checkout webhook subscription activation",
        )

        subscription_id = mapping_after_checkout_webhook.get("subscription_id", "")
        customer_id = mapping_after_checkout_webhook.get("customer_id", "")
        if not subscription_id or not customer_id:
            raise ValidationError(
                "Subscription activation mapping missing subscription_id/customer_id. "
                "Confirm Stripe listen is forwarding to /api/v1/billing/webhooks."
            )
        print(f"      subscription_id={subscription_id}")
        print(f"      customer_id={customer_id}")

        print("[3/6] Triggering invoice.paid and validating period/payment sync...")
        _run_stripe_trigger(
            args.stripe_cli_bin,
            "invoice.paid",
            add_fields=[
                f"invoice:subscription={subscription_id}",
                f"invoice:customer={customer_id}",
            ],
        )

        mapping_after_paid = _wait_for(
            lambda: (
                m
                if (m := _redis_mapping(redis_client, args.tenant_id)).get("status") == "active"
                and bool(m.get("last_invoice_id"))
                else None
            ),
            timeout_seconds=args.timeout_seconds,
            description="invoice.paid mapping update",
        )

        if not mapping_after_paid.get("current_period_end"):
            raise ValidationError("invoice.paid did not persist current_period_end")

        print("[4/6] Triggering invoice.payment_failed and validating past_due state...")
        _run_stripe_trigger(
            args.stripe_cli_bin,
            "invoice.payment_failed",
            add_fields=[
                f"invoice:subscription={subscription_id}",
                f"invoice:customer={customer_id}",
            ],
        )

        _wait_for(
            lambda: (
                m
                if (m := _redis_mapping(redis_client, args.tenant_id)).get("status") == "past_due"
                else None
            ),
            timeout_seconds=args.timeout_seconds,
            description="invoice.payment_failed status transition",
        )

        print("[5/6] Verifying portal session endpoint...")
        portal_response = _post_json(
            client,
            "/api/v1/billing/portal",
            {
                "tenant_id": args.tenant_id,
                "tenant_name": args.tenant_name,
                "customer_email": args.customer_email,
            },
            headers=_headers(args.api_key, tenant_id=args.tenant_id),
        )

        portal_url = str(portal_response.get("portal_url") or "")
        if not portal_url.startswith("https://billing.stripe.com/"):
            raise ValidationError(f"Unexpected portal URL: {portal_url}")

        print("[6/6] Verifying invoice list + invoice PDF endpoint...")
        invoice_list = _get_json(
            client,
            "/api/v1/billing/invoices",
            params={"tenant_id": args.tenant_id, "limit": 10},
            headers=_headers(args.api_key, tenant_id=args.tenant_id),
        )

        invoices = invoice_list.get("invoices") or []
        if invoices:
            invoice_id = str(invoices[0].get("invoice_id") or "")
            if not invoice_id:
                raise ValidationError("Invoice list returned an entry without invoice_id")
            invoice_pdf = _get_json(
                client,
                f"/api/v1/billing/invoices/{invoice_id}/pdf",
                params={"tenant_id": args.tenant_id},
                headers=_headers(args.api_key, tenant_id=args.tenant_id),
            )
            pdf_url = str(invoice_pdf.get("pdf_url") or "")
            if not pdf_url.startswith("https://"):
                raise ValidationError(f"Invoice PDF URL is invalid: {pdf_url}")
            print(f"      invoice_id={invoice_id}")
            print(f"      pdf_url={pdf_url}")
        else:
            print(
                "      No invoices listed yet. This can happen if Stripe test fixtures have not fully propagated."
            )

    print("\nStripe billing flow validation passed.")
    print(json.dumps(_redis_mapping(redis_client, args.tenant_id), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValidationError as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # pragma: no cover - defensive CLI guardrail
        print(f"Unexpected error: {exc}", file=sys.stderr)
        sys.exit(1)
