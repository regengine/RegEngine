"""Partner Gateway router — all 12 operations from the OpenAPI spec.

Status: AUTH IS PRODUCTION-READY, DATA WIRING IS STUBBED.

Every handler enforces the scope declared in
``regengine-partner-gateway-openapi.yaml`` via :func:`require_partner_scope`,
so 401/403 behavior is real and shippable. Response payloads are stubs
clearly marked with ``"_stub": True``; the docstring on each handler
lists the exact data wiring TODOs (which tables, which RLS contexts,
which billing rollups). Filling them in is mechanical and can be done
endpoint-by-endpoint without further auth changes.

Drift between this file and the OpenAPI spec is a security bug: the
spec's ``x-required-scopes`` value MUST match the string passed to
``require_partner_scope`` for the same operationId.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field

from .auth import PartnerPrincipal, require_partner_scope

router = APIRouter(prefix="/v1/partner", tags=["Partner Gateway"])


# ---------------------------------------------------------------------------
# Request bodies — kept narrow for the stub phase. When real wiring lands,
# generate full Pydantic models from the OpenAPI spec rather than
# hand-extending these.
# ---------------------------------------------------------------------------


class CreateClientRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    billing_tier: str = Field(pattern="^(free|growth|scale|enterprise)$")
    verticals: list[str] = Field(default_factory=lambda: ["fsma"])
    allowed_jurisdictions: list[str] = Field(default_factory=lambda: ["US"])
    contact_email: Optional[str] = None
    webhook_url: Optional[str] = None


class UpdateClientRequest(BaseModel):
    name: Optional[str] = None
    billing_tier: Optional[str] = Field(
        default=None, pattern="^(free|growth|scale|enterprise)$"
    )
    webhook_url: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(active|suspended)$")


class EvidenceExportRequest(BaseModel):
    from_date: Optional[str] = None  # ISO date
    to_date: Optional[str] = None
    format: str = Field(default="zip", pattern="^(json|zip)$")
    include_verification_sdk: bool = True


class CreateApiKeyRequest(BaseModel):
    name: str
    # Per the OpenAPI spec the per-CLIENT key scopes are
    # ``[read, ingest, admin]`` — those are deliberately narrow because
    # client keys hit ingestion endpoints, not the partner gateway. They
    # are NOT the same set as the ``partner.*`` scopes used to gate this
    # gateway. Do not conflate them.
    scopes: list[str]
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=365)


class BrandingPayload(BaseModel):
    logo_url: Optional[str] = None
    primary_color: Optional[str] = Field(
        default=None, pattern="^#[0-9A-Fa-f]{6}$"
    )
    company_name_override: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub(principal: PartnerPrincipal, payload: dict) -> dict:
    """Wrap every stub response with consistent debug fields.

    Removes the temptation to copy/paste forgotten ``"_stub": True``
    markers and gives the operator a uniform way to grep for stubbed
    traffic in production logs (any 200 with ``"_stub"`` is unwired).
    """
    return {
        **payload,
        "_stub": True,
        "_principal_key_id": principal.key_id,
        "_principal_partner_id": principal.partner_id,
    }


# ---------------------------------------------------------------------------
# Client management
# ---------------------------------------------------------------------------


@router.get(
    "/clients",
    summary="List all client tenants originated by this partner",
    operation_id="listClients",
)
async def list_clients(
    principal: PartnerPrincipal = Depends(
        require_partner_scope("partner.clients.read")
    ),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(
        None, alias="status", pattern="^(active|suspended|churned|onboarding)$"
    ),
) -> dict:
    """STUB. Real wiring:

    1. Set tenant GUC to ``principal.partner_id`` so RLS filters apply.
    2. Query ``tenants`` joined with ``billing.subscriptions`` for the
       compliance score / MRR / status fields.
    3. Page server-side via ``LIMIT/OFFSET`` — partner accounts can
       have thousands of clients.
    """
    return _stub(
        principal,
        {
            "data": [],
            "pagination": {"page": page, "per_page": per_page, "total": 0},
            "totals": {
                "active_clients": 0,
                "total_mrr": 0.0,
                "avg_compliance_score": 0.0,
            },
        },
    )


@router.post(
    "/clients",
    summary="Provision a new client tenant",
    operation_id="createClient",
    status_code=201,
)
async def create_client(
    body: CreateClientRequest,
    principal: PartnerPrincipal = Depends(
        require_partner_scope("partner.clients.write")
    ),
) -> dict:
    """STUB. Real wiring:

    1. Insert a row into ``tenants`` with ``partner_id = principal.partner_id``
       (the column linking the new client back to the issuing partner).
    2. Create RLS-scoped schema and apply default policies.
    3. Issue per-client API keys (delegate to
       ``DatabaseAPIKeyStore.create_key`` with the new tenant_id).
    4. Configure default branding from partner defaults if none provided.
    """
    return _stub(
        principal,
        {
            "id": "00000000-0000-0000-0000-000000000000",
            "name": body.name,
            "status": "onboarding",
            "billing_tier": body.billing_tier,
            "compliance_score": 0.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.get(
    "/clients/{client_id}",
    summary="Get detailed client tenant information",
    operation_id="getClient",
)
async def get_client(
    client_id: UUID = Path(...),
    principal: PartnerPrincipal = Depends(
        require_partner_scope("partner.clients.read")
    ),
) -> dict:
    """STUB. Real wiring:

    1. Set tenant GUC; query ``tenants`` joined with metric rollups.
    2. Verify ``tenants.partner_id = principal.partner_id`` — RLS
       should make this redundant, but check explicitly so a misconfigured
       policy doesn't silently leak cross-partner data.
    3. 404 if not found OR if owned by a different partner.
    """
    return _stub(
        principal,
        {
            "id": str(client_id),
            "name": "Example Client",
            "status": "active",
            "billing_tier": "growth",
            "compliance_score": 0.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.patch(
    "/clients/{client_id}",
    summary="Update client tenant configuration",
    operation_id="updateClient",
)
async def update_client(
    body: UpdateClientRequest,
    client_id: UUID = Path(...),
    principal: PartnerPrincipal = Depends(
        require_partner_scope("partner.clients.write")
    ),
) -> dict:
    """STUB. Real wiring:

    1. Same RLS + ownership check as ``get_client``.
    2. Apply partial update — explicitly enumerate updatable fields,
       do not pass ``body.dict()`` straight through (would let a partner
       set columns like ``partner_id`` they shouldn't touch).
    3. Suspending → set ``status='suspended'`` AND disable per-client
       keys via ``revoke_key()`` so ingestion stops immediately.
    """
    return _stub(
        principal,
        {
            "id": str(client_id),
            "updated": True,
            "fields_set": [
                k for k, v in body.model_dump().items() if v is not None
            ],
        },
    )


# ---------------------------------------------------------------------------
# Compliance + evidence
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/compliance",
    summary="Get client compliance dashboard data",
    operation_id="getClientCompliance",
)
async def get_client_compliance(
    client_id: UUID = Path(...),
    vertical: str = Query("fsma", pattern="^fsma$"),
    principal: PartnerPrincipal = Depends(
        require_partner_scope("partner.compliance.read")
    ),
) -> dict:
    """STUB. Real wiring:

    1. Resolve the compliance dashboard rollup for ``client_id`` —
       same query the existing internal compliance dashboard uses.
    2. Return only the fields documented in the OpenAPI schema; do
       NOT pass through internal-only metrics like control IDs.
    """
    return _stub(
        principal,
        {
            "client_id": str(client_id),
            "vertical": vertical,
            "overall_score": 0.0,
            "obligation_coverage": 0.0,
            "control_effectiveness": 0.0,
            "evidence_freshness": 0.0,
            "risk_level": "LOW",
            "active_drift_alerts": 0,
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.post(
    "/clients/{client_id}/evidence/export",
    summary="Export cryptographic evidence chain for audit",
    operation_id="exportEvidence",
    status_code=202,
)
async def export_evidence(
    body: EvidenceExportRequest,
    client_id: UUID = Path(...),
    principal: PartnerPrincipal = Depends(
        require_partner_scope("partner.evidence.export")
    ),
) -> dict:
    """STUB. Real wiring:

    1. Enqueue an evidence export job (existing service:
       ``services/compliance`` has the export pipeline already).
    2. Return ``202 Accepted`` + a polling URL or pre-signed download
       URL once the job completes. The OpenAPI spec implies inline
       response — the real impl should return a job id and let the
       client poll, since chains can be GBs.
    3. Sign the download URL with a short TTL (1 hour per spec).
    """
    return _stub(
        principal,
        {
            "export_id": "00000000-0000-0000-0000-000000000000",
            "client_id": str(client_id),
            "status": "queued",
            "format": body.format,
            "envelope_count": 0,
            "verification_command": "python verify_snapshot_chain.py export.json",
        },
    )


# ---------------------------------------------------------------------------
# Per-client API keys (NB: these are CLIENT keys, not partner keys —
# different scope namespace; see CreateApiKeyRequest docstring)
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/api-keys",
    summary="List per-client API keys (metadata only)",
    operation_id="listClientApiKeys",
)
async def list_client_api_keys(
    client_id: UUID = Path(...),
    principal: PartnerPrincipal = Depends(
        require_partner_scope("partner.api_keys.read")
    ),
) -> dict:
    """STUB. Real wiring:

    1. ``DatabaseAPIKeyStore.list_keys(tenant_id=str(client_id))``.
    2. Filter to keys whose ``partner_id`` matches the principal — a
       defense-in-depth check above RLS.
    3. NEVER return ``raw_key`` here (the column doesn't exist on the
       response model anyway, but be explicit).
    """
    return _stub(principal, {"data": []})


@router.post(
    "/clients/{client_id}/api-keys",
    summary="Create a per-client API key",
    operation_id="createClientApiKey",
    status_code=201,
)
async def create_client_api_key(
    body: CreateApiKeyRequest,
    client_id: UUID = Path(...),
    principal: PartnerPrincipal = Depends(
        require_partner_scope("partner.api_keys.write")
    ),
) -> dict:
    """STUB. Real wiring:

    1. Verify the requested ``scopes`` are a subset of what the partner
       can grant. A partner CANNOT issue a client key with admin scopes
       — enforce this here, do not rely on a client-side check.
    2. ``DatabaseAPIKeyStore.create_key(tenant_id=client_id,
       partner_id=principal.partner_id, scopes=body.scopes, ...)``.
    3. Return the raw_key exactly once — the response schema is the
       only acknowledgment the partner will get.
    """
    return _stub(
        principal,
        {
            "key_id": "00000000-0000-0000-0000-000000000000",
            "raw_key": "rge_stub.stubstubstubstubstub",
            "name": body.name,
            "scopes": body.scopes,
            "expires_at": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# Revenue + payouts
# ---------------------------------------------------------------------------


@router.get(
    "/revenue",
    summary="Get partner revenue share metrics",
    operation_id="getRevenueMetrics",
)
async def get_revenue_metrics(
    principal: PartnerPrincipal = Depends(
        require_partner_scope("partner.revenue.read")
    ),
    period: str = Query(
        "current_month", pattern="^(current_month|last_month|current_quarter|ytd)$"
    ),
) -> dict:
    """STUB. Real wiring:

    1. Resolve ``period`` to a (start, end) datetime tuple in UTC.
    2. Query Stripe billing rollups filtered by ``principal.partner_id``
       — never accept ``partner_id`` from query params (IDOR).
    3. Apply the partner's revenue share percentage from the
       ``partner_agreements`` table; do not hard-code rates.
    """
    return _stub(
        principal,
        {
            "partner_id": principal.partner_id,
            "period": period,
            "tier": "standard",
            "revenue_share_pct": 0.0,
            "clients": [],
            "totals": {
                "total_mrr": 0.0,
                "partner_total_share": 0.0,
                "currency": "USD",
            },
        },
    )


@router.get(
    "/revenue/payouts",
    summary="List partner payouts",
    operation_id="listPayouts",
)
async def list_payouts(
    principal: PartnerPrincipal = Depends(
        require_partner_scope("partner.payouts.read")
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """STUB. Real wiring: query ``partner_payouts`` table (or Stripe
    transfers API) filtered by ``principal.partner_id``."""
    return _stub(
        principal,
        {
            "data": [],
            "pagination": {"limit": limit, "offset": offset, "total": 0},
        },
    )


# ---------------------------------------------------------------------------
# Branding (white-label)
# ---------------------------------------------------------------------------


@router.get(
    "/branding",
    summary="Read white-label branding config",
    operation_id="getBranding",
)
async def get_branding(
    principal: PartnerPrincipal = Depends(
        require_partner_scope("partner.branding.read")
    ),
) -> dict:
    """STUB. Real wiring: read the partner's row from
    ``partner_branding`` keyed by ``principal.partner_id``."""
    return _stub(
        principal,
        {
            "logo_url": None,
            "primary_color": "#2E5090",
            "company_name_override": None,
            "custom_domain": None,
            "wizard_embed_domains": [],
        },
    )


@router.put(
    "/branding",
    summary="Update white-label branding config",
    operation_id="updateBranding",
)
async def update_branding(
    body: BrandingPayload,
    principal: PartnerPrincipal = Depends(
        require_partner_scope("partner.branding.write")
    ),
) -> dict:
    """STUB. Real wiring:

    1. Validate ``custom_domain`` and any ``wizard_embed_domains`` as
       real hostnames (RFC 1035 / 5891) — the OpenAPI review flagged
       this as a SSRF surface if the backend ever fetches them.
    2. Upsert into ``partner_branding`` keyed by ``principal.partner_id``.
    3. Invalidate any CDN edge caches for the partner's branded URLs.
    """
    return _stub(
        principal,
        {
            **body.model_dump(exclude_none=True),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
