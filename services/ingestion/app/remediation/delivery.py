"""Notification-outbox drainer — delivers remediation emails via Resend.

Closes the delivery gap left by v095: ``outbox.enqueue_preview`` wrote rows
that nothing ever sent, so remediation links had to be copied out of the
``create_link`` API response and delivered by hand.

Hash-at-rest constraint drives the design. The outbox row stores only a
masked link + the token row id (the raw token exists exactly once, in the
``create_link`` response), so the drainer cannot send the stored payload.
Instead, at send time it:

  1. Verifies the referenced token is still the live one for its case —
     revoked, superseded, expired, or already-exchanged tokens are
     terminally skipped with the reason recorded. Expiry recovery stays a
     buyer action (reissue), exactly as documented in ``tokens.py``.
  2. Follows the buyer reissue path verbatim (``revoke_tokens_for_case`` +
     ``issue_token`` with ``superseded_token_id``), preserving the original
     token's absolute expiry so the enqueued body text ("Link expires …")
     stays truthful. The fresh raw token lives only in process memory and
     the outgoing email; the row's ``payload.token_id`` is repointed at the
     fresh token so a retry re-validates against the live token.

Idempotency per entry: a row is atomically claimed (``status='sending'`` +
``claimed_at``) before the provider call, so a concurrent drainer cannot
double-send. A crash mid-send strands the row in 'sending'; it is reclaimed
as a retry after ``STALE_CLAIM_MINUTES`` — each retry supersedes the
previously minted token, so a duplicate email never carries a live older
link. Transient send failures reschedule with backoff ('queued'); after
``MAX_ATTEMPTS`` the row flips to 'failed'.

Only rows enqueued as 'queued' (post-v101 with a recipient) are delivered.
Legacy 'pending' rows predate delivery and were handled manually — draining
them would revoke links buyers already shared. Rows without a recipient
stay pure previews ('pending').

Scheduling: ``drain_all_tenants`` runs from the scheduler leader (see
``SchedulerService.drain_remediation_notifications``). The outbox is FORCE
RLS with no sysadmin bypass, so tenant discovery iterates ``public.tenants``
and every claim runs under that tenant's GUC — same pattern as the
deadline monitor (#2461).
"""

from __future__ import annotations

import html as html_lib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from shared.env import is_production
from shared.pii import mask_email
from shared.tenant_context import set_tenant_guc, tenant_scope
from sqlalchemy import text

from . import tokens
from .audit_utils import audit_event

logger = logging.getLogger("remediation.delivery")

#: Retries per entry before the row is marked 'failed'.
MAX_ATTEMPTS = 8

#: Backoff (seconds) indexed by attempt count, same shape as webhook_outbox.
_BACKOFF = (30.0, 120.0, 600.0, 1800.0, 3600.0, 14400.0, 43200.0, 86400.0)

#: A 'sending' row older than this is treated as stranded by a crash and
#: reclaimed as a retry.
STALE_CLAIM_MINUTES = 15

#: Same URL shape as create_link: the token rides in the URL FRAGMENT so it
#: can never land in server access logs.
CORRECTION_URL_BASE = "https://regengine.co/api/v1/remediation/supplier/form"

#: (recipient, subject, html_body) -> provider message id (None when the
#: dev fallback logged instead of sending). Raises on failure.
EmailSender = Callable[[str, str, str], Optional[str]]


def correction_url(raw_token: str) -> str:
    return f"{CORRECTION_URL_BASE}#{raw_token}"


def default_email_sender(recipient: str, subject: str, html_body: str) -> Optional[str]:
    """Send via Resend, mirroring the passwordless-login sender.

    Missing key: dev logs-and-succeeds (parity with the login-code and
    invite senders); production raises so the row stays queued and the
    backlog is visible instead of silently marked sent.
    """
    resend_api_key = os.getenv("RESEND_API_KEY")
    if not resend_api_key:
        if is_production():
            raise RuntimeError("RESEND_API_KEY not configured")
        logger.warning("remediation_email_dev recipient=%s subject=%s", mask_email(recipient), subject)
        return None

    import resend

    resend.api_key = resend_api_key
    from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@regengine.co")
    response = resend.Emails.send(
        {
            "from": from_email,
            "to": recipient,
            "subject": subject,
            "html": html_body,
        }
    )
    return getattr(response, "id", None) or (response.get("id") if isinstance(response, dict) else None)


