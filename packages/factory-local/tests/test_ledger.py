import base64
import stat
from datetime import datetime, timedelta, timezone

import pytest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ledger import GENESIS, build_receipt, canonical_hash, leaf_hash_of, load_or_create_signing_key, verify_rows


def test_rfc8785_canonical_form_and_hash():
    assert rfc8785.dumps({"b": 1, "a": [1.0, "é", True, None]}) == '{"a":[1,"é",true,null],"b":1}'.encode()
    assert canonical_hash({"b": 1, "a": 2}) == canonical_hash({"a": 2, "b": 1})
    assert canonical_hash({"a": 1.0}) == canonical_hash({"a": 1})
    assert canonical_hash({"a": 1}) == "015abd7f5cc57a2dd94b7590f04ad8084273905ee33ec5cebeae62276a97f862"  # pragma: allowlist secret


@pytest.fixture
def key():
    return Ed25519PrivateKey.generate()


def chain(key, n=3, tenant="t1"):
    rows, prev = [], GENESIS
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        r = build_receipt(previous_leaf_hash=prev, tenant_id=tenant, rule_uid="R", version_uid="V",
                          input_payload={"i": i}, evaluated_decision="COMPLIANT", citation_uri="urn:x",
                          private_key=key, evaluated_at=t0 + timedelta(seconds=i))
        r["seq"] = i + 1
        rows.append(r)
        prev = r["leaf_hash"]
    return rows


def test_chain_verifies(key):
    rows = chain(key)
    assert rows[0]["previous_leaf_hash"] == GENESIS
    assert verify_rows(rows, key.public_key()) == {"ok": True, "count": 3, "first_bad": None}
    assert verify_rows([], key.public_key())["ok"] is True


def test_timestamp_timezone_does_not_change_leaf(key):
    row = chain(key, 1)[0]
    shifted = {**row, "evaluated_at": row["evaluated_at"].astimezone(timezone(timedelta(hours=-6)))}
    assert leaf_hash_of(shifted) == row["leaf_hash"]


def test_tampered_field_detected(key):
    rows = chain(key)
    rows[1]["evaluated_decision"] = "COMPLIANT_VIA_SAFE_HARBOR"
    res = verify_rows(rows, key.public_key())
    assert res["ok"] is False and res["first_bad"]["seq"] == 2
    assert res["first_bad"]["reason"] == "leaf_hash_mismatch"


def test_rehashed_without_key_fails_signature(key):
    rows = chain(key)
    rows[2]["evaluated_decision"] = "EXEMPT_OR_NOT_APPLICABLE"
    rows[2]["leaf_hash"] = leaf_hash_of(rows[2])
    res = verify_rows(rows, key.public_key())
    assert res["first_bad"] == {"seq": 3, "execution_id": str(rows[2]["execution_id"]), "reason": "bad_signature"}


def test_deleted_or_reordered_row_breaks_link(key):
    rows = chain(key)
    assert verify_rows([rows[0], rows[2]], key.public_key())["first_bad"]["reason"] == "broken_link"
    assert verify_rows(rows[1:], key.public_key())["first_bad"]["seq"] == 2


def test_wrong_public_key_fails(key):
    other = Ed25519PrivateKey.generate().public_key()
    assert verify_rows(chain(key), other)["first_bad"]["reason"] == "bad_signature"


def test_garbage_signature_reported_not_raised(key):
    rows = chain(key, 1)
    rows[0]["ed25519_signature"] = base64.b64encode(b"short").decode()
    assert verify_rows(rows, key.public_key())["first_bad"]["reason"] == "bad_signature"


def test_key_created_with_0600_and_reloaded(tmp_path):
    path = tmp_path / ".keys" / "ed25519.pem"
    k1 = load_or_create_signing_key(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    k2 = load_or_create_signing_key(path)
    assert k1.public_key().public_bytes_raw() == k2.public_key().public_bytes_raw()
