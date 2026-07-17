"""Supplier-facing token-scoped endpoints (no account, no principal).

Tenant binding: the token row IS the authenticated context — tenant_id is
read only from that server-side row (SECURITY DEFINER lookup), the RLS GUC
is set from it, and every query still carries explicit tenant/case
predicates. Request bodies define no tenant field at all.

Anti-enumeration: every token failure returns the same 400 body and every
session failure the same 401 body; the real deny reason goes to the audit
log only. Raw tokens appear once in the emailed link — in the URL
FRAGMENT, which browsers never send to the server — and only hashes are
stored. The context preview never consumes the token (acceptance #7);
the explicit exchange mints the single-use 30-minute session.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from shared.database import get_db_session
from shared.tenant_rate_limiting import consume_tenant_rate_limit as _consume_rate_limit

from . import corrections, outbox, service, tokens
from .audit_utils import audit_event
from .schemas import MAX_FIELD_VALUE_CHARS, CorrectionRequest, ExchangeRequest
from .state import transition

logger = logging.getLogger("remediation.supplier")

router = APIRouter(prefix="/api/v1/remediation/supplier", tags=["Supplier Remediation (token)"])

_get_db_session = get_db_session  # test-override alias

_RATE_WINDOW_SECONDS = 60


def _rate_limit(request: Request, bucket: str, limit: int) -> None:
    """Shared (Redis-backed when configured) sliding-window rate limit.

    Behind the Railway proxy request.client.host is the proxy peer — a
    single global bucket that one abuser could exhaust for everyone.
    First X-Forwarded-For hop is spoofable but strictly better here.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    allowed, _remaining = _consume_rate_limit(
        tenant_id=f"remsup:{client_ip}",
        bucket_suffix=f"remediation.{bucket}",
        limit=limit,
        window=_RATE_WINDOW_SECONDS,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many requests")


def _db(db_session):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return db_session


def _case_context(db, token_row: Dict[str, Any]) -> Dict[str, Any]:
    from .router import _load_case  # same package; avoids duplicating the loader

    case = _load_case(db, token_row["tenant_id"], token_row["case_id"])
    record = service.load_record(db, tenant_id=token_row["tenant_id"], record_id=case["manifest_record_id"])
    current_values = {
        f["field_path"]: corrections.get_value(record["normalized_payload"] or {}, f["field_path"])
        for f in case["allowed_fields"]
    }
    return {
        "case_id": case["id"],
        "status": case["status"],
        "supplier": case["supplier_org"],
        "manifest": case["manifest_ref"],
        "line": case["line_ref"],
        "due_at": case["due_at"],
        "authorized_fields": case["allowed_fields"],
        "current_values": current_values,
        "failures": record["rule_failures"],
        "_case": case,
        "_record": record,
    }


@router.post("/context", summary="View the correction request (does not consume the link)")
async def get_token_context(body: ExchangeRequest, request: Request, db_session=Depends(get_db_session)):
    """Non-consuming preview. The token travels in the request BODY —
    never in a URL path or query string, so it cannot land in access logs."""
    _rate_limit(request, "preview", 10)
    db = _db(db_session)
    token_row = tokens.resolve_active_token(db, body.token)
    ctx = _case_context(db, token_row)
    return {k: v for k, v in ctx.items() if not k.startswith("_")}


@router.get("/form", response_class=HTMLResponse, summary="Supplier correction form (token read from URL fragment)")
async def correction_form() -> HTMLResponse:
    """Static, self-contained form page. The correction link puts the raw
    token in the URL FRAGMENT (…/form#<token>): fragments are never sent
    to the server, so the token cannot appear in gunicorn/proxy logs. The
    page's JS reads location.hash and talks to the JSON endpoints."""
    return HTMLResponse(content=_FORM_HTML)


@router.post("/exchange", summary="Exchange the link token for a 30-minute correction session")
async def exchange(body: ExchangeRequest, request: Request, db_session=Depends(get_db_session)):
    _rate_limit(request, "exchange", 5)
    db = _db(db_session)
    token_row = tokens.resolve_active_token(db, body.token)
    session = tokens.exchange_for_session(db, token_row)
    ctx = _case_context(db, token_row)
    return {
        "session_token": session["session_token"],
        "session_expires_at": session["expires_at"].isoformat(),
        "case": {k: v for k, v in ctx.items() if not k.startswith("_")},
    }


def _session_row(db, authorization: str) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise tokens.SESSION_NOT_VALID
    return tokens.resolve_active_session(db, authorization[7:].strip())


@router.get("/session/current", summary="Current record state for an active session")
async def get_session_state(
    request: Request,
    authorization: str = Header(default=""),
    db_session=Depends(get_db_session),
):
    _rate_limit(request, "session", 30)
    db = _db(db_session)
    token_row = _session_row(db, authorization)
    ctx = _case_context(db, token_row)
    return {k: v for k, v in ctx.items() if not k.startswith("_")}


@router.post("/session/corrections", summary="Submit a correction (attested, append-only)")
async def submit_correction(
    body: CorrectionRequest,
    request: Request,
    authorization: str = Header(default=""),
    db_session=Depends(get_db_session),
):
    _rate_limit(request, "correction", 10)
    db = _db(db_session)
    token_row = _session_row(db, authorization)
    ctx = _case_context(db, token_row)
    case, record = ctx["_case"], ctx["_record"]
    tenant_id = token_row["tenant_id"]

    if case["status"] != "awaiting_supplier":
        raise HTTPException(status_code=409, detail=f"Case is not awaiting a correction (status: {case['status']})")
    if not body.attestation.accepted:
        raise HTTPException(status_code=422, detail="The accuracy attestation must be accepted")

    allowed_paths = [f["field_path"] for f in case["allowed_fields"]]
    issue_by_field = {f["field_path"]: f.get("issue_id") for f in case["allowed_fields"]}
    for field_path, value in body.changes.items():
        corrections.validate_field_path(field_path, allowed_paths)
        if len(str(value)) > MAX_FIELD_VALUE_CHARS:
            raise HTTPException(
                status_code=422, detail=f"Value for '{field_path}' exceeds {MAX_FIELD_VALUE_CHARS} characters"
            )

    original_event = record["normalized_payload"] or {}
    previous_values = {p: corrections.get_value(original_event, p) for p in body.changes}

    patch_ids = corrections.insert_patches(
        db,
        tenant_id=tenant_id,
        case_id=case["id"],
        manifest_record_id=record["id"],
        changes=dict(body.changes),
        previous_values=previous_values,
        issue_by_field=issue_by_field,
        correcting_org=body.correcting_org or case["supplier_org"],
        actor_name=body.actor_name,
        actor_role=body.actor_role,
        correction_reason=body.reason,
        attestation_text=body.attestation.text,
        evidence_ref=body.evidence_ref,
    )

    # Apply patches to the staged record (original raw_row is never touched).
    updated = original_event
    for field_path, value in body.changes.items():
        updated = corrections.set_value(updated, field_path, value)
    record["normalized_payload"] = updated

    provenance = record["field_provenance"] or {}
    for i, field_path in enumerate(sorted(body.changes.keys())):
        provenance[field_path] = {
            "source": "supplier_correction",
            "patch_id": patch_ids[i] if i < len(patch_ids) else None,
            "value": body.changes[field_path],
        }
    _store_provenance(db, tenant_id, record["id"], provenance)

    audit_event(
        db,
        tenant_id=tenant_id,
        event_type="remediation.correction.submit",
        action="remediation.correction.submit",
        resource_type="remediation_case",
        resource_id=case["id"],
        metadata={
            "patch_ids": patch_ids,
            "field_paths": sorted(body.changes.keys()),
            "actor_name": body.actor_name,
            "actor_role": body.actor_role,
            "auth_method": "remediation_token",
        },
    )

    transition(
        db,
        tenant_id=tenant_id,
        case_id=case["id"],
        to_status="correction_submitted",
        expected_from="awaiting_supplier",
        actor=body.actor_name,
    )
    transition(
        db,
        tenant_id=tenant_id,
        case_id=case["id"],
        to_status="revalidating",
        expected_from="correction_submitted",
        actor="system",
    )

    result = service.revalidate_record(db, tenant_id=tenant_id, record=record)

    if not result["blocking"]:
        meta = service.get_run_meta(db, tenant_id=tenant_id, run_id=record["ingestion_run_id"])
        event_id = service.release_record(db, tenant_id=tenant_id, record=record, source_meta=meta)
        transition(
            db,
            tenant_id=tenant_id,
            case_id=case["id"],
            to_status="released",
            expected_from="revalidating",
            actor="system",
        )
        _resolve_exception(db, tenant_id, case, event_id)
        _notify_buyer(db, tenant_id, case, released_event_id=event_id, still_blocked=False)
        return {
            "status": "released",
            "released_event_id": event_id,
            "patch_ids": patch_ids,
            "message": "Correction accepted. The record passed revalidation and has been released.",
        }

    transition(
        db,
        tenant_id=tenant_id,
        case_id=case["id"],
        to_status="buyer_review",
        expected_from="revalidating",
        actor="system",
    )
    _notify_buyer(db, tenant_id, case, released_event_id=None, still_blocked=True)
    return {
        "status": "still_blocked",
        "patch_ids": patch_ids,
        "failures": result["failures"],
        "message": "Correction recorded, but the record still fails validation. The buyer has been notified for review.",
    }


def _store_provenance(db, tenant_id: str, record_id: str, provenance: Dict[str, Any]) -> None:
    import json

    from sqlalchemy import text

    db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            UPDATE fsma.manifest_records
            SET field_provenance = CAST(:provenance AS jsonb), updated_at = now()
            WHERE id = CAST(:record_id AS uuid)
              AND tenant_id = CAST(:tenant_id AS uuid)
            """
        ),
        {"provenance": json.dumps(provenance), "record_id": record_id, "tenant_id": tenant_id},
    )


def _resolve_exception(db, tenant_id: str, case: Dict[str, Any], event_id: str) -> None:
    if not case.get("exception_case_id"):
        return
    try:
        from shared.exception_queue import ExceptionQueueService

        with db.begin_nested():
            ExceptionQueueService(db).resolve_exception(
                tenant_id=tenant_id,
                case_id=case["exception_case_id"],
                resolution_summary=f"Supplier correction accepted; record released as event {event_id}.",
                resolved_by=f"supplier-remediation:{case['id']}",
            )
    except Exception as exc:  # pragma: no cover — mirror is best-effort
        logger.warning("exception_resolve_failed case=%s error=%s", case["id"], exc)


def _notify_buyer(db, tenant_id: str, case: Dict[str, Any], *, released_event_id, still_blocked: bool) -> None:
    subject = (
        f"Supplier correction released: {case['manifest_ref']} ({case['line_ref']})"
        if not still_blocked
        else f"Supplier correction needs review: {case['manifest_ref']} ({case['line_ref']})"
    )
    body_text = (
        f"The supplier corrected {case['line_ref']} and the record passed revalidation (event {released_event_id})."
        if not still_blocked
        else f"The supplier submitted a correction for {case['line_ref']} but the record still fails validation."
    )
    outbox.enqueue_preview(
        db,
        tenant_id=tenant_id,
        case_id=case["id"],
        recipient=None,
        subject=subject,
        body=body_text,
        payload={"case_id": case["id"], "released_event_id": released_event_id},
    )


_FORM_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Correction request</title>
<style>
  body { font-family: -apple-system, system-ui, sans-serif; max-width: 42rem;
         margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
  h1 { font-size: 1.25rem; } h2 { font-size: 1rem; margin-top: 1.5rem; }
  .card { border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
  .fail { background: #fff5f5; border-color: #e0b4b4; }
  .ok { background: #f0fff4; border-color: #a3d9a5; }
  label { display: block; font-weight: 600; margin-top: .75rem; font-size: .9rem; }
  .why { font-weight: 400; color: #86181d; font-size: .85rem; }
  input[type=text] { width: 100%; padding: .45rem; margin-top: .25rem;
         border: 1px solid #bbb; border-radius: 6px; box-sizing: border-box; }
  button { margin-top: 1rem; padding: .55rem 1.1rem; border: 0; border-radius: 6px;
         background: #1f6feb; color: #fff; font-size: .95rem; cursor: pointer; }
  button:disabled { background: #9bb9e8; }
  .muted { color: #666; font-size: .85rem; }
  .attest { margin-top: 1rem; font-size: .9rem; }
</style>
</head>
<body>
<h1>Shipment record correction</h1>
<div id="status" class="muted">Loading…</div>
<div id="app" hidden>
  <div class="card" id="caseinfo"></div>
  <div class="card fail"><h2>What needs fixing</h2><div id="failures"></div></div>
  <div id="startwrap">
    <button id="start">Start correction (opens a 30-minute session)</button>
    <p class="muted">This link works once. If your session expires before you
    submit, ask your buyer contact to send a new link.</p>
  </div>
  <form id="form" hidden>
    <h2>Your correction</h2>
    <div id="fields"></div>
    <label>Your name<input type="text" id="actor_name" required></label>
    <label>Your role<input type="text" id="actor_role" required></label>
    <label>Reason for the correction<input type="text" id="reason" required minlength="3"></label>
    <div class="attest">
      <label><input type="checkbox" id="attest">
        I attest that the corrected information is accurate to the best of my knowledge.</label>
    </div>
    <button type="submit">Submit correction</button>
  </form>
  <div id="result" class="card ok" hidden></div>
</div>
<script>
(function () {
  var token = location.hash.slice(1);
  var api = "/api/v1/remediation/supplier";
  var statusEl = document.getElementById("status");
  var session = null, ctx = null;
  function esc(s) { var d = document.createElement("div"); d.textContent = String(s == null ? "" : s); return d.innerHTML; }
  function post(path, body, bearer) {
    return fetch(api + path, {
      method: "POST",
      headers: Object.assign({"Content-Type": "application/json"},
        bearer ? {Authorization: "Bearer " + bearer} : {}),
      body: JSON.stringify(body)
    }).then(function (r) { return r.json().then(function (j) { return {ok: r.ok, body: j}; }); });
  }
  if (!token) { statusEl.textContent = "This link is missing its access code."; return; }
  post("/context", {token: token}).then(function (r) {
    if (!r.ok) { statusEl.textContent = r.body.detail || "This link is not usable."; return; }
    ctx = r.body;
    statusEl.hidden = true;
    document.getElementById("app").hidden = false;
    document.getElementById("caseinfo").innerHTML =
      "<h2>" + esc(ctx.manifest) + " — " + esc(ctx.line) + "</h2>" +
      "<p class='muted'>Supplier: " + esc(ctx.supplier) +
      (ctx.due_at ? " · Respond by " + esc(ctx.due_at) : "") + "</p>";
    document.getElementById("failures").innerHTML = (ctx.failures || [])
      .map(function (f) { return "<p>• " + esc(f.why_failed) + "</p>"; }).join("");
    var fields = document.getElementById("fields");
    (ctx.authorized_fields || []).forEach(function (f) {
      var cur = ctx.current_values && ctx.current_values[f.field_path];
      fields.insertAdjacentHTML("beforeend",
        "<label>" + esc(f.field_path) +
        "<span class='why'> — " + esc(f.reason) + "</span>" +
        "<input type='text' data-path='" + esc(f.field_path) + "' value='" +
        esc(cur == null ? "" : cur) + "'></label>");
    });
  });
  document.getElementById("start").onclick = function () {
    post("/exchange", {token: token}).then(function (r) {
      if (!r.ok) { alert(r.body.detail || "Could not start a session."); return; }
      session = r.body.session_token;
      document.getElementById("startwrap").hidden = true;
      document.getElementById("form").hidden = false;
    });
  };
  document.getElementById("form").onsubmit = function (e) {
    e.preventDefault();
    if (!document.getElementById("attest").checked) { alert("Please confirm the attestation."); return; }
    var changes = {};
    document.querySelectorAll("#fields input").forEach(function (i) { changes[i.dataset.path] = i.value; });
    post("/session/corrections", {
      changes: changes,
      actor_name: document.getElementById("actor_name").value,
      actor_role: document.getElementById("actor_role").value,
      reason: document.getElementById("reason").value,
      attestation: {text: "I attest that the corrected information is accurate to the best of my knowledge.", accepted: true}
    }, session).then(function (r) {
      var out = document.getElementById("result");
      out.hidden = false;
      if (r.ok && r.body.status === "released") {
        out.innerHTML = "<h2>Correction accepted</h2><p>" + esc(r.body.message) + "</p>";
        document.getElementById("form").hidden = true;
      } else {
        out.className = "card fail";
        out.innerHTML = "<h2>Still blocked</h2><p>" + esc(r.body.message || r.body.detail) + "</p>" +
          ((r.body.failures || []).map(function (f) { return "<p>• " + esc(f.why_failed) + "</p>"; }).join(""));
      }
    });
  };
})();
</script>
</body>
</html>"""
