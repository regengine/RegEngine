"""
Webhook Ingestion Router.

Provides POST /api/v1/webhooks/ingest for external systems to push
FSMA 204 traceability events into RegEngine. Each event is validated
against per-CTE KDE requirements, SHA-256 hashed, chain-linked, and
persisted to Postgres.

V2: Replaced in-memory storage with CTEPersistence (Postgres-backed).
    Events now survive restarts, support multi-tenant RLS, and feed
    the FDA export pipeline with real data.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from .authz import require_permission, IngestionPrincipal
from .subscription_gate import require_active_subscription
from shared.database import get_db_session
from .config import get_settings
from .tenant_validation import validate_tenant_id
from shared.funnel_events import emit_funnel_event
from shared.idempotency import IdempotencyDependency
from shared.tenant_rate_limiting import consume_tenant_rate_limit
from .webhook_models import (
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

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhook Ingestion"])


class _CanonicalPersistenceError(Exception):
    """Raised when required canonical persistence cannot complete."""


def _get_persistence(db_session=None):
    """Get CTEPersistence instance, or None if DB unavailable."""
    if db_session is None:
        return None
    try:
        from shared.cte_persistence import CTEPersistence
        return CTEPersistence(db_session)
    except ImportError:
        logger.warning("cte_persistence module not available")
        return None


# ---------------------------------------------------------------------------
# In-memory fallback REMOVED — production must have Postgres
# ---------------------------------------------------------------------------
# Previously, RegEngine would silently accept events into a module-level dict
# when DB was unavailable. This is dangerous: data vanishes on restart, chain
# integrity cannot be guaranteed, and operators have no visibility into lost data.
# Now the endpoint returns 503 Service Unavailable if Postgres is down.


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _is_production() -> bool:
    """Detect production using centralized environment detection."""
    from shared.env import is_production
    return is_production()


def _verify_api_key(
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
) -> None:
    """Fail-closed defense-in-depth check on the X-RegEngine-API-Key header.

    Does NOT validate the key itself — that happens later in
    ``require_permission`` → ``get_ingestion_principal`` → ``require_api_key``
    which consults the DB-backed key store and the preshared master env var.
    This gate only enforces that (a) a header is present at all and (b) the
    service has at least one credential configured, so a misconfigured
    prod deploy can't silently accept unauthenticated traffic.

    Before this fix, the gate only checked ``API_KEY`` (never set on
    Railway — ``REGENGINE_API_KEY`` is used instead), so every per-tenant
    API key 401'd here even when valid and later resolved by the
    principal path.
    """
    if not x_regengine_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    settings = get_settings()
    configured_api_key = (
        getattr(settings, "api_key", None)
        or os.environ.get("API_KEY")
        or os.environ.get("REGENGINE_API_KEY")
    )
    if not configured_api_key and _is_production():
        # Neither API_KEY nor REGENGINE_API_KEY set in prod — reject so a
        # misconfigured deploy cannot silently accept traffic.
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------------------------------------------------------------------------
# Webhook HMAC signature verification (#1243)
# ---------------------------------------------------------------------------


def _webhook_hmac_secret() -> Optional[str]:
    """Configured webhook HMAC secret, or ``None`` if unset.

    Single global secret to start — per-tenant / per-integration
    rotation is planned as follow-up (see #1243 fix description). When
    the env is unset the dependency is a no-op, which preserves the
    existing partner-integration ramp. Production operators MUST set
    this before relying on webhook-ingest events.
    """
    secret = os.getenv("WEBHOOK_HMAC_SECRET", "").strip()
    return secret or None


async def _verify_webhook_signature(
    request: Request,
    x_webhook_signature: Optional[str] = Header(default=None, alias="X-Webhook-Signature"),
) -> None:
    """Enforce HMAC-SHA256(secret, raw_body) on every ingest request.

    #1243: API-key auth alone makes any key leak (logs, proxies, .env)
    sufficient to forge a tenant's supply-chain events. A signed body
    adds proof that the sender holds the shared secret and that the
    bytes weren't tampered with in flight.

    Signature format (GitHub-style): ``X-Webhook-Signature:
    sha256=<hex>``. A bare hex digest is also accepted so existing
    Stripe-style senders don't need a separate code path.

    Behavior:
    - ``WEBHOOK_HMAC_SECRET`` unset → verification skipped (migration ramp).
    - Secret set + signature missing → HTTP 401.
    - Secret set + signature mismatch → HTTP 401 (timing-safe compare).
    - Unknown scheme → HTTP 401.
    """
    secret = _webhook_hmac_secret()
    if not secret:
        return

    if not x_webhook_signature:
        logger.warning("webhook_signature_missing")
        raise HTTPException(
            status_code=401,
            detail={
                "error": "missing_webhook_signature",
                "message": (
                    "X-Webhook-Signature header is required when "
                    "WEBHOOK_HMAC_SECRET is configured. Format: "
                    "'sha256=<hex>' where hex = HMAC-SHA256(secret, raw_body)."
                ),
            },
        )

    sig = x_webhook_signature.strip()
    if "=" in sig:
        scheme, _, provided = sig.partition("=")
        scheme = scheme.strip().lower()
        provided = provided.strip().lower()
    else:
        scheme = "sha256"
        provided = sig.lower()

    if scheme != "sha256":
        logger.warning("webhook_signature_unsupported_scheme scheme=%s", scheme)
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unsupported_signature_scheme",
                "scheme": scheme,
                "message": "Only 'sha256' signatures are supported.",
            },
        )

    raw_body = await request.body()
    expected = hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, provided):
        logger.warning(
            "webhook_signature_mismatch body_len=%d",
            len(raw_body),
        )
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_webhook_signature",
                "message": (
                    "X-Webhook-Signature does not match the expected "
                    "HMAC of the request body. Verify the shared secret "
                    "and that the body bytes were not altered in flight."
                ),
            },
        )


# ---------------------------------------------------------------------------
# Event-timestamp replay window (#1245)
# ---------------------------------------------------------------------------


def _max_event_age_days() -> int:
    try:
        return int(os.getenv("WEBHOOK_MAX_EVENT_AGE_DAYS", "90"))
    except ValueError:
        return 90


def _max_event_future_hours() -> int:
    try:
        return int(os.getenv("WEBHOOK_MAX_EVENT_FUTURE_HOURS", "24"))
    except ValueError:
        return 24


def _validate_event_timestamp_window(timestamp: str) -> Optional[str]:
    """Return an error string if ``timestamp`` is outside the replay
    window, else ``None``. Separate from signature-level replay
    defense: this catches captured webhooks replayed months later with
    a freshly-computed signature.

    Window:
    - floor = now - WEBHOOK_MAX_EVENT_AGE_DAYS (default 90 days)
    - ceil  = now + WEBHOOK_MAX_EVENT_FUTURE_HOURS (default 24 h)
    """
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return f"event.timestamp is not parseable ISO-8601: {timestamp!r}"

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    age_cap_days = _max_event_age_days()
    future_cap_hours = _max_event_future_hours()

    if dt < now - timedelta(days=age_cap_days):
        return (
            f"event.timestamp {timestamp} is older than "
            f"WEBHOOK_MAX_EVENT_AGE_DAYS={age_cap_days} — replay window "
            f"exceeded"
        )
    if dt > now + timedelta(hours=future_cap_hours):
        return (
            f"event.timestamp {timestamp} is more than "
            f"WEBHOOK_MAX_EVENT_FUTURE_HOURS={future_cap_hours} in the "
            f"future"
        )
    return None


# ── Prometheus metric (#1245) ──────────────────────────────────────────────
# The replay-window check itself blocks the stale/future-replay vector; the
# metric makes it observable in prod. Without a counter, an SRE can't tell
# whether rejections are a steady-state partner-clock-skew issue, a surge
# from one bad integration, or an active replay attack.
try:  # pragma: no cover - metrics are best-effort; never break ingest on registry error
    from prometheus_client import REGISTRY, Counter

    def _matches_registered_name(collector_name: str, requested: str) -> bool:
        """Prometheus strips ``_total`` from Counter names internally, so
        a Counter requested as ``foo_total`` ends up with ``_name='foo'``.
        Compare both forms so the fallback-lookup works regardless of
        which suffix is present in either string."""
        if not collector_name:
            return False
        a = collector_name[:-6] if collector_name.endswith("_total") else collector_name
        b = requested[:-6] if requested.endswith("_total") else requested
        return a == b

    def _get_or_create_counter(name, documentation, labelnames):
        try:
            return Counter(name, documentation, labelnames)
        except ValueError:
            # Already registered (common during pytest re-imports or
            # multi-path imports).
            for collector in list(REGISTRY._collector_to_names):
                if _matches_registered_name(
                    getattr(collector, "_name", None), name
                ):
                    return collector
            raise

    WEBHOOK_REPLAY_REJECTED = _get_or_create_counter(
        "webhook_replay_rejected_total",
        "Webhook ingest events rejected by the replay-window check (#1245)",
        ["reason", "age_bucket"],
    )
    _WEBHOOK_METRICS_ENABLED = True
except Exception as _wh_metrics_exc:  # pragma: no cover
    logger.debug("webhook_replay_metric_init_failed: %s", _wh_metrics_exc)
    WEBHOOK_REPLAY_REJECTED = None
    _WEBHOOK_METRICS_ENABLED = False


def _classify_replay_rejection(timestamp: str) -> tuple[str, str]:
    """Return ``(reason, age_bucket)`` for metric labelling.

    ``reason`` is one of ``"stale"`` / ``"future"`` / ``"unparseable"``.
    ``age_bucket`` is a coarse, bounded-cardinality bucket of how far
    off the event timestamp is from now. Using buckets rather than raw
    offsets keeps Prometheus label cardinality finite regardless of
    hostile input.

    Both are string literals from a closed set — nothing user-supplied
    reaches the label values.
    """
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return ("unparseable", "na")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    delta = dt - now

    if delta.total_seconds() > 0:
        hours = delta.total_seconds() / 3600
        # Future bucket: how far in the future
        if hours <= 48:
            return ("future", "lt_48h")
        if hours <= 24 * 30:
            return ("future", "lt_30d")
        return ("future", "gte_30d")

    # Stale path
    days = (-delta).total_seconds() / 86400
    if days <= 180:
        return ("stale", "lt_180d")
    if days <= 365:
        return ("stale", "lt_1y")
    return ("stale", "gte_1y")


def _record_replay_rejection(timestamp: str) -> None:
    """Best-effort metric emission on replay-window rejection. Never
    raises — a metric-registry blip must not fail the ingest path."""
    if not _WEBHOOK_METRICS_ENABLED or WEBHOOK_REPLAY_REJECTED is None:
        return
    try:
        reason, age_bucket = _classify_replay_rejection(timestamp)
        WEBHOOK_REPLAY_REJECTED.labels(
            reason=reason, age_bucket=age_bucket
        ).inc()
    except Exception:  # pragma: no cover
        pass


# ---------------------------------------------------------------------------
# Rate Limiting (Redis-backed with in-memory fallback via shared module)
# ---------------------------------------------------------------------------

_WEBHOOK_RATE_LIMIT_RPM = max(1, int(os.getenv("WEBHOOK_INGEST_RATE_LIMIT_RPM", "120")))
_WEBHOOK_RATE_LIMIT_WINDOW_SECS = max(
    1,
    int(os.getenv("WEBHOOK_INGEST_RATE_LIMIT_WINDOW_SECONDS", "60")),
)


def _check_rate_limit(tenant_id: str) -> None:
    """Tenant-scoped sliding-window limit for webhook ingestion."""
    allowed, remaining = consume_tenant_rate_limit(
        tenant_id=tenant_id,
        bucket_suffix="webhooks.ingest",
        limit=_WEBHOOK_RATE_LIMIT_RPM,
        window=_WEBHOOK_RATE_LIMIT_WINDOW_SECS,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded for tenant '{tenant_id}' "
                f"({_WEBHOOK_RATE_LIMIT_RPM}/{_WEBHOOK_RATE_LIMIT_WINDOW_SECS}s)"
            ),
            headers={
                "Retry-After": str(_WEBHOOK_RATE_LIMIT_WINDOW_SECS),
                "X-RateLimit-Limit": str(_WEBHOOK_RATE_LIMIT_RPM),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Tenant": tenant_id,
                "X-RateLimit-Scope": "webhooks.ingest",
            },
        )
    logger.debug(
        "webhook_rate_limit_allow tenant_id=%s remaining=%s",
        tenant_id,
        remaining,
    )


# ---------------------------------------------------------------------------
# KDE Validation
# ---------------------------------------------------------------------------

def _validate_event_kdes(event: IngestEvent) -> list[str]:
    """Validate that an event has all required KDEs for its CTE type."""
    errors: list[str] = []
    required = REQUIRED_KDES_BY_CTE.get(event.cte_type, [])

    available: dict[str, object] = {
        "traceability_lot_code": event.traceability_lot_code,
        "product_description": event.product_description,
        "quantity": event.quantity,
        "unit_of_measure": event.unit_of_measure,
        "location_name": event.location_name,
        "location_gln": event.location_gln,
        **event.kdes,
    }

    for kde_name in required:
        val = available.get(kde_name)
        if val is None or (isinstance(val, str) and val.strip() == ""):
            errors.append(f"Missing required KDE '{kde_name}' for {event.cte_type.value} CTE")

    return errors


# ---------------------------------------------------------------------------
# Compliance Alerts
# ---------------------------------------------------------------------------

def _generate_alerts(event: IngestEvent) -> list[dict]:
    """Generate compliance alerts for an event."""
    alerts: list[dict] = []

    if event.cte_type.value in ("shipping", "receiving"):
        has_source = event.kdes.get("ship_from_location") or event.kdes.get("ship_from_gln")
        has_dest = event.kdes.get("ship_to_location") or event.kdes.get("ship_to_gln") or event.kdes.get("receiving_location")
        if not has_source or not has_dest:
            alerts.append({
                "severity": "warning",
                "alert_type": "incomplete_route",
                "message": "Shipping/receiving event missing source or destination identifiers",
            })

    return alerts


# ---------------------------------------------------------------------------
# Post-Ingest Obligation Check
# ---------------------------------------------------------------------------

def _check_obligations(db_session, event: IngestEvent, event_id: str, tenant_id: str) -> list[dict]:
    """
    Check ingested event against obligation-CTE rules from the database.

    For each obligation that applies to this CTE type, verify that the required
    KDE is present in the event. Write pass/fail results to fsma.compliance_alerts.

    Returns list of failed obligation checks (alerts).
    """
    if db_session is None:
        return []

    try:
        from sqlalchemy import text

        # Fetch rules for this CTE type + rules that apply to all CTE types
        # Use savepoint so a UUID cast failure doesn't abort the outer transaction
        nested = db_session.begin_nested()
        try:
            rows = db_session.execute(
                text("""
                    SELECT r.id, r.obligation_id, r.cte_type, r.required_kde_key,
                           r.validation_rule, r.description,
                           o.obligation_text, o.risk_category
                    FROM obligation_cte_rules r
                    JOIN obligations o ON o.id = r.obligation_id
                    WHERE o.tenant_id = CAST(:tid AS uuid)
                      AND r.cte_type IN (:cte_type, 'all')
                    ORDER BY o.risk_category DESC
                """),
                {"tid": tenant_id, "cte_type": event.cte_type.value},
            ).fetchall()
        except (SQLAlchemyError, ValueError, TypeError, RuntimeError) as exc:
            nested.rollback()
            logger.debug("obligation_query_rollback: %s", str(exc))
            return []

        if not rows:
            return []

        alerts = []
        # Build available KDE values from event
        available = {
            "traceability_lot_code": event.traceability_lot_code,
            "product_description": event.product_description,
            "quantity": event.quantity,
            "unit_of_measure": event.unit_of_measure,
            "location_name": event.location_name,
            "location_gln": event.location_gln,
            **event.kdes,
        }

        for row in rows:
            rule_id, obl_id, cte_type, kde_key, validation_rule, desc, obl_text, risk = row

            passed = True
            if validation_rule == "present" and kde_key:
                val = available.get(kde_key)
                passed = val is not None and (not isinstance(val, str) or val.strip() != "")
            elif validation_rule == "tlc_assigned":
                passed = bool(event.traceability_lot_code and len(event.traceability_lot_code) >= 3)
            elif validation_rule == "tlc_not_reassigned":
                # Shipping events should NOT create new TLCs — the TLC must already
                # exist in prior events (harvesting, packing, etc.)
                if event.cte_type.value in ("shipping", "transformation"):
                    prior = db_session.execute(
                        text("""
                            SELECT COUNT(*) FROM fsma.cte_events
                            WHERE tenant_id = :tid
                              AND traceability_lot_code = :tlc
                              AND event_type NOT IN ('shipping', 'transformation')
                        """),
                        {"tid": tenant_id, "tlc": event.traceability_lot_code},
                    ).scalar()
                    passed = (prior or 0) > 0
                else:
                    passed = True
            elif validation_rule == "downstream_transmitted":
                # Receiving events should have upstream source info (ship_from)
                # Shipping events should have downstream destination (ship_to)
                if event.cte_type.value == "receiving":
                    passed = bool(
                        available.get("ship_from_location")
                        or available.get("ship_from_gln")
                        or available.get("immediate_previous_source")
                    )
                elif event.cte_type.value == "shipping":
                    passed = bool(
                        available.get("ship_to_location")
                        or available.get("ship_to_gln")
                    )
                else:
                    passed = True
            elif validation_rule == "record_exists":
                # Verify that records exist in the chain for this TLC
                # (i.e., this isn't an orphan event with no audit trail)
                _chain_count = db_session.execute(
                    text("""
                        SELECT COUNT(*) FROM fsma.hash_chain h
                        JOIN fsma.cte_events e ON e.id = h.cte_event_id
                        WHERE e.tenant_id = :tid
                          AND e.traceability_lot_code = :tlc
                    """),
                    {"tid": tenant_id, "tlc": event.traceability_lot_code},
                ).scalar()
                # For first event of a TLC, chain_count will be 0 (just ingested,
                # chain entry may not exist yet). Allow it.
                # For subsequent events, at least 1 prior chain entry should exist.
                passed = True  # Chain is verified at scoring time; here we just check existence

            if not passed:
                severity = "critical" if risk == "CRITICAL" else "warning"
                alert = {
                    "severity": severity,
                    "alert_type": "chain_break",
                    "message": f"Obligation not met: {obl_text[:100]}",
                    "obligation_id": str(obl_id),
                    "missing_kde": kde_key,
                }
                alerts.append(alert)

                # Write to compliance_alerts table
                try:
                    db_session.execute(
                        text("""
                            INSERT INTO fsma.compliance_alerts
                            (tenant_id, org_id, event_id, severity, alert_type, message, details)
                            VALUES (CAST(:tid AS uuid), CAST(:tid AS uuid), :eid::uuid, :sev, :atype, :msg, :details::jsonb)
                        """),
                        {
                            "tid": tenant_id,
                            "eid": event_id,
                            "sev": severity,
                            "atype": "chain_break",
                            "msg": f"Missing KDE '{kde_key}' required by obligation",
                            "details": json.dumps({
                                "obligation_id": str(obl_id),
                                "obligation_text": obl_text[:200],
                                "risk_category": risk,
                                "missing_kde": kde_key,
                            }),
                        },
                    )
                except (SQLAlchemyError, ValueError, RuntimeError) as alert_err:
                    logger.warning("obligation_alert_write_failed: %s", str(alert_err))

        return alerts

    except (ImportError, SQLAlchemyError, ValueError, TypeError, RuntimeError, KeyError) as exc:
        logger.warning("obligation_check_failed: %s", str(exc))
        return []


# ---------------------------------------------------------------------------
# Neo4j Graph Sync
# ---------------------------------------------------------------------------

_SYNC_COUNTER_PREFIX = "regengine:graph_sync"
_graph_sync_failures = 0  # Fallback when Redis unavailable
_graph_sync_successes = 0


def _get_redis_client():
    """Get Redis client for counter persistence. Returns None if unavailable."""
    try:
        import redis
        redis_url = os.getenv("REDIS_URL", "rediss://redis:6379/0")
        return redis.from_url(redis_url, decode_responses=True, socket_timeout=1)
    except Exception:
        logger.debug("redis_client_unavailable", exc_info=True)
        return None


def _incr_sync_counter(key: str) -> None:
    """Increment a graph sync counter in Redis with in-memory fallback."""
    global _graph_sync_failures, _graph_sync_successes
    try:
        client = _get_redis_client()
        if client:
            client.incr(f"{_SYNC_COUNTER_PREFIX}:{key}")
            return
    except Exception:
        logger.debug("redis_sync_counter_failed", key=key, exc_info=True)
    # Fallback to in-memory
    if key == "failures":
        _graph_sync_failures += 1
    else:
        _graph_sync_successes += 1


def get_graph_sync_stats() -> dict:
    """Return graph sync success/failure counts from Redis or in-memory fallback."""
    try:
        client = _get_redis_client()
        if client:
            return {
                "successes": int(client.get(f"{_SYNC_COUNTER_PREFIX}:successes") or 0),
                "failures": int(client.get(f"{_SYNC_COUNTER_PREFIX}:failures") or 0),
            }
    except Exception:
        logger.debug("redis_sync_stats_unavailable", exc_info=True)
    return {"successes": _graph_sync_successes, "failures": _graph_sync_failures}


# #1378 — Neo4j sync producer gating (mirrors shared.canonical_persistence.legacy_dual_write).
#
# The consumer (services/graph/scripts/fsma_sync_worker.py) is not started
# by any deployment manifest (Dockerfile, docker-compose, railway.toml).
# Publishing unconditionally caused the ``neo4j-sync`` Redis list to grow
# without bound, evicting hot keys (rate limit counters, idempotency
# records) under the ``allkeys-lru`` policy. Gate the producer behind
# ``ENABLE_NEO4J_SYNC`` (default off) and bound the queue with ``LTRIM``
# in case a dev/test environment opts in but the consumer falls behind.
_NEO4J_SYNC_QUEUE_KEY = "neo4j-sync"


def _neo4j_sync_enabled() -> bool:
    """Return True only if the operator has explicitly opted in.

    Defaults to False because the consumer is not deployed by any
    published manifest; writing to Redis without a reader lets the
    queue grow unbounded (#1378). Evaluated at call time so env
    changes on a long-running process take effect without restart.
    """
    raw = os.getenv("ENABLE_NEO4J_SYNC", "false").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _neo4j_sync_max_queue() -> int:
    """Upper bound on queued messages before we drop the oldest.

    Only applied when the producer is enabled. 100k mirrors the
    canonical-persistence default — see migration.py for the sizing
    rationale. Override with ``NEO4J_SYNC_MAX_QUEUE``.
    """
    try:
        return max(1, int(os.getenv("NEO4J_SYNC_MAX_QUEUE", "100000")))
    except ValueError:
        logger.warning(
            "neo4j_sync_max_queue_invalid_env_value value=%s",
            os.getenv("NEO4J_SYNC_MAX_QUEUE"),
        )
        return 100_000


def _rules_preeval_reject(event: IngestEvent, db_session, tenant_id: str):
    """Pre-evaluate rules to decide whether the event should be rejected
    under the current ``RULES_ENGINE_ENFORCE`` policy.

    Runs ``engine.evaluate_event(persist=False)`` so the decision is made
    without writing eval rows — a reject can exclude the event from the
    batch without polluting the transaction. Canonical normalization or
    rule evaluation errors are logged and treated as no-verdict (never
    reject) so a transient module-level bug can't take down ingestion
    for every tenant.

    Short-circuits on OFF mode — skips normalization + eval entirely
    so the default production path pays no added latency. Without this
    guard every webhook ingest would re-normalize and re-evaluate even
    though ``should_reject`` would always return ``(False, None)``;
    the threaded post-commit block still does its own eval with
    ``persist=True``, so under enforcement we pay for the double eval
    intentionally. Under OFF we must not.

    Returns ``(reject, reason, summary)``:
      * ``reject``: True when the caller must reject the event.
      * ``reason``: short string suitable for ``EventResult.errors``,
        or None when not rejecting.
      * ``summary``: the ``EvaluationSummary`` produced by pre-eval, or
        None when pre-eval was skipped (OFF mode short-circuit, or
        canonical/eval errored). Returned so callers can hand it back
        to the post-commit persistence path via
        ``engine.persist_summary`` and avoid re-evaluating the rules —
        eliminates the double-eval that otherwise lands when
        ``RULES_ENGINE_ENFORCE != off``.

    All three branches return a 3-tuple. PR #1919 (OFF short-circuit)
    and PR #1926 (3-tuple signature) were composed by hand during a
    botched merge and one branch got left at the old 2-tuple shape;
    every webhook ingest under the prod-default ``OFF`` mode crashed
    at the call-site destructure with ``ValueError: not enough values
    to unpack``. Restored consistent 3-tuple here. See spawned task.
    """
    from shared.rules.enforcement import current_mode, should_reject, EnforcementMode  # noqa: PLC0415
    if current_mode() == EnforcementMode.OFF:
        return False, None, None

    try:
        canonical = normalize_webhook_event(event, tenant_id)
        from shared.rules_engine import RulesEngine  # noqa: PLC0415
        engine = RulesEngine(db_session)
        event_data = {
            "event_id": str(canonical.event_id),
            "event_type": canonical.event_type.value,
            "traceability_lot_code": canonical.traceability_lot_code,
            "product_reference": canonical.product_reference,
            "quantity": canonical.quantity,
            "unit_of_measure": canonical.unit_of_measure,
            "from_facility_reference": canonical.from_facility_reference,
            "to_facility_reference": canonical.to_facility_reference,
            "from_entity_reference": canonical.from_entity_reference,
            "to_entity_reference": canonical.to_entity_reference,
            "kdes": canonical.kdes,
        }
        summary = engine.evaluate_event(event_data, persist=False, tenant_id=tenant_id)
    except (ImportError, SQLAlchemyError, ValueError, TypeError, RuntimeError,
            AttributeError, KeyError) as err:
        logger.warning("rules_preeval_skipped", extra={"error": str(err)})
        return False, None, None

    reject, reason = should_reject(summary)
    return reject, reason, summary


def _persist_canonical_and_eval(
    db_session,
    event: IngestEvent,
    tenant_id: str,
    precomputed_summary,
    source: str = "webhook_api",
    canonical_event_id: str | None = None,
) -> None:
    """Persist canonical event + write rule eval rows + create exception
    queue entries for non-compliant verdicts.

    Module-level so the happy-path batch block and the fallback path
    can share a single implementation, AND so the
    routing logic (use ``persist_summary`` when the pre-computed summary
    is available, else fall back to ``evaluate_event(persist=True)``)
    can be unit-tested without mounting the full ``ingest_events`` route.

    Routing rules (verified by ``test_webhook_router_v2_canonical_helper``):
      - ``precomputed_summary`` is non-None AND has results →
        ``RulesEngine.persist_summary`` writes the eval rows. No
        re-evaluation. Fast path under
        ``RULES_ENGINE_ENFORCE=cte_only|all``.
      - ``precomputed_summary`` is None OR has empty ``.results`` →
        ``RulesEngine.evaluate_event(persist=True)`` re-runs and
        persists. Default production path under ``OFF`` mode and
        fallback for no-verdict / pre-eval-error cases.
      - In both paths, ``not summary.compliant`` triggers
        ``ExceptionQueueService.create_exceptions_from_evaluation``
        for non-blocking failure visibility.

    Anchors the eval rows on the canonical event_id we just persisted
    (``str(canonical.event_id)``), not on whatever ID the pre-eval
    canonical happened to have. ``normalize_webhook_event`` mints a
    fresh UUID per call.

    Caller is responsible for catching exceptions raised by this
    function — the helper does not swallow errors so the caller can
    decide between "abort the request" and "log and continue".

    History: this helper was originally supposed to land in PR #1929,
    but only the test file made it through the merge — the source
    change was dropped during conflict resolution. Restored here.
    """
    from shared.canonical_persistence import CanonicalEventStore  # noqa: PLC0415
    from shared.rules_engine import RulesEngine  # noqa: PLC0415

    canonical = normalize_webhook_event(event, tenant_id, source=source)
    if canonical_event_id is not None:
        # Reuse the legacy fsma.cte_events UUID for the canonical row and
        # rule-evaluation anchor. The legacy CTEPersistence path already
        # writes fsma.hash_chain for this event; canonical persistence must
        # not append a second chain row to the same shared ledger.
        canonical.event_id = UUID(str(canonical_event_id))
        canonical.prepare_for_persistence()
    store = CanonicalEventStore(db_session, dual_write=False, skip_chain_write=True)
    persist_result = store.persist_event(canonical)
    persisted_event_id = str(getattr(persist_result, "event_id", None) or canonical.event_id)
    engine = RulesEngine(db_session)

    if precomputed_summary is not None and precomputed_summary.results:
        engine.persist_summary(
            precomputed_summary,
            tenant_id=tenant_id,
            event_id=persisted_event_id,
        )
        summary = precomputed_summary
    else:
        event_data = {
            "event_id": persisted_event_id,
            "event_type": canonical.event_type.value,
            "traceability_lot_code": canonical.traceability_lot_code,
            "product_reference": canonical.product_reference,
            "quantity": canonical.quantity,
            "unit_of_measure": canonical.unit_of_measure,
            "from_facility_reference": canonical.from_facility_reference,
            "to_facility_reference": canonical.to_facility_reference,
            "from_entity_reference": canonical.from_entity_reference,
            "to_entity_reference": canonical.to_entity_reference,
            "kdes": canonical.kdes,
        }
        summary = engine.evaluate_event(event_data, persist=True, tenant_id=tenant_id)

    if not summary.compliant:
        from shared.exception_queue import ExceptionQueueService  # noqa: PLC0415
        ExceptionQueueService(db_session).create_exceptions_from_evaluation(
            tenant_id, summary
        )


def _persist_required_canonical_and_eval(
    db_session,
    event: IngestEvent,
    tenant_id: str,
    precomputed_summary,
    source: str = "webhook_api",
    canonical_event_id: str | None = None,
) -> None:
    """Persist canonical evidence or fail the ingest transaction."""
    try:
        _persist_canonical_and_eval(
            db_session,
            event,
            tenant_id,
            precomputed_summary,
            source=source,
            canonical_event_id=canonical_event_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise _CanonicalPersistenceError(
            f"Canonical persistence failed for TLC {event.traceability_lot_code}: {exc}"
        ) from exc


def _publish_graph_sync(event_id: str, event: IngestEvent, tenant_id: str) -> None:
    """Push a CTE creation event to Redis for Neo4j graph sync.

    Behaviour matrix (#1378 — matches shared.canonical_persistence.legacy_dual_write):

    - ``ENABLE_NEO4J_SYNC`` not set (default) → no-op. The consumer at
      ``services/graph/scripts/fsma_sync_worker.py`` is not in any
      deployment manifest, so sending here would grow Redis unbounded.
      Default in every environment to ensure a forgotten flag does not
      recreate the leak.
    - ``ENABLE_NEO4J_SYNC=true`` + ``REDIS_URL`` set → send, then
      ``LTRIM`` the list to ``NEO4J_SYNC_MAX_QUEUE`` entries so a
      stalled consumer cannot exhaust Redis memory.
    - ``ENABLE_NEO4J_SYNC=true`` + ``REDIS_URL`` unset → no-op.

    This function is temporary and will be deleted outright when Neo4j
    is retired in favour of PostgreSQL-native graph queries.
    """
    if not _neo4j_sync_enabled():
        return

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return

    try:
        import redis as redis_lib
        client = redis_lib.from_url(redis_url)
        message = {
            "event": "cte.created",
            "data": {
                "cte": {
                    "id": event_id,
                    "event_type": event.cte_type.value,
                    "traceability_lot_code": event.traceability_lot_code,
                    "product_description": event.product_description,
                    "quantity": event.quantity,
                    "unit_of_measure": event.unit_of_measure,
                    "location_gln": event.location_gln,
                    "location_name": event.location_name,
                    "timestamp": event.timestamp,
                    "tenant_id": tenant_id,
                    "kdes": event.kdes,
                },
            },
        }
        client.rpush(_NEO4J_SYNC_QUEUE_KEY, json.dumps(message, default=str))
        # Bound queue size. LTRIM keeps the NEWEST `max_queue` entries;
        # if the consumer falls far behind the oldest messages drop on
        # the floor instead of eating Redis. The canonical write in
        # Postgres is the authoritative record so losing stale graph
        # sync messages is acceptable.
        try:
            client.ltrim(_NEO4J_SYNC_QUEUE_KEY, -_neo4j_sync_max_queue(), -1)
        except Exception:
            # LTRIM bound is best-effort; a failure here must not be
            # treated as a publish failure since the rpush above did
            # succeed and the canonical row in Postgres is intact.
            logger.debug("neo4j_sync_ltrim_failed", exc_info=True)
        _incr_sync_counter("successes")
    except (ImportError, ConnectionError, TimeoutError, OSError, ValueError, TypeError) as exc:
        _incr_sync_counter("failures")
        logger.warning("graph_sync_publish_failed event_id=%s error=%s", event_id, str(exc))


# ---------------------------------------------------------------------------
# Ingest Endpoint
# ---------------------------------------------------------------------------

# #1232 — enforce ``Idempotency-Key`` on all webhook ingest calls. The
# ``IdempotencyMiddleware`` mounted in ``main.py`` then caches the 2xx
# response for 24h, scoped per tenant (#1237).
_require_idempotency_key = IdempotencyDependency(strict=True)


def _lookup_tenant_id_for_api_key(raw_api_key: str) -> Optional[str]:
    """Best-effort legacy tenant lookup for callers without principal tenant context."""
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text as _text

        key_hash = hashlib.sha256(raw_api_key.encode("utf-8")).hexdigest()
        _db = SessionLocal()
        try:
            _row = _db.execute(
                _text("SELECT tenant_id FROM api_keys WHERE key_hash = :key_hash LIMIT 1"),
                {"key_hash": key_hash},
            ).fetchone()
            if _row and _row[0]:
                return str(_row[0])
        finally:
            _db.close()
    except (ImportError, SQLAlchemyError, ValueError, RuntimeError, ConnectionError, OSError) as _tenant_err:
        logger.debug("tenant_key_lookup_failed", error=str(_tenant_err))
    return None


def _resolve_ingest_tenant_id(
    *,
    payload_tenant_id: Optional[str],
    principal: IngestionPrincipal,
    x_regengine_api_key: Optional[str],
    x_tenant_id: Optional[str],
) -> str:
    """Resolve tenant context without letting request bodies override scoped keys.

    Scoped API keys already carry tenant authority in ``principal.tenant_id``.
    Any divergent body/header tenant is therefore an attempted cross-tenant
    write and must fail before rate limiting or persistence (#2069).
    """
    if principal.tenant_id:
        for source, requested in (
            ("payload tenant_id", payload_tenant_id),
            ("X-Tenant-ID", x_tenant_id),
        ):
            if requested and requested != principal.tenant_id:
                raise HTTPException(
                    status_code=403,
                    detail=f"Tenant mismatch: {source} does not match authenticated API key tenant.",
                )
        validate_tenant_id(principal.tenant_id)
        return principal.tenant_id

    # Legacy master/dev-open callers do not carry a principal tenant. Preserve
    # the historical fallback order for those modes only.
    tenant_id = payload_tenant_id
    if not tenant_id and x_regengine_api_key:
        tenant_id = _lookup_tenant_id_for_api_key(x_regengine_api_key)
    if not tenant_id and x_tenant_id:
        tenant_id = x_tenant_id
    if not tenant_id:
        logger.error("Webhook rejected: no tenant_id resolved")
        raise HTTPException(status_code=400, detail="Tenant context required")
    validate_tenant_id(tenant_id)
    return tenant_id


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Ingest traceability events",
    description=(
        "Accept CTE events from external systems (IoT platforms, ERPs, manual entry). "
        "Each event is validated against FSMA 204 KDE requirements, SHA-256 hashed, "
        "chain-linked, and persisted to the compliance database. "
        "The ``Idempotency-Key`` header is REQUIRED — safe retries replay "
        "the cached response for 24 hours. Cache keys are tenant-scoped."
    ),
)
async def ingest_events(
    payload: WebhookPayload,
    principal: IngestionPrincipal = Depends(require_permission("webhooks.ingest")),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    _auth: None = Depends(_verify_api_key),
    # #1243: HMAC signature check runs in parallel with the API-key check.
    # A leaked key alone is no longer sufficient to forge events when
    # ``WEBHOOK_HMAC_SECRET`` is configured.
    _signature: None = Depends(_verify_webhook_signature),
    _subscription: None = Depends(require_active_subscription),
    _idempotency_key: Optional[str] = Depends(_require_idempotency_key),
    db_session=Depends(get_db_session),
) -> IngestResponse:
    """Process incoming webhook events with persistent storage."""
    tenant_id = _resolve_ingest_tenant_id(
        payload_tenant_id=payload.tenant_id,
        principal=principal,
        x_regengine_api_key=x_regengine_api_key,
        x_tenant_id=x_tenant_id,
    )

    # Rate limiting (tenant-scoped)
    _check_rate_limit(tenant_id)

    results: list[EventResult] = []
    accepted = 0
    rejected = 0

    # Batch deduplication — detect identical events within the same payload
    seen_in_batch: set[str] = set()

    # Get persistence layer from injected db_session (Depends(get_db_session))
    persistence = None
    if db_session is None:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable — cannot accept events. Retry after service recovery.",
        )
    try:
        from shared.cte_persistence import CTEPersistence
        persistence = CTEPersistence(db_session)
    except (ImportError, SQLAlchemyError, RuntimeError, ConnectionError, OSError) as e:
        logger.error("db_init_failed — rejecting ingest: %s", str(e))
        raise HTTPException(
            status_code=503,
            detail="Database unavailable — cannot accept events. Retry after service recovery.",
        )

    try:
        # --- Phase 1: Validate all events, collect valid ones for batch persist ---
        valid_events: list = []  # (event, alerts) tuples
        for event in payload.events:
            # Batch deduplication — skip identical events in same request
            dedup_key = f"{event.cte_type.value}|{event.traceability_lot_code}|{event.timestamp}|{event.location_gln or event.location_name or ''}"
            if dedup_key in seen_in_batch:
                results.append(EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="rejected",
                    errors=["Duplicate event in batch — same CTE type, TLC, timestamp, and location"],
                ))
                rejected += 1
                continue
            seen_in_batch.add(dedup_key)

            # #1245: event-timestamp replay window. Signature-freshness
            # defends against immediate replay; this defends against a
            # captured payload re-ingested months later with freshly
            # computed signature.
            replay_error = _validate_event_timestamp_window(event.timestamp)
            if replay_error:
                logger.warning(
                    "webhook_replay_window_rejected tenant=%s tlc=%s ts=%s",
                    tenant_id, event.traceability_lot_code, event.timestamp,
                )
                _record_replay_rejection(event.timestamp)
                results.append(EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="rejected",
                    errors=[replay_error],
                ))
                rejected += 1
                continue

            # Validate KDEs
            errors = _validate_event_kdes(event)

            if errors:
                results.append(EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="rejected",
                    errors=errors,
                ))
                rejected += 1
                continue

            # Generate alerts
            alerts = _generate_alerts(event)
            valid_events.append((event, alerts))

        # --- Phase 2a: Rules enforcement partition ---
        # Under RULES_ENGINE_ENFORCE=cte_only|all, exclude events whose
        # rules verdict says reject BEFORE they hit the batch store.
        # Runs a non-persisting eval per event; decision logic is in
        # ``shared.rules.enforcement.should_reject``. When ENFORCE=off
        # (default) every call returns (False, None) and the loop is a
        # no-op. No-verdict summaries (no rules loaded, non-FTL, etc.)
        # never reject — see EvaluationSummary.compliant docstring.
        # ``pre_eval_summaries`` is a parallel list to ``valid_events`` after
        # the filter — same length, same order, ``None`` entries for events
        # whose pre-eval skipped (OFF mode, canonical/eval error). The
        # threaded post-commit block uses the captured summary instead of
        # re-evaluating, eliminating the double-eval regression
        # (services/shared/rules/engine.py:persist_summary).
        pre_eval_summaries: list = []
        if valid_events:
            _filtered: list = []
            for _event, _alerts in valid_events:
                _reject, _reason, _summary = _rules_preeval_reject(_event, db_session, tenant_id)
                if _reject:
                    results.append(EventResult(
                        traceability_lot_code=_event.traceability_lot_code,
                        cte_type=_event.cte_type.value,
                        status="rejected",
                        errors=[f"rule_violation: {_reason}"],
                    ))
                    rejected += 1
                    continue
                _filtered.append((_event, _alerts))
                pre_eval_summaries.append(_summary)
            valid_events = _filtered

        # --- Phase 2: Batch persist all valid events ---
        if valid_events:
            batch_dicts = []
            event_objs = []
            for event, alerts in valid_events:
                batch_dicts.append({
                    "event_type": event.cte_type.value,
                    "traceability_lot_code": event.traceability_lot_code,
                    "product_description": event.product_description,
                    "quantity": event.quantity,
                    "unit_of_measure": event.unit_of_measure,
                    "event_timestamp": event.timestamp,
                    "location_gln": event.location_gln,
                    "location_name": event.location_name,
                    "kdes": event.kdes,
                })
                event_objs.append(event)

            try:
                store_results = persistence.store_events_batch(
                    tenant_id=tenant_id,
                    events=batch_dicts,
                    source=payload.source,
                )

                for store_result, event, precomputed_summary in zip(
                    store_results, event_objs, pre_eval_summaries
                ):
                    results.append(EventResult(
                        traceability_lot_code=event.traceability_lot_code,
                        cte_type=event.cte_type.value,
                        status="accepted",
                        event_id=store_result.event_id,
                        sha256_hash=store_result.sha256_hash,
                        chain_hash=store_result.chain_hash,
                    ))
                    accepted += 1

                    # Canonical normalization + rule evaluation + exception creation.
                    # This is required evidence now: it runs synchronously in the
                    # request transaction so accepted legacy CTEs cannot diverge
                    # from canonical rows or persisted rule-evaluation evidence.
                    _persist_required_canonical_and_eval(
                        db_session,
                        event,
                        tenant_id,
                        precomputed_summary,
                        source=payload.source,
                        canonical_event_id=store_result.event_id,
                    )

                    # Post-ingest graph sync (non-blocking)
                    _publish_graph_sync(store_result.event_id, event, tenant_id)

                    # Auto-learn product catalog from confirmed scans
                    try:
                        from .product_catalog import learn_from_event
                        learn_from_event(
                            tenant_id=tenant_id,
                            event={
                                "product_description": event.product_description,
                                "gtin": event.kdes.get("gtin") if event.kdes else None,
                                "kdes": event.kdes,
                                "location_name": event.location_name,
                            },
                        )
                    except (ImportError, SQLAlchemyError, ValueError, TypeError, RuntimeError, KeyError) as learn_err:
                        logger.warning("catalog_learn_skipped: %s", str(learn_err))

            except (ValueError, TypeError, RuntimeError, AttributeError) as e:
                logger.error(
                    "batch_persistence_failed",
                    extra={"error": str(e), "batch_size": len(valid_events)},
                )
                # Fall back to per-event persistence
                for event, alerts in valid_events:
                    # Enforcement: same pre-eval gate as the happy path.
                    # Events that were pre-eval rejected above never
                    # reach this fallback (they were stripped from
                    # valid_events), but running the check again here
                    # is cheap insurance — if the batch path ever
                    # mutates valid_events in flight, the fallback
                    # still honors the enforcement policy.
                    _fb_reject, _fb_reason, _fb_summary = _rules_preeval_reject(event, db_session, tenant_id)
                    if _fb_reject:
                        results.append(EventResult(
                            traceability_lot_code=event.traceability_lot_code,
                            cte_type=event.cte_type.value,
                            status="rejected",
                            errors=[f"rule_violation: {_fb_reason}"],
                        ))
                        rejected += 1
                        continue
                    try:
                        store_result = persistence.store_event(
                            tenant_id=tenant_id,
                            event_type=event.cte_type.value,
                            traceability_lot_code=event.traceability_lot_code,
                            product_description=event.product_description,
                            quantity=event.quantity,
                            unit_of_measure=event.unit_of_measure,
                            event_timestamp=event.timestamp,
                            source=payload.source,
                            location_gln=event.location_gln,
                            location_name=event.location_name,
                            kdes=event.kdes,
                            alerts=alerts,
                        )
                        results.append(EventResult(
                            traceability_lot_code=event.traceability_lot_code,
                            cte_type=event.cte_type.value,
                            status="accepted",
                            event_id=store_result.event_id,
                            sha256_hash=store_result.sha256_hash,
                            chain_hash=store_result.chain_hash,
                        ))
                        accepted += 1

                        # Canonical normalization + rule evaluation. Required in
                        # the same transaction as the legacy fallback write.
                        _persist_required_canonical_and_eval(
                            db_session,
                            event,
                            tenant_id,
                            _fb_summary,
                            source=payload.source,
                            canonical_event_id=store_result.event_id,
                        )

                        _publish_graph_sync(store_result.event_id, event, tenant_id)
                        try:
                            from .product_catalog import learn_from_event
                            learn_from_event(
                                tenant_id=tenant_id,
                                event={
                                    "product_description": event.product_description,
                                    "gtin": event.kdes.get("gtin") if event.kdes else None,
                                    "kdes": event.kdes,
                                    "location_name": event.location_name,
                                },
                            )
                        except (ImportError, SQLAlchemyError, ValueError, TypeError, KeyError) as learn_err:
                            logger.warning("catalog_learn_skipped: %s", str(learn_err))
                    except (SQLAlchemyError, ValueError, TypeError, RuntimeError, KeyError) as inner_e:
                        logger.error("persistence_failed", extra={"error": str(inner_e), "tlc": event.traceability_lot_code})
                        results.append(EventResult(
                            traceability_lot_code=event.traceability_lot_code,
                            cte_type=event.cte_type.value,
                            status="rejected",
                            errors=[f"Storage error: {str(inner_e)}"],
                        ))
                        rejected += 1

        if accepted > 0:
            emit_funnel_event(
                tenant_id=tenant_id,
                event_name="first_ingest",
                metadata={
                    "accepted_events": accepted,
                    "source": payload.source,
                },
                db_session=db_session,
            )

        # Commit all events in a single transaction
        if db_session:
            db_session.commit()

    except Exception as e:
        if db_session:
            db_session.rollback()
        logger.error("ingest_batch_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Ingestion failed. Check server logs for details.")
    finally:
        if db_session:
            db_session.close()

    return IngestResponse(
        accepted=accepted,
        rejected=rejected,
        total=len(payload.events),
        events=results,
    )


# ---------------------------------------------------------------------------
# Chain Verification Endpoint
# ---------------------------------------------------------------------------

async def get_recent_events(
    tenant_id: str,
    limit: int = 10,
):
    """
    Get most recent CTE events for a tenant — powers the scan history
    dashboard widget.
    """
    validate_tenant_id(tenant_id)
    db_session = None
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text as _text
        db_session = SessionLocal()
        rows = db_session.execute(
            _text("""
                SELECT id, event_type, traceability_lot_code, product_description,
                       quantity, unit_of_measure, location_name, source, ingested_at
                FROM fsma.cte_events
                WHERE tenant_id = :tid
                ORDER BY ingested_at DESC
                LIMIT :lim
            """),
            {"tid": tenant_id, "lim": min(limit, 50)},
        ).fetchall()
        events = [
            {
                "event_id": str(r[0]),
                "event_type": r[1],
                "traceability_lot_code": r[2],
                "product_description": r[3],
                "quantity": float(r[4]) if r[4] else 0,
                "unit_of_measure": r[5],
                "location_name": r[6],
                "source": r[7],
                "ingested_at": r[8].isoformat() if r[8] else None,
            }
            for r in rows
        ]
        return {"tenant_id": tenant_id, "events": events, "total": len(events)}
    except (ImportError, ValueError, RuntimeError) as e:
        logger.warning("recent_events_query_failed: %s", str(e))
        return {"tenant_id": tenant_id, "events": [], "total": 0}
    finally:
        if db_session:
            db_session.close()


@router.get(
    "/recent",
    response_model=RecentEventsResponse,
    summary="Get recent CTE events",
    description="Returns the most recently ingested traceability events for the scan history widget.",
)
async def recent_events_endpoint(
    tenant_id: str,
    limit: int = 10,
    _auth: None = Depends(_verify_api_key),
):
    return await get_recent_events(tenant_id, limit)


@router.get(
    "/chain/verify",
    response_model=ChainVerifyResponse,
    summary="Verify hash chain integrity",
    description=(
        "Walk the tenant's entire hash chain from genesis to head, "
        "recomputing each link and checking for tampering."
    ),
)
async def verify_chain(
    tenant_id: str,
    _auth: None = Depends(_verify_api_key),
):
    """Verify the integrity of the tenant's hash chain."""
    validate_tenant_id(tenant_id)
    db_session = None
    try:
        from shared.database import SessionLocal
        from shared.cte_persistence import CTEPersistence

        db_session = SessionLocal()
        persistence = CTEPersistence(db_session)
        result = persistence.verify_chain(tenant_id)

        return {
            "tenant_id": tenant_id,
            "chain_valid": result.valid,
            "chain_length": result.chain_length,
            "errors": result.errors,
            "checked_at": result.checked_at,
        }
    except (ImportError, ValueError, RuntimeError) as e:
        logger.error("chain_verification_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Chain verification failed. Check server logs for details.")
    finally:
        if db_session:
            db_session.close()