def _render_html(body: str, link: Optional[str]) -> str:
    """Invite-email styling: body text, then a button + copyable URL."""
    safe_body = html_lib.escape(body, quote=True)
    parts = [
        "<div style='font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;'>",
        f"<p style='color: #374151; line-height: 1.6;'>{safe_body}</p>",
    ]
    if link:
        safe_link = html_lib.escape(link, quote=True)
        parts.append(
            "<p style='margin: 24px 0;'>"
            f"<a href='{safe_link}' "
            "style='background: #10b981; color: #ffffff; text-decoration: none; "
            "padding: 12px 20px; border-radius: 8px; display: inline-block; font-weight: 600;'>"
            "Open secure correction link"
            "</a>"
            "</p>"
            "<p style='color: #6b7280; font-size: 13px;'>"
            "If the button does not work, copy and paste this URL into your browser:<br/>"
            f"{safe_link}"
            "</p>"
        )
    parts.append("</div>")
    return "".join(parts)


def _record_e2e_delivery(recipient: str, subject: str, link: Optional[str]) -> None:
    """Dev/e2e parity with the enqueue-side recorder in outbox.py."""
    outbox_path = os.environ.get("REGENGINE_E2E_EMAIL_OUTBOX")
    if not outbox_path:
        return
    try:
        with open(outbox_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"kind": "delivered", "recipient": recipient, "subject": subject, "link": link}) + "\n")
    except OSError as exc:  # pragma: no cover
        logger.warning("e2e_delivery_write_failed error=%s", exc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class NotificationOutboxDrainer:
    """Claim-and-drain worker for ``fsma.notification_outbox``.

    Single-threaded row-at-a-time like WebhookOutboxDrainer — one bad row
    cannot poison the batch; each row commits its own status transition.
    All queries carry explicit tenant predicates on top of RLS.
    """

    def __init__(self, session, *, email_sender: Optional[EmailSender] = None):
        self._session = session
        self._send = email_sender or default_email_sender

    def drain_tenant_once(self, tenant_id: str, batch_size: int = 50) -> Dict[str, int]:
        """Drain one tenant's due rows. Caller must have set the tenant GUC."""
        summary = {"claimed": 0, "sent": 0, "skipped": 0, "failed": 0, "rescheduled": 0}
        for row in self._due_rows(tenant_id, batch_size):
            if not self._claim(tenant_id, row["id"]):
                continue  # another drainer won the row
            summary["claimed"] += 1
            outcome = self._drain_one(tenant_id, row)
            summary[outcome] += 1
        return summary

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _due_rows(self, tenant_id: str, batch_size: int) -> List[Dict[str, Any]]:
        rows = self._session.execute(
            # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
            text(
                """
                SELECT id, case_id, recipient, subject, body, payload, attempts
                FROM fsma.notification_outbox
                WHERE tenant_id = CAST(:tenant_id AS uuid)
                  AND (
                        (status = 'queued' AND next_attempt_at <= now())
                     OR (status = 'sending'
                         AND claimed_at <= now() - make_interval(mins => :stale_minutes))
                  )
                ORDER BY created_at ASC
                LIMIT :limit
                """
            ),
            {"tenant_id": tenant_id, "stale_minutes": STALE_CLAIM_MINUTES, "limit": batch_size},
        ).fetchall()
        return [
            {
                "id": str(r[0]),
                "case_id": str(r[1]) if r[1] else None,
                "recipient": r[2],
                "subject": r[3],
                "body": r[4],
                "payload": r[5] or {},
                "attempts": r[6] or 0,
            }
            for r in rows
        ]

    def _claim(self, tenant_id: str, outbox_id: str) -> bool:
        """Atomic claim — the commit makes a double-send impossible even if
        a second drainer instance is running the same tenant."""
        result = self._session.execute(
            # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
            text(
                """
                UPDATE fsma.notification_outbox
                SET status = 'sending', claimed_at = now()
                WHERE id = CAST(:id AS uuid)
                  AND tenant_id = CAST(:tenant_id AS uuid)
                  AND (
                        (status = 'queued' AND next_attempt_at <= now())
                     OR (status = 'sending'
                         AND claimed_at <= now() - make_interval(mins => :stale_minutes))
                  )
                """
            ),
            {"id": outbox_id, "tenant_id": tenant_id, "stale_minutes": STALE_CLAIM_MINUTES},
        )
        self._session.commit()
        return result.rowcount == 1

    def _drain_one(self, tenant_id: str, row: Dict[str, Any]) -> str:
        if not row["recipient"]:
            # enqueue_preview keeps recipient-less rows out of the queue;
            # this guards rows queued by any other path.
            return self._finish_skipped(tenant_id, row, reason="no_recipient")

        token_id = (row["payload"] or {}).get("token_id")
        link: Optional[str] = None
        if token_id:
            token_row = self._load_token(tenant_id, token_id)
            skip_reason = self._token_skip_reason(token_row)
            if skip_reason:
                return self._finish_skipped(tenant_id, row, reason=skip_reason)
            try:
                link = self._remint_link(tenant_id, row, token_row)
            except Exception as exc:  # noqa: BLE001 — classified as transient below
                self._session.rollback()
                return self._on_send_failure(tenant_id, row, f"remint failed: {exc}")

        try:
            provider_id = self._send(row["recipient"], row["subject"], _render_html(row["body"], link))
        except Exception as exc:  # noqa: BLE001 — provider/network failures reschedule
            return self._on_send_failure(tenant_id, row, str(exc))

        _record_e2e_delivery(row["recipient"], row["subject"], link)
        return self._finish_sent(tenant_id, row, provider_id=provider_id, with_link=link is not None)

    def _load_token(self, tenant_id: str, token_id: str) -> Optional[Dict[str, Any]]:
        r = self._session.execute(
            # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
            text(
                """
                SELECT id, case_id, expires_at, revoked_at, superseded_by, exchange_count
                FROM fsma.remediation_tokens
                WHERE id = CAST(:token_id AS uuid)
                  AND tenant_id = CAST(:tenant_id AS uuid)
                """
            ),
            {"token_id": token_id, "tenant_id": tenant_id},
        ).fetchone()
        if not r:
            return None
        return {
            "id": str(r[0]),
            "case_id": str(r[1]),
            "expires_at": r[2],
            "revoked_at": r[3],
            "superseded_by": str(r[4]) if r[4] else None,
            "exchange_count": r[5] or 0,
        }

    @staticmethod
    def _token_skip_reason(token_row: Optional[Dict[str, Any]]) -> Optional[str]:
        """TTL + revoke/reissue semantics from tokens.py, enforced at send.

        superseded is checked before revoked: reissue sets both, and the
        newer token's own outbox row is the one that delivers.
        """
        if token_row is None:
            return "token_missing"
        if token_row["superseded_by"]:
            return "token_superseded"
        if token_row["revoked_at"] is not None:
            return "token_revoked"
        if token_row["expires_at"] <= _now():
            return "token_expired"
        if token_row["exchange_count"] >= tokens.MAX_EXCHANGES:
            return "token_already_exchanged"
        return None

    def _remint_link(self, tenant_id: str, row: Dict[str, Any], token_row: Dict[str, Any]) -> str:
        """Reissue path from create_link, preserving the original absolute
        expiry so the enqueued body's "Link expires …" stays accurate."""
        remaining_hours = (token_row["expires_at"] - _now()).total_seconds() / 3600.0
        tokens.revoke_tokens_for_case(
            self._session,
            tenant_id=tenant_id,
            case_id=token_row["case_id"],
            actor="remediation-delivery",
        )
        minted = tokens.issue_token(
            self._session,
            tenant_id=tenant_id,
            case_id=token_row["case_id"],
            supplier_email=row["recipient"],
            created_by="remediation-delivery",
            expires_hours=remaining_hours,
            superseded_token_id=token_row["id"],
        )
        # Repoint the row at the live token BEFORE the provider call: if the
        # send fails, the retry must validate the minted token, not the
        # now-superseded original. Only the id is stored — never the raw.
        self._session.execute(
            # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
            text(
                """
                UPDATE fsma.notification_outbox
                SET payload = payload || jsonb_build_object('token_id', CAST(:token_id AS text))
                WHERE id = CAST(:id AS uuid)
                  AND tenant_id = CAST(:tenant_id AS uuid)
                """
            ),
            {"token_id": minted["token_id"], "id": row["id"], "tenant_id": tenant_id},
        )
        self._session.commit()
        return correction_url(minted["token"])

    # ------------------------------------------------------------------
    # Outcomes — each commits its own transition
    # ------------------------------------------------------------------

    def _finish_sent(self, tenant_id: str, row: Dict[str, Any], *, provider_id: Optional[str], with_link: bool) -> str:
        self._session.execute(
            # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
            text(
                """
                UPDATE fsma.notification_outbox
                SET status = 'sent', sent_at = now(),
                    provider_message_id = :provider_id, last_error = NULL
                WHERE id = CAST(:id AS uuid)
                  AND tenant_id = CAST(:tenant_id AS uuid)
                """
            ),
            {"provider_id": provider_id, "id": row["id"], "tenant_id": tenant_id},
        )
        audit_event(
            self._session,
            tenant_id=tenant_id,
            event_type="remediation.notification.sent",
            action="remediation.notification.send",
            actor_id="remediation-delivery",
            resource_type="notification_outbox",
            resource_id=row["id"],
            metadata={
                "case_id": row["case_id"],
                "with_link": with_link,
                **({"provider_message_id": provider_id} if provider_id else {}),
            },
        )
        self._session.commit()
        logger.info(
            "remediation_notification_sent outbox_id=%s recipient=%s with_link=%s",
            row["id"],
            mask_email(row["recipient"]),
            with_link,
        )
        return "sent"

    def _finish_skipped(self, tenant_id: str, row: Dict[str, Any], *, reason: str) -> str:
        self._session.execute(
            # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
            text(
                """
                UPDATE fsma.notification_outbox
                SET status = 'skipped', last_error = :reason
                WHERE id = CAST(:id AS uuid)
                  AND tenant_id = CAST(:tenant_id AS uuid)
                """
            ),
            {"reason": reason, "id": row["id"], "tenant_id": tenant_id},
        )
        self._session.commit()
        logger.info("remediation_notification_skipped outbox_id=%s reason=%s", row["id"], reason)
        return "skipped"

    def _on_send_failure(self, tenant_id: str, row: Dict[str, Any], reason: str) -> str:
        attempts = row["attempts"] + 1
        if attempts >= MAX_ATTEMPTS:
            self._session.execute(
                # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
                text(
                    """
                    UPDATE fsma.notification_outbox
                    SET status = 'failed', attempts = :attempts, last_error = :reason
                    WHERE id = CAST(:id AS uuid)
                      AND tenant_id = CAST(:tenant_id AS uuid)
                    """
                ),
                {"attempts": attempts, "reason": reason[:4000], "id": row["id"], "tenant_id": tenant_id},
            )
            self._session.commit()
            logger.warning(
                "remediation_notification_failed outbox_id=%s attempts=%s reason=%s", row["id"], attempts, reason[:200]
            )
            return "failed"

        delay = _BACKOFF[min(attempts - 1, len(_BACKOFF) - 1)]
        self._session.execute(
            # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
            text(
                """
                UPDATE fsma.notification_outbox
                SET status = 'queued', attempts = :attempts, last_error = :reason,
                    next_attempt_at = now() + make_interval(secs => :delay)
                WHERE id = CAST(:id AS uuid)
                  AND tenant_id = CAST(:tenant_id AS uuid)
                """
            ),
            {"attempts": attempts, "reason": reason[:4000], "delay": delay, "id": row["id"], "tenant_id": tenant_id},
        )
        self._session.commit()
        logger.info(
            "remediation_notification_rescheduled outbox_id=%s attempts=%s delay=%s", row["id"], attempts, delay
        )
        return "rescheduled"


def drain_all_tenants(session, *, email_sender: Optional[EmailSender] = None, batch_size: int = 50) -> Dict[str, int]:
    """Tenant-iterating entry point for the scheduler job.

    Tenant UUID discovery uses the audited admin credential; the RLS-forced
    outbox is then drained through the ordinary role one tenant at a time.
    """
    from shared.maintenance_tenants import list_maintenance_tenant_ids

    tenant_ids = list_maintenance_tenant_ids()
    drainer = NotificationOutboxDrainer(session, email_sender=email_sender)
    totals = {"claimed": 0, "sent": 0, "skipped": 0, "failed": 0, "rescheduled": 0}
    for tid in tenant_ids:
        try:
            with tenant_scope(tid):
                set_tenant_guc(session, tid)
                summary = drainer.drain_tenant_once(tid, batch_size=batch_size)
        except Exception:  # noqa: BLE001 — one tenant must not poison the tick
            session.rollback()
            logger.exception("remediation_outbox_drain_tenant_failed tenant_id=%s", tid)
            continue
        for key, value in summary.items():
            totals[key] += value
    return totals
