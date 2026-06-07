"""HMAC-based message authentication for RegEngine Kafka traffic (#1078).

Before this module, consumers took ``tenant_id`` directly from the Kafka
event body and routed writes (Neo4j tenant DB selection, FSMA audit
writes, graph upserts) based on whatever value the message claimed.
There was no producer authentication and no broker-level ACLs, so any
actor with publish access to ``ingest.normalized`` or ``graph.update``
could forge events tagged with another tenant's id — producing
cross-tenant data contamination that is *invisible* in the audit log,
because the tenant_id recorded *matches the injected value*.

This module implements the near-term remediation from the security
issue: message-level HMAC-SHA256 signatures over a canonical
representation of the event, bound to an authenticated producer
identity that consumers allowlist per-topic.

Design:

* **Serializer-agnostic.** We canonicalize the *dict* form (sorted keys,
  compact separators) rather than the raw bytes. This means both
  the legacy JSON producer path and ``confluent-kafka``
  (custom ``value.deserializer``) consumers can verify the same
  producer's messages without having to agree on a specific byte-level
  encoding. The only requirement is that the dict survives the
  round-trip — which both JSON and Avro-over-Kafka-Schema-Registry
  preserve for our payloads.

* **Signature lives in Kafka headers**, not in the body, so adding
  signing does not break downstream schema validators that don't know
  about ``_producer_service`` / ``_signed_at``. Those two fields are
  added to the body only because they MUST be covered by the signature
  (otherwise an attacker could replay a valid signature but swap the
  producer claim).

* **Rollout-safe.** :func:`verify_event` accepts ``strict=False`` so a
  consumer can be deployed before every producer is signing. The
  default is strict, and ``KAFKA_SIGNATURE_STRICT=false`` in the
  environment downgrades rejections to warnings during the rollout
  window. Flip the env back to true once all producers have rolled.

* **Per-producer-service signing keys (RE-SEC-004).** Each producer
  service holds its OWN HMAC key, looked up by the verified
  ``_producer_service`` body claim — the producer_service IS the kid.
  Cross-service forgery is bound by per-service key possession: a
  compromised nlp-service can no longer sign as ingestion-service.

  Env-var convention (one per service)::

      KAFKA_SIGNING_KEY_NLP
      KAFKA_SIGNING_KEY_INGESTION
      KAFKA_SIGNING_KEY_GRAPH
      KAFKA_SIGNING_KEY_ADMIN
      KAFKA_SIGNING_KEY_SCHEDULER

  Plus a ``..._PREVIOUS`` mirror for zero-downtime rotation (verify
  accepts current OR previous; sign always uses current).

  ``KAFKA_EVENT_SIGNING_KEY`` (legacy single shared key) is still
  honored as a fallback during rollout. Three-phase plan:

    Phase 1 (this module): land the per-service resolver. With only
        ``KAFKA_EVENT_SIGNING_KEY`` set, behavior is unchanged.
    Phase 2 (deploy step): set ``KAFKA_SIGNING_KEY_<SERVICE>`` in each
        service's deploy config; keep the legacy var set as a
        transition fallback.
    Phase 3 (after-rollout-2026-Q3): remove ``KAFKA_EVENT_SIGNING_KEY``
        from all envs and delete the legacy fallback below — see the
        ``TODO(after-rollout-2026-Q3)`` marker on
        :data:`LEGACY_SHARED_KEY_ENV`.

The broker-level remediation (SASL_SSL + per-topic ACLs) is infra
work that is out of scope for this PR and tracked separately in the
issue body.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping

import structlog

logger = structlog.get_logger("shared.kafka_auth")


# Kafka header names. Lower-case ASCII is safest across clients;
# Kafka clients preserve case but some
# brokers normalize, so we stick to a conservative convention.
HEADER_SIGNATURE = "x-evt-sig"
HEADER_PRODUCER_SERVICE = "x-producer-service"
HEADER_SIG_VERSION = "x-evt-sig-v"

# The current signature scheme. Bumping this is how we retire the
# existing scheme without breaking in-flight messages.
CURRENT_SIG_VERSION = "v1"

# Fields added to the event body that are covered by the signature.
# Callers MUST NOT rely on these being absent — they appear on every
# signed message. :func:`verify_event` returns the dict with them
# intact so downstream code can log the producer claim if useful.
BODY_FIELD_PRODUCER_SERVICE = "_producer_service"
BODY_FIELD_SIGNED_AT = "_signed_at"


# Env var names. Kept module-level so tests can monkeypatch / override.
ENV_SIGNING_KEY = "KAFKA_EVENT_SIGNING_KEY"
ENV_STRICT = "KAFKA_SIGNATURE_STRICT"
ENV_MAX_SIG_AGE = "KAFKA_MAX_SIGNATURE_AGE_SECONDS"

# Per-producer-service signing keys (RE-SEC-004). Each producer holds its
# own HMAC secret; consumers see all of them and resolve the right one
# from the verified ``_producer_service`` body claim. Add new entries
# here when a new producer service comes online.
_PRODUCER_KEY_ENV_MAP: dict[str, str] = {
    "nlp-service": "KAFKA_SIGNING_KEY_NLP",
    "ingestion-service": "KAFKA_SIGNING_KEY_INGESTION",
    "graph-service": "KAFKA_SIGNING_KEY_GRAPH",
    "admin-service": "KAFKA_SIGNING_KEY_ADMIN",
    "scheduler-service": "KAFKA_SIGNING_KEY_SCHEDULER",
}

# Per-service "previous" keys used during a rotation overlap window.
# When a service rotates from old-key -> new-key, operators set the
# current var to new-key and the *_PREVIOUS var to old-key for one
# deploy cycle so consumers accept envelopes signed with either.
# After the rotation deploy lands across all consumers, the *_PREVIOUS
# var is unset.
_PRODUCER_PREVIOUS_KEY_ENV_MAP: dict[str, str] = {
    "nlp-service": "KAFKA_SIGNING_KEY_NLP_PREVIOUS",
    "ingestion-service": "KAFKA_SIGNING_KEY_INGESTION_PREVIOUS",
    "graph-service": "KAFKA_SIGNING_KEY_GRAPH_PREVIOUS",
    "admin-service": "KAFKA_SIGNING_KEY_ADMIN_PREVIOUS",
    "scheduler-service": "KAFKA_SIGNING_KEY_SCHEDULER_PREVIOUS",
}

# TODO(after-rollout-2026-Q3): once every producer service has rolled
# to per-service keys (Phase 2 deploy) and we have run for a few weeks
# with all envelopes verifying via per-service keys, drop this constant
# AND the legacy branch in :func:`_resolve_verification_keys` /
# :func:`_resolve_producer_signing_key`. At that point, an envelope
# whose ``_producer_service`` is not in the map is a hard reject.
LEGACY_SHARED_KEY_ENV = ENV_SIGNING_KEY


# Replay-protection freshness window for `_signed_at` (RE-SEC-003).
# A signed envelope older than this is rejected post-HMAC even if the
# signature is otherwise valid; combined with the NLP header-trust fix
# (RE-SEC-001) this closes the per-tenant replay primitive.
DEFAULT_MAX_SIGNATURE_AGE_SECONDS = 900  # 15 minutes
# Tolerated clock-skew window for envelopes timestamped slightly in the
# future. Anything beyond this is treated as a forgery / clock attack.
SIGNATURE_FUTURE_SKEW_SECONDS = 60


def _max_signature_age() -> int:
    """Read the freshness window from env, falling back to the default."""
    raw = os.environ.get(ENV_MAX_SIG_AGE)
    if raw is None:
        return DEFAULT_MAX_SIGNATURE_AGE_SECONDS
    try:
        return int(raw)
    except (ValueError, TypeError):
        return DEFAULT_MAX_SIGNATURE_AGE_SECONDS


# -----------------------------------------------------------------------------
# Errors
# -----------------------------------------------------------------------------


class KafkaAuthError(Exception):
    """Raised when a message fails authentication.

    Callers should DLQ the message, commit the offset (so the poison
    pill doesn't block the partition), and surface the failure as a
    metric + structured log — never fall back to "process anyway", and
    never retry: an attacker-controlled signature will never verify
    no matter how many times you read the record.
    """

    def __init__(self, reason: str, **fields: Any) -> None:
        super().__init__(reason)
        self.reason = reason
        self.fields = fields

    def __str__(self) -> str:
        if self.fields:
            parts = ", ".join(f"{k}={v}" for k, v in self.fields.items())
            return f"{self.reason} ({parts})"
        return self.reason


# -----------------------------------------------------------------------------
# Key / config resolution
# -----------------------------------------------------------------------------


def _coerce_key(value: bytes | str | None) -> bytes | None:
    """Normalize a key value to bytes (or None for empty)."""
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return value.encode("utf-8")
    return value


def _resolve_producer_signing_key(
    producer_service: str,
    signing_key: bytes | str | None,
    *,
    required: bool,
) -> bytes | None:
    """Return the *current* signing key for a producer service.

    Resolution order (first non-empty wins):

    1. Explicit ``signing_key`` argument (used by tests and any caller
       that wants to override env entirely).
    2. ``KAFKA_SIGNING_KEY_<SERVICE>`` per-service env var (the
       Phase-2 mechanism that makes cross-service forgery impossible).
    3. ``KAFKA_EVENT_SIGNING_KEY`` legacy shared key (Phase-1 fallback,
       removed after Phase-3 — see :data:`LEGACY_SHARED_KEY_ENV`).

    ``required=True`` raises :class:`KafkaAuthError` when nothing
    resolves. Producers always require a key (you can't sign without
    one). Consumers call with ``required=False`` because they may run
    in rollout mode without strict verification.
    """
    explicit = _coerce_key(signing_key)
    if explicit is not None:
        return explicit

    env_name = _PRODUCER_KEY_ENV_MAP.get(producer_service)
    if env_name:
        per_service = _coerce_key(os.environ.get(env_name))
        if per_service is not None:
            return per_service

    legacy = _coerce_key(os.environ.get(LEGACY_SHARED_KEY_ENV))
    if legacy is not None:
        return legacy

    if required:
        raise KafkaAuthError(
            "signing_key_not_configured",
            producer_service=producer_service,
        )
    return None


def _resolve_verification_keys(
    producer_service: str,
    signing_key: bytes | str | None,
) -> list[bytes]:
    """Return the keys to TRY when verifying an envelope, in order.

    Order:

    1. Explicit ``signing_key`` argument, if passed (single-key mode
       used by tests).
    2. ``KAFKA_SIGNING_KEY_<SERVICE>`` (current per-service key).
    3. ``KAFKA_SIGNING_KEY_<SERVICE>_PREVIOUS`` (rotation overlap).
    4. ``KAFKA_EVENT_SIGNING_KEY`` (legacy shared, Phase-1 fallback).

    ``verify_event`` HMAC-compares against each in turn and accepts
    the first match. This means an envelope signed by the previous
    per-service key, OR by the legacy shared key, still verifies
    during the rollout window — zero-downtime per-service rotation.
    """
    if signing_key is not None and signing_key != "":
        coerced = _coerce_key(signing_key)
        if coerced is not None:
            return [coerced]

    keys: list[bytes] = []

    env_name = _PRODUCER_KEY_ENV_MAP.get(producer_service)
    if env_name:
        current = _coerce_key(os.environ.get(env_name))
        if current is not None:
            keys.append(current)

    prev_env = _PRODUCER_PREVIOUS_KEY_ENV_MAP.get(producer_service)
    if prev_env:
        previous = _coerce_key(os.environ.get(prev_env))
        if previous is not None:
            keys.append(previous)

    legacy = _coerce_key(os.environ.get(LEGACY_SHARED_KEY_ENV))
    if legacy is not None:
        keys.append(legacy)

    return keys


def _any_signing_key_configured() -> bool:
    """True if the environment has ANY HMAC key configured.

    Used by :func:`verify_event` for its rollout-mode bypass: when no
    key at all is set, strict-mode raises and non-strict logs a warning
    and accepts the event. Per-service keys, ``*_PREVIOUS`` rotation
    keys, and the legacy shared key all count.
    """
    for env_name in _PRODUCER_KEY_ENV_MAP.values():
        if _coerce_key(os.environ.get(env_name)) is not None:
            return True
    for env_name in _PRODUCER_PREVIOUS_KEY_ENV_MAP.values():
        if _coerce_key(os.environ.get(env_name)) is not None:
            return True
    if _coerce_key(os.environ.get(LEGACY_SHARED_KEY_ENV)) is not None:
        return True
    return False


def _resolve_signing_key(
    signing_key: bytes | str | None,
    *,
    required: bool,
) -> bytes | None:
    """Backwards-compatible single-key resolver (legacy call sites).

    .. deprecated:: RE-SEC-004
        Producer-aware paths should use
        :func:`_resolve_producer_signing_key` /
        :func:`_resolve_verification_keys`. This helper is retained
        for paths that have no producer claim yet (e.g. the
        no-key-configured detection branch in :func:`verify_event`).
    """
    explicit = _coerce_key(signing_key)
    if explicit is not None:
        return explicit
    legacy = _coerce_key(os.environ.get(LEGACY_SHARED_KEY_ENV))
    if legacy is not None:
        return legacy
    if required:
        raise KafkaAuthError("signing_key_not_configured")
    return None


def _resolve_strict(strict: bool | None) -> bool:
    """Resolve the strict-verification flag from arg or env.

    Default is strict. The env var lets operators flip to permissive
    during a rollout window without a code change. Once all producers
    are signing, the env override should be removed.
    """
    if strict is not None:
        return strict
    raw = os.environ.get(ENV_STRICT)
    if raw is None:
        return True
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# -----------------------------------------------------------------------------
# Canonicalization + signing
# -----------------------------------------------------------------------------


def _canonicalize(payload: Mapping[str, Any]) -> bytes:
    """Canonical JSON: sorted keys, compact separators, stable floats.

    We use ``default=str`` so datetimes and UUIDs (which callers tend
    to pass through) round-trip deterministically instead of raising.
    ``ensure_ascii=False`` would be nicer for Unicode payloads but the
    default ASCII escaping is what our current producers emit, so we
    keep it to avoid canonicalization drift.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _iso_now(now_fn: Callable[[], datetime] | None) -> str:
    fn = now_fn or (lambda: datetime.now(timezone.utc))
    value = fn()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def sign_event(
    payload: Mapping[str, Any],
    producer_service: str,
    *,
    signing_key: bytes | str | None = None,
    existing_headers: Iterable[tuple[str, bytes]] | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], list[tuple[str, bytes]]]:
    """Enrich, sign, and return the message ready to publish.

    Returns ``(enriched_body_dict, kafka_headers)``. The caller should
    pass ``enriched_body_dict`` to the Kafka producer's ``value=`` and
    ``kafka_headers`` to ``headers=``.

    ``existing_headers`` is preserved in the returned list — callers
    already attaching correlation / trace headers pass them in so we
    return a single merged list.

    The producer_service name MUST match what the consumer allowlist
    expects. Typical values: ``"ingestion-service"``, ``"nlp-service"``,
    ``"scheduler-service"``.
    """
    if not isinstance(payload, Mapping):
        raise KafkaAuthError(
            "payload_not_mapping",
            type=type(payload).__name__,
        )
    if not producer_service:
        raise KafkaAuthError("producer_service_empty")

    key = _resolve_producer_signing_key(producer_service, signing_key, required=True)
    assert key is not None  # for mypy — required=True guarantees this

    enriched: dict[str, Any] = dict(payload)
    enriched[BODY_FIELD_PRODUCER_SERVICE] = producer_service
    enriched[BODY_FIELD_SIGNED_AT] = _iso_now(now_fn)

    canonical = _canonicalize(enriched)
    signature = hmac.new(key, canonical, hashlib.sha256).hexdigest()

    auth_headers: list[tuple[str, bytes]] = [
        (HEADER_SIGNATURE, signature.encode("ascii")),
        (HEADER_PRODUCER_SERVICE, producer_service.encode("utf-8")),
        (HEADER_SIG_VERSION, CURRENT_SIG_VERSION.encode("ascii")),
    ]

    # Strip any caller-supplied versions of the auth headers to avoid
    # an attacker-planted header surviving alongside ours. The consumer
    # would pick the first match; duplicates are a confusion vector.
    auth_keys = {HEADER_SIGNATURE, HEADER_PRODUCER_SERVICE, HEADER_SIG_VERSION}
    merged: list[tuple[str, bytes]] = [
        (name, value) for (name, value) in (existing_headers or []) if name not in auth_keys
    ]
    merged.extend(auth_headers)

    return enriched, merged


