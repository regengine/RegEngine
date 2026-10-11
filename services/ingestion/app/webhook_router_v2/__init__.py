"""
Webhook Ingestion Router.

Provides POST /api/v1/webhooks/ingest for external systems to push
FSMA 204 traceability events into RegEngine. Each event is validated
against per-CTE KDE requirements, SHA-256 hashed, chain-linked, and
persisted to Postgres.

V2: Replaced in-memory storage with CTEPersistence (Postgres-backed).
    Events now survive restarts, support multi-tenant RLS, and feed
    the FDA export pipeline with real data.

Package layout: the original single-file ``webhook_router_v2.py`` was
split into focused submodules (tech-debt refactor; see ARCHITECTURE.md):

* ``security``   — API-key gate, HMAC signature verification (#1243),
                   event-timestamp replay window (#1245)
* ``metrics``    — Prometheus counters + replay/HMAC-skip recorders
* ``ratelimit``  — tenant-scoped ingest/read rate limiting
* ``validation`` — KDE validation, compliance alerts, obligation checks
* ``graph_sync`` — Redis-backed Neo4j sync publishing + counters (#1378)
* ``rules_eval`` — rules-engine pre-eval gate + canonical persistence
* ``tenant``     — tenant resolution for ingest (#2069)
* ``routes``     — the FastAPI router and endpoint handlers

Backward compatibility: every module-level name from the original file
is re-exported here, so ``from app.webhook_router_v2 import X`` and
``import app.webhook_router_v2 as wr; wr.X`` keep working unchanged.
Tests monkeypatch attributes on this module (e.g. ``wr._check_rate_limit``,
``wr.consume_tenant_rate_limit``, ``wr._last_hmac_skip_warn_at``); the
submodules resolve those collaborators through this package namespace at
call time, preserving the original late-bound global-name semantics.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..authz import require_permission, IngestionPrincipal, get_ingestion_principal
from shared.permissions import has_permission as _has_permission
from ..subscription_gate import require_active_subscription
from shared.database import get_db_session
from ..config import get_settings
from ..tenant_validation import validate_tenant_id
from shared.funnel_events import emit_funnel_event
from shared.idempotency import IdempotencyDependency
from shared.api_key_store import api_key_hash_candidates
from shared.tenant_rate_limiting import consume_tenant_rate_limit, rate_limit_reset_epoch
from shared.tenant_context import resolve_tenant_context
from ..webhook_models import (
    ChainVerifyResponse,
    EventResult,
    IngestEvent,
    IngestResponse,
    RecentEventsResponse,
    REQUIRED_KDES_BY_CTE,
    WebhookPayload,
)
from shared.canonical_event import normalize_webhook_event

# Backwards-compat alias: tests override this private name via
# ``app.dependency_overrides[_get_db_session]``. Point it at the canonical
# shared helper so the override matches the Depends() callable.
_get_db_session = get_db_session

logger = structlog.get_logger("webhook-ingestion")


# ---------------------------------------------------------------------------
# Shared mutable state
# ---------------------------------------------------------------------------
# Defined here — BEFORE the submodule imports below — so the submodules can
# read/write it through the package namespace at call time. Tests reset and
# inspect these attributes directly on the module (e.g.
# ``wr._last_hmac_skip_warn_at = 0.0`` / ``wr._graph_sync_failures``).

# F-5: observability for the silent-skip fail-open path is wired up in
# ``.metrics`` (after _get_or_create_counter is defined). See _record_hmac_skip().
_HMAC_SKIP_WARN_INTERVAL_SECS = 60.0
_last_hmac_skip_warn_at: float = 0.0
WEBHOOK_HMAC_SKIPPED = None  # populated after counter helper is defined

_graph_sync_failures = 0  # Fallback when Redis unavailable
_graph_sync_successes = 0


# ---------------------------------------------------------------------------
# Submodule re-exports (backward-compatible import surface)
# ---------------------------------------------------------------------------

from .security import (  # noqa: E402
    _is_production,
    _requires_closed_hmac_gate,
    _verify_api_key_present,
    _verify_api_key,
    _webhook_hmac_secret,
    webhook_hmac_configured,
    _verify_webhook_signature,
    _max_event_age_days,
    _max_event_future_hours,
    _validate_event_timestamp_window,
)

from . import metrics as _metrics_mod  # noqa: E402

WEBHOOK_REPLAY_REJECTED = _metrics_mod.WEBHOOK_REPLAY_REJECTED
WEBHOOK_HMAC_SKIPPED = _metrics_mod.WEBHOOK_HMAC_SKIPPED
WEBHOOK_HMAC_REJECTED = _metrics_mod.WEBHOOK_HMAC_REJECTED
JEV_REVIEW_FLAGGED = _metrics_mod.JEV_REVIEW_FLAGGED
OBLIGATION_CHECK_SKIPPED = _metrics_mod.OBLIGATION_CHECK_SKIPPED
_WEBHOOK_METRICS_ENABLED = _metrics_mod._WEBHOOK_METRICS_ENABLED
# The counter helpers only exist when prometheus_client imported cleanly —
# mirrors the original module, where they were defined inside the try block.
if hasattr(_metrics_mod, "_matches_registered_name"):
    _matches_registered_name = _metrics_mod._matches_registered_name
    _get_or_create_counter = _metrics_mod._get_or_create_counter
_record_hmac_skip = _metrics_mod._record_hmac_skip
_record_hmac_reject = _metrics_mod._record_hmac_reject
_classify_replay_rejection = _metrics_mod._classify_replay_rejection
_record_replay_rejection = _metrics_mod._record_replay_rejection
_record_obligation_skip = _metrics_mod._record_obligation_skip
_record_jev_review_flag = _metrics_mod._record_jev_review_flag

from .ratelimit import (  # noqa: E402
    _WEBHOOK_RATE_LIMIT_RPM,
    _WEBHOOK_RATE_LIMIT_WINDOW_SECS,
    _WEBHOOK_READ_RATE_LIMIT_RPM,
    _WEBHOOK_READ_RATE_LIMIT_WINDOW_SECS,
    _store_rate_limit_state,
    _check_read_rate_limit,
    _check_rate_limit,
)

from .validation import (  # noqa: E402
    _validate_event_kdes,
    _generate_alerts,
    _check_obligations,
)

from .jev_obligation_review import (  # noqa: E402
    review_event_for_alert_worthiness,
)

from .graph_sync import (  # noqa: E402
    _SYNC_COUNTER_PREFIX,
    _NEO4J_SYNC_QUEUE_KEY,
    _get_redis_client,
    _incr_sync_counter,
    get_graph_sync_stats,
    _neo4j_sync_enabled,
    _neo4j_sync_max_queue,
    _publish_graph_sync,
)

from .rules_eval import (  # noqa: E402
    _CanonicalPersistenceError,
    _get_persistence,
    _rules_preeval_reject,
    _persist_canonical_and_eval,
    _persist_required_canonical_and_eval,
)

from .tenant import (  # noqa: E402
    _lookup_tenant_id_for_api_key,
    _resolve_ingest_tenant_id,
)

from .routes import (  # noqa: E402
    router,
    _require_idempotency_key,
    ingest_events,
    get_recent_events,
    _enforce_webhooks_read_principal,
    recent_events_endpoint,
    verify_chain,
)

__all__ = [
    # Router / endpoints
    "router",
    "ingest_events",
    "get_recent_events",
    "recent_events_endpoint",
    "verify_chain",
    # Public helpers
    "webhook_hmac_configured",
    "get_graph_sync_stats",
    "review_event_for_alert_worthiness",
    # Auth / signature / replay window
    "_is_production",
    "_requires_closed_hmac_gate",
    "_verify_api_key_present",
    "_verify_api_key",
    "_webhook_hmac_secret",
    "_verify_webhook_signature",
    "_max_event_age_days",
    "_max_event_future_hours",
    "_validate_event_timestamp_window",
    # Metrics
    "WEBHOOK_REPLAY_REJECTED",
    "WEBHOOK_HMAC_SKIPPED",
    "WEBHOOK_HMAC_REJECTED",
    "JEV_REVIEW_FLAGGED",
    "OBLIGATION_CHECK_SKIPPED",
    "_WEBHOOK_METRICS_ENABLED",
    "_HMAC_SKIP_WARN_INTERVAL_SECS",
    "_last_hmac_skip_warn_at",
    "_record_hmac_skip",
    "_record_hmac_reject",
    "_classify_replay_rejection",
    "_record_replay_rejection",
    "_record_obligation_skip",
    "_record_jev_review_flag",
    # Rate limiting
    "_WEBHOOK_RATE_LIMIT_RPM",
    "_WEBHOOK_RATE_LIMIT_WINDOW_SECS",
    "_WEBHOOK_READ_RATE_LIMIT_RPM",
    "_WEBHOOK_READ_RATE_LIMIT_WINDOW_SECS",
    "_store_rate_limit_state",
    "_check_read_rate_limit",
    "_check_rate_limit",
    # Validation / alerts / obligations
    "_validate_event_kdes",
    "_generate_alerts",
    "_check_obligations",
    # Graph sync
    "_SYNC_COUNTER_PREFIX",
    "_NEO4J_SYNC_QUEUE_KEY",
    "_graph_sync_failures",
    "_graph_sync_successes",
    "_get_redis_client",
    "_incr_sync_counter",
    "_neo4j_sync_enabled",
    "_neo4j_sync_max_queue",
    "_publish_graph_sync",
    # Rules / canonical persistence
    "_CanonicalPersistenceError",
    "_get_persistence",
    "_rules_preeval_reject",
    "_persist_canonical_and_eval",
    "_persist_required_canonical_and_eval",
    # Tenant resolution
    "_lookup_tenant_id_for_api_key",
    "_resolve_ingest_tenant_id",
    # Misc / re-exported collaborators (kept for monkeypatching + back-compat)
    "_get_db_session",
    "logger",
    "_require_idempotency_key",
    "_enforce_webhooks_read_principal",
    "get_db_session",
    "get_settings",
    "validate_tenant_id",
    "emit_funnel_event",
    "consume_tenant_rate_limit",
    "rate_limit_reset_epoch",
    "resolve_tenant_context",
    "normalize_webhook_event",
    "api_key_hash_candidates",
]
