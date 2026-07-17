"""Token-scope and fail-closed security tests (PRD fixtures 9, AC 6-8, 13).

The app engine connects as a non-superuser role, so FORCE RLS and the
SECURITY DEFINER lookup path are enforced for real in these tests.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text

from .conftest import requires_db, upload_fixture

pytestmark = requires_db

UNIFORM_400 = {"detail": "Remediation link is not usable"}
UNIFORM_401 = {"detail": "Session is not valid"}


def _blocked_case(client, fixture: str = "05_missing_tlc_source.csv") -> str:
    body = upload_fixture(client, fixture).json()
    blocked = next(r for r in body["records"] if r["blocking"])
    return blocked["remediation_case_id"]


def _issue_link(client, case_id: str) -> dict:
    response = client.post(
        f"/api/v1/remediation/cases/{case_id}/link",
        json={"supplier_email": "logistics@valleyfarms.example"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_raw_token_never_stored(client, admin_engine):
    case_id = _blocked_case(client)
    link = _issue_link(client, case_id)
    with admin_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT token_hash FROM fsma.remediation_tokens WHERE case_id = CAST(:c AS uuid)"),
            {"c": case_id},
        ).fetchall()
    assert rows, "token row must exist"
    for row in rows:
        assert row[0] != link["token"]
        assert len(row[0]) == 64  # sha256 hex at rest


def test_get_does_not_consume_token(client):
    case_id = _blocked_case(client)
    link = _issue_link(client, case_id)
    for _ in range(3):
        response = client.get(f"/api/v1/remediation/supplier/{link['token']}")
        assert response.status_code == 200
    # Still exchangeable after several GETs (AC-7).
    response = client.post("/api/v1/remediation/supplier/exchange", json={"token": link["token"]})
    assert response.status_code == 200


def test_token_context_is_scoped_to_case(client):
    case_id = _blocked_case(client)
    link = _issue_link(client, case_id)
    ctx = client.get(f"/api/v1/remediation/supplier/{link['token']}").json()
    assert ctx["case_id"] == case_id
    assert ctx["authorized_fields"], "supplier must see exactly the failing fields"
    paths = {f["field_path"] for f in ctx["authorized_fields"]}
    assert "kdes.tlc_source_reference" in paths
    assert "traceability_lot_code" not in paths  # not part of this failure


def test_unknown_expired_revoked_all_uniform_400(client, admin_engine):
    case_id = _blocked_case(client)
    link = _issue_link(client, case_id)

    unknown = client.get(f"/api/v1/remediation/supplier/{'A' * 43}")
    assert unknown.status_code == 400
    assert unknown.json() == UNIFORM_400

    with admin_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE fsma.remediation_tokens SET expires_at = now() - interval '1 hour' "
                "WHERE case_id = CAST(:c AS uuid)"
            ),
            {"c": case_id},
        )
    expired = client.get(f"/api/v1/remediation/supplier/{link['token']}")
    assert expired.status_code == 400
    assert expired.json() == UNIFORM_400

    link2 = _issue_link(client, case_id)  # reissue revokes nothing live but mints fresh
    client.post(f"/api/v1/remediation/cases/{case_id}/link/revoke")
    revoked = client.get(f"/api/v1/remediation/supplier/{link2['token']}")
    assert revoked.status_code == 400
    assert revoked.json() == UNIFORM_400


def test_reissue_invalidates_previous_token(client):
    case_id = _blocked_case(client)
    first = _issue_link(client, case_id)
    second = _issue_link(client, case_id)  # create_link revokes live tokens first
    old = client.get(f"/api/v1/remediation/supplier/{first['token']}")
    assert old.status_code == 400
    assert old.json() == UNIFORM_400
    fresh = client.get(f"/api/v1/remediation/supplier/{second['token']}")
    assert fresh.status_code == 200


def test_session_expiry_and_replay_rejected(client, admin_engine):
    case_id = _blocked_case(client)
    link = _issue_link(client, case_id)
    session = client.post("/api/v1/remediation/supplier/exchange", json={"token": link["token"]}).json()
    headers = {"Authorization": f"Bearer {session['session_token']}"}
    assert client.get("/api/v1/remediation/supplier/session/current", headers=headers).status_code == 200

    with admin_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE fsma.remediation_tokens SET session_expires_at = now() - interval '1 minute' "
                "WHERE case_id = CAST(:c AS uuid)"
            ),
            {"c": case_id},
        )
    replay = client.get("/api/v1/remediation/supplier/session/current", headers=headers)
    assert replay.status_code == 401
    assert replay.json() == UNIFORM_401


def test_exchange_rotates_session(client):
    case_id = _blocked_case(client)
    link = _issue_link(client, case_id)
    s1 = client.post("/api/v1/remediation/supplier/exchange", json={"token": link["token"]}).json()
    s2 = client.post("/api/v1/remediation/supplier/exchange", json={"token": link["token"]}).json()
    old_headers = {"Authorization": f"Bearer {s1['session_token']}"}
    assert client.get("/api/v1/remediation/supplier/session/current", headers=old_headers).status_code == 401
    new_headers = {"Authorization": f"Bearer {s2['session_token']}"}
    assert client.get("/api/v1/remediation/supplier/session/current", headers=new_headers).status_code == 200


def test_cross_tenant_token_fails_closed(client, admin_engine, tenant_b):
    """Fixture 9: a token forged/rebound cross-tenant must not expose tenant A data.

    We simulate the strongest variant: an attacker who somehow obtained a row
    in tenant B pointing at tenant A's case. The SECURITY DEFINER lookup
    returns tenant B, so the GUC + explicit WHERE predicates can only address
    tenant B rows — the case load 404s and no tenant A data is readable or
    writable. DB state for tenant A is asserted unchanged.
    """
    case_id = _blocked_case(client)  # tenant A case
    _issue_link(client, case_id)

    import hashlib
    import secrets

    forged_raw = secrets.token_urlsafe(32)
    forged_case = str(uuid.uuid4())
    with admin_engine.begin() as conn:
        # Forged token row lives in tenant B but references tenant A's case id.
        conn.execute(
            text(
                """
                INSERT INTO fsma.remediation_cases
                    (id, tenant_id, manifest_record_id, supplier_org, status, allowed_fields)
                SELECT CAST(:forged_case AS uuid), CAST(:tenant_b AS uuid),
                       manifest_record_id, 'attacker', 'awaiting_supplier', allowed_fields
                FROM fsma.remediation_cases WHERE id = CAST(:case_a AS uuid)
                """
            ),
            {"forged_case": forged_case, "tenant_b": tenant_b, "case_a": case_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO fsma.remediation_tokens (tenant_id, case_id, token_hash, expires_at)
                VALUES (CAST(:tenant_b AS uuid), CAST(:forged_case AS uuid), :hash, now() + interval '1 day')
                """
            ),
            {
                "tenant_b": tenant_b,
                "forged_case": forged_case,
                "hash": hashlib.sha256(forged_raw.encode()).hexdigest(),
            },
        )
        before = conn.execute(
            text("SELECT COUNT(*) FROM fsma.correction_patches WHERE tenant_id != CAST(:tb AS uuid)"),
            {"tb": tenant_b},
        ).scalar()

    # The forged token resolves inside tenant B only; the record it points at
    # belongs to tenant A, so every access fails closed.
    response = client.get(f"/api/v1/remediation/supplier/{forged_raw}")
    assert response.status_code == 404  # record unreachable across the tenant boundary

    exchange = client.post("/api/v1/remediation/supplier/exchange", json={"token": forged_raw})
    assert exchange.status_code in (400, 404)

    with admin_engine.connect() as conn:
        after = conn.execute(
            text("SELECT COUNT(*) FROM fsma.correction_patches WHERE tenant_id != CAST(:tb AS uuid)"),
            {"tb": tenant_b},
        ).scalar()
    assert after == before  # nothing written outside tenant B