# -----------------------------------------------------------------------------
# Verification
# -----------------------------------------------------------------------------


def _normalize_header_value(value: Any) -> str | None:
    """Coerce a Kafka header value to str.

    Kafka clients should yield bytes
    too (or None for missing). We accept str for convenience in tests.
    """
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(value, str):
        return value
    return None


def _header_map(
    headers: Iterable[tuple[str, Any]] | None,
) -> dict[str, str]:
    """Build a case-insensitive last-wins map of headers.

    Kafka allows duplicate header names. Our signing contract is "there
    is exactly one auth header of each kind" — enforced by the
    ``sign_event`` strip step above — but we defensively coalesce
    here too.
    """
    result: dict[str, str] = {}
    if not headers:
        return result
    for name, value in headers:
        if not name:
            continue
        key = name.lower()
        decoded = _normalize_header_value(value)
        if decoded is not None:
            result[key] = decoded
    return result


def verify_event(
    payload: Any,
    headers: Iterable[tuple[str, Any]] | None,
    *,
    topic: str,
    signing_key: bytes | str | None = None,
    allowed_producers: Iterable[str] | None = None,
    strict: bool | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], str]:
    """Verify an inbound Kafka event and return ``(evt_dict, producer_service)``.

    ``payload`` may be a dict (when the consumer used a deserializer
    like ``confluent-kafka``'s ``DeserializingConsumer``) or raw
    ``bytes`` (when the consumer reads ``record.value`` as bytes and
    hasn't decoded yet). We handle both — callers don't have to
    normalize before calling.

    Raises :class:`KafkaAuthError` on any failure:

    * missing signature header
    * signing key not configured (only in strict mode)
    * signature mismatch (tamper, wrong key, unsigned message)
    * unknown signature version
    * producer_service claim missing or not in the topic allowlist
    * body mismatch between header and signed claim
    * ``_signed_at`` older than ``KAFKA_MAX_SIGNATURE_AGE_SECONDS``
      (default 900s) — replay protection (RE-SEC-003)
    * ``_signed_at`` more than 60s in the future — clock-attack guard

    On success returns the decoded dict (with ``_producer_service`` /
    ``_signed_at`` still present) and the verified producer service
    name. The verified name comes from the signed body, not the raw
    header — a raw header an attacker could replay alone wouldn't
    match the signature.

    ``strict=False`` (or ``KAFKA_SIGNATURE_STRICT=false`` in the env)
    downgrades "no signing key configured" to a WARN log and lets the
    event through. This is ONLY for rollout; do not leave strict off
    in production.
    """
    strict_mode = _resolve_strict(strict)
    header_map = _header_map(headers)

    # Pre-flight "is ANY key configured at all?" probe. We can't resolve
    # the per-service key until we've parsed the body and read the
    # producer claim, but we DO need to honor the rollout-mode bypass
    # ("no key in env => warn + accept") that callers depend on. An
    # explicit ``signing_key=`` argument or *any* env var implies a
    # configured environment.
    explicit_key = _coerce_key(signing_key)
    has_any_env_key = explicit_key is not None or _any_signing_key_configured()

    # Decode bytes -> dict up front so we always return a dict, even
    # on the rollout / no-key path.
    if isinstance(payload, (bytes, bytearray)):
        try:
            evt = json.loads(bytes(payload).decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise KafkaAuthError("body_not_json", error=str(exc)) from exc
    elif isinstance(payload, Mapping):
        evt = dict(payload)
    else:
        raise KafkaAuthError(
            "payload_not_supported_type",
            type=type(payload).__name__,
        )

    if not isinstance(evt, dict):
        # Top-level JSON arrays / primitives are never valid RegEngine
        # events, but the JSON parser accepts them. Reject explicitly.
        raise KafkaAuthError("body_not_object")

    if not has_any_env_key:
        if strict_mode:
            raise KafkaAuthError("signing_key_not_configured", topic=topic)
        logger.warning(
            "kafka_auth_bypass_no_key",
            topic=topic,
            advice=("set KAFKA_SIGNING_KEY_<SERVICE> (or legacy KAFKA_EVENT_SIGNING_KEY) to enable HMAC verification"),
        )
        producer_claim = evt.get(BODY_FIELD_PRODUCER_SERVICE) or "unsigned"
        # RE-SEC-005: even on the bypass branch, enforce the per-topic
        # allowlist if the caller provided one. Without this, a
        # non-strict consumer would accept events from any producer name
        # the body claims — defeating the layer-3 defense entirely.
        if allowed_producers is not None:
            allowed_set = {p for p in allowed_producers}
            if str(producer_claim) not in allowed_set:
                raise KafkaAuthError(
                    "producer_not_allowed_for_topic",
                    topic=topic,
                    producer_service=str(producer_claim),
                    allowed=sorted(allowed_set),
                )
        return evt, str(producer_claim)

    version = header_map.get(HEADER_SIG_VERSION)
    if version is None:
        raise KafkaAuthError("missing_sig_version_header", topic=topic)
    if version != CURRENT_SIG_VERSION:
        raise KafkaAuthError(
            "unsupported_sig_version",
            topic=topic,
            version=version,
        )

    header_sig = header_map.get(HEADER_SIGNATURE)
    if not header_sig:
        raise KafkaAuthError("missing_signature_header", topic=topic)

    header_producer = header_map.get(HEADER_PRODUCER_SERVICE)
    if not header_producer:
        raise KafkaAuthError("missing_producer_service_header", topic=topic)

    # The authoritative producer claim is the one in the SIGNED body,
    # not the header. An attacker can plant any header they like; only
    # the body field is covered by the HMAC.
    body_producer = evt.get(BODY_FIELD_PRODUCER_SERVICE)
    if not isinstance(body_producer, str) or not body_producer:
        raise KafkaAuthError(
            "missing_producer_service_in_body",
            topic=topic,
        )
    if body_producer != header_producer:
        # Header/body mismatch is suspicious — either the producer
        # misconfigured itself or something is rewriting in transit.
        # Either way, don't trust it.
        raise KafkaAuthError(
            "producer_service_header_body_mismatch",
            topic=topic,
            header=header_producer,
            body=body_producer,
        )

    # Check allowlist BEFORE the HMAC compare. The allowlist is cheap
    # and produces a better diagnostic than "signature_mismatch" when
    # the real cause is "that service isn't supposed to publish here".
    if allowed_producers is not None:
        allowed_set = {p for p in allowed_producers}
        if body_producer not in allowed_set:
            raise KafkaAuthError(
                "producer_not_allowed_for_topic",
                topic=topic,
                producer_service=body_producer,
                allowed=sorted(allowed_set),
            )

    # Resolve verification keys bound to the SIGNED producer claim. An
    # attacker who has the nlp-service key cannot satisfy this check
    # for a body claiming ``_producer_service=ingestion-service`` —
    # that's RE-SEC-004's whole point.
    candidate_keys = _resolve_verification_keys(body_producer, signing_key)
    if not candidate_keys:
        raise KafkaAuthError(
            "signing_key_not_configured",
            topic=topic,
            producer_service=body_producer,
        )

    canonical = _canonicalize(evt)
    matched = False
    for candidate in candidate_keys:
        expected_sig = hmac.new(candidate, canonical, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected_sig, header_sig):
            matched = True
            break
    if not matched:
        raise KafkaAuthError(
            "signature_mismatch",
            topic=topic,
            producer_service=body_producer,
        )

    # Replay-protection freshness check (RE-SEC-003).
    #
    # `_signed_at` was always covered by the HMAC but never read. A
    # captured envelope could be replayed indefinitely. We check it
    # only AFTER the HMAC verifies — checking before would be a
    # pre-auth DoS surface (attacker forces parse errors on garbage).
    #
    # When ``strict_mode`` is False (rollout window) we downgrade
    # stale/future to a warning log. The audit's recommendation is:
    # if signing is non-strict, freshness is also non-strict.
    signed_at_raw = evt.get(BODY_FIELD_SIGNED_AT)
    if not signed_at_raw:
        if strict_mode:
            raise KafkaAuthError(
                "missing_signed_at_in_body",
                topic=topic,
                producer_service=body_producer,
            )
        logger.warning(
            "kafka_auth_missing_signed_at",
            topic=topic,
            producer_service=body_producer,
        )
        return evt, body_producer

    try:
        signed_at = datetime.fromisoformat(str(signed_at_raw).replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        if strict_mode:
            raise KafkaAuthError(
                "invalid_signed_at_format",
                topic=topic,
                producer_service=body_producer,
                signed_at=str(signed_at_raw),
            ) from exc
        logger.warning(
            "kafka_auth_invalid_signed_at",
            topic=topic,
            producer_service=body_producer,
            signed_at=str(signed_at_raw),
            error=str(exc),
        )
        return evt, body_producer

    if signed_at.tzinfo is None:
        signed_at = signed_at.replace(tzinfo=timezone.utc)

    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    age_seconds = (now - signed_at).total_seconds()
    max_age = _max_signature_age()

    if age_seconds > max_age:
        if strict_mode:
            raise KafkaAuthError(
                "signed_at_stale",
                topic=topic,
                producer_service=body_producer,
                age_seconds=int(age_seconds),
                max_age_seconds=max_age,
            )
        logger.warning(
            "kafka_auth_stale_signature_bypass",
            topic=topic,
            producer_service=body_producer,
            age_seconds=int(age_seconds),
            max_age_seconds=max_age,
        )
    elif age_seconds < -SIGNATURE_FUTURE_SKEW_SECONDS:
        # Tolerate small clock skew, reject obvious future-dated forgeries.
        if strict_mode:
            raise KafkaAuthError(
                "signed_at_in_future",
                topic=topic,
                producer_service=body_producer,
                age_seconds=int(age_seconds),
                skew_tolerance_seconds=SIGNATURE_FUTURE_SKEW_SECONDS,
            )
        logger.warning(
            "kafka_auth_future_signature_bypass",
            topic=topic,
            producer_service=body_producer,
            age_seconds=int(age_seconds),
        )

    return evt, body_producer


# -----------------------------------------------------------------------------
# Allowlist helper
# -----------------------------------------------------------------------------


def get_allowed_producers(topic: str) -> set[str] | None:
    """Read the per-topic producer allowlist from the environment.

    Env var form::

        KAFKA_ALLOWED_PRODUCERS_INGEST_NORMALIZED=ingestion-service
        KAFKA_ALLOWED_PRODUCERS_GRAPH_UPDATE=nlp-service,scheduler-service

    Topic name is UPPER_SNAKE_CASED (dots and dashes become
    underscores). Returns ``None`` when not configured — callers should
    treat ``None`` as "no allowlist enforced" (signature is still
    verified). Returns an empty set only when the env var is set to
    an empty string, which means "reject all producers" and is useful
    for incident lockout.
    """
    env_key = "KAFKA_ALLOWED_PRODUCERS_" + topic.upper().replace(".", "_").replace("-", "_")
    raw = os.environ.get(env_key)
    if raw is None:
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}
