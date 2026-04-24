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

* **Key management is out of scope.** The signing key is read from
  ``KAFKA_EVENT_SIGNING_KEY`` (a shared secret across all services for
  this topic domain). Per-service keys with a key-id header are a
  future iteration — captured as a TODO rather than blocking the P1
  fix.

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


def _resolve_signing_key(
    signing_key: bytes | str | None,
    *,
    required: bool,
) -> bytes | None:
    """Return the signing key as bytes, reading from env if not passed.

    ``required=True`` raises :class:`KafkaAuthError` when no key is
    configured; producers always require a key (you can't sign without
    one). Consumers call with ``required=False`` because they may run
    in rollout mode without strict verification.
    """
    if signing_key is None:
        signing_key = os.environ.get(ENV_SIGNING_KEY)
    if signing_key in (None, ""):
        if required:
            raise KafkaAuthError("signing_key_not_configured")
        return None
    if isinstance(signing_key, str):
        return signing_key.encode("utf-8")
    return signing_key


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

    key = _resolve_signing_key(signing_key, required=True)
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
        (name, value)
        for (name, value) in (existing_headers or [])
        if name not in auth_keys
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
    key = _resolve_signing_key(signing_key, required=False)
    header_map = _header_map(headers)

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

    if key is None:
        if strict_mode:
            raise KafkaAuthError("signing_key_not_configured", topic=topic)
        logger.warning(
            "kafka_auth_bypass_no_key",
            topic=topic,
            advice="set KAFKA_EVENT_SIGNING_KEY to enable HMAC verification",
        )
        producer_claim = evt.get(BODY_FIELD_PRODUCER_SERVICE) or "unsigned"
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

    canonical = _canonicalize(evt)
    expected_sig = hmac.new(key, canonical, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, header_sig):
        raise KafkaAuthError(
            "signature_mismatch",
            topic=topic,
            producer_service=body_producer,
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