def test_out_of_scope_field_rejected(client):
    case_id = _blocked_case(client)
    link = _issue_link(client, case_id)
    session = client.post("/api/v1/remediation/supplier/exchange", json={"token": link["token"]}).json()
    headers = {"Authorization": f"Bearer {session['session_token']}"}
    response = client.post(
        "/api/v1/remediation/supplier/session/corrections",
        headers=headers,
        json={
            "changes": {"traceability_lot_code": "HACKED-LOT"},
            "actor_name": "Mallory",
            "actor_role": "attacker",
            "reason": "not authorized for this field",
            "attestation": {"text": "I attest this correction is accurate.", "accepted": True},
        },
    )
    assert response.status_code == 422
    assert "not authorized" in response.json()["detail"]


def test_attestation_required(client):
    case_id = _blocked_case(client)
    link = _issue_link(client, case_id)
    session = client.post("/api/v1/remediation/supplier/exchange", json={"token": link["token"]}).json()
    headers = {"Authorization": f"Bearer {session['session_token']}"}
    response = client.post(
        "/api/v1/remediation/supplier/session/corrections",
        headers=headers,
        json={
            "changes": {"kdes.tlc_source_reference": "Valley Farms Packinghouse"},
            "actor_name": "Jordan Lee",
            "actor_role": "Logistics Coordinator",
            "reason": "TLC source omitted from export",
            "attestation": {"text": "I attest this correction is accurate.", "accepted": False},
        },
    )
    assert response.status_code == 422


def test_rate_limit_trips(client):
    bogus = "B" * 43
    last = None
    for _ in range(12):
        last = client.get(f"/api/v1/remediation/supplier/{bogus}")
    assert last.status_code == 429
