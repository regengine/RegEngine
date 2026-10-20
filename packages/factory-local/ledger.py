"""Hash chained, Ed25519 signed compliance receipts.

Each receipt's leaf hash is SHA-256 over the RFC 8785 canonical JSON of its
fields, including the previous leaf hash of the same tenant. The signature is
over the 32 raw bytes of the leaf hash. Genesis previous hash is "0" * 64.

The pure functions (canonical_hash, build_receipt, verify_rows) carry all the
logic and are tested offline. append_receipt / verify_chain add Postgres IO.
"""

from __future__ import annotations

import base64
import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

GENESIS = "0" * 64
DEFAULT_KEY_PATH = Path(__file__).resolve().parent / ".keys" / "ed25519.pem"

LEAF_FIELDS = (
    "execution_id", "tenant_id", "rule_uid", "version_uid", "input_payload_hash",
    "evaluated_decision", "citation_uri", "previous_leaf_hash", "evaluated_at",
)


def canonical_hash(obj: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(obj)).hexdigest()


def load_or_create_signing_key(path: Path = DEFAULT_KEY_PATH) -> Ed25519PrivateKey:
    path = Path(path)
    if path.exists():
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError(f"{path} is not an Ed25519 private key")
        return key
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(pem)
    os.chmod(path, 0o600)
    return key


def _ts(value: datetime) -> str:
    # Postgres timestamptz keeps microseconds; normalise to UTC so the string
    # recomputed from a database row matches the one signed at append time.
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def leaf_hash_of(row: dict) -> str:
    leaf = {k: row[k] for k in LEAF_FIELDS}
    leaf["execution_id"] = str(leaf["execution_id"])
    leaf["evaluated_at"] = _ts(leaf["evaluated_at"])
    return canonical_hash(leaf)


def build_receipt(
    *,
    previous_leaf_hash: str,
    tenant_id: str,
    rule_uid: str,
    version_uid: str,
    input_payload: Any,
    evaluated_decision: str,
    citation_uri: str,
    private_key: Ed25519PrivateKey,
    evaluated_at: datetime | None = None,
    execution_id: uuid.UUID | None = None,
) -> dict:
    row = {
        "execution_id": execution_id or uuid.uuid4(),
        "tenant_id": tenant_id,
        "rule_uid": rule_uid,
        "version_uid": version_uid,
        "input_payload_hash": canonical_hash(input_payload),
        "evaluated_decision": evaluated_decision,
        "citation_uri": citation_uri,
        "previous_leaf_hash": previous_leaf_hash,
        "evaluated_at": evaluated_at or datetime.now(timezone.utc),
    }
    row["leaf_hash"] = leaf_hash_of(row)
    row["ed25519_signature"] = base64.b64encode(private_key.sign(bytes.fromhex(row["leaf_hash"]))).decode()
    return row


def verify_rows(rows: Iterable[dict], public_key: Ed25519PublicKey) -> dict:
    """Rows must be one tenant's receipts in seq order."""
    expected_prev, count = GENESIS, 0
    for row in rows:
        count += 1
        where = {"seq": row.get("seq"), "execution_id": str(row["execution_id"])}
        if row["previous_leaf_hash"] != expected_prev:
            return {"ok": False, "count": count, "first_bad": {**where, "reason": "broken_link"}}
        if leaf_hash_of(row) != row["leaf_hash"]:
            return {"ok": False, "count": count, "first_bad": {**where, "reason": "leaf_hash_mismatch"}}
        try:
            public_key.verify(base64.b64decode(row["ed25519_signature"]), bytes.fromhex(row["leaf_hash"]))
        except (InvalidSignature, ValueError):
            return {"ok": False, "count": count, "first_bad": {**where, "reason": "bad_signature"}}
        expected_prev = row["leaf_hash"]
    return {"ok": True, "count": count, "first_bad": None}


_INSERT = """
INSERT INTO compliance_audit_ledger (
    execution_id, tenant_id, rule_uid, version_uid, input_payload_hash,
    evaluated_decision, citation_uri, previous_leaf_hash, leaf_hash,
    ed25519_signature, evaluated_at
) VALUES (
    %(execution_id)s, %(tenant_id)s, %(rule_uid)s, %(version_uid)s, %(input_payload_hash)s,
    %(evaluated_decision)s, %(citation_uri)s, %(previous_leaf_hash)s, %(leaf_hash)s,
    %(ed25519_signature)s, %(evaluated_at)s
) RETURNING seq
"""


def append_receipt(
    conn,
    tenant_id: str,
    *,
    rule_uid: str,
    version_uid: str,
    input_payload: Any,
    evaluated_decision: str,
    citation_uri: str,
    private_key: Ed25519PrivateKey,
) -> dict:
    """Append one receipt. The per-tenant advisory lock serialises writers so two
    concurrent appends cannot both chain off the same previous leaf."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (tenant_id,))
            cur.execute(
                "SELECT leaf_hash FROM compliance_audit_ledger WHERE tenant_id = %s ORDER BY seq DESC LIMIT 1",
                (tenant_id,),
            )
            prev = cur.fetchone()
            row = build_receipt(
                previous_leaf_hash=prev[0] if prev else GENESIS,
                tenant_id=tenant_id,
                rule_uid=rule_uid,
                version_uid=version_uid,
                input_payload=input_payload,
                evaluated_decision=evaluated_decision,
                citation_uri=citation_uri,
                private_key=private_key,
            )
            cur.execute(_INSERT, row)
            row["seq"] = cur.fetchone()[0]
    return row


def fetch_rows(conn, tenant_id: str) -> list[dict]:
    cols = ("seq", *LEAF_FIELDS, "leaf_hash", "ed25519_signature")
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {', '.join(cols)} FROM compliance_audit_ledger WHERE tenant_id = %s ORDER BY seq",
            (tenant_id,),
        )
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def verify_chain(conn, tenant_id: str, public_key: Ed25519PublicKey) -> dict:
    return verify_rows(fetch_rows(conn, tenant_id), public_key)
