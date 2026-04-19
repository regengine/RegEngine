"""Coverage for app/fda_export/merkle.py — Merkle root + inclusion-proof handlers.

Locks:
- get_merkle_root_handler: happy path returns tenant_id + chain fields,
  exception path raises HTTPException(500), HTTPException pass-through,
  finally closes db_session even on error.
- get_merkle_proof_handler: happy path returns tenant_id + proof fields,
  None proof → 404, exception path raises 500, HTTPException pass-through,
  finally closes db_session.

The handlers import ``shared.database.SessionLocal`` and
``shared.cte_persistence.CTEPersistence`` lazily inside the function, so we
install stubs via ``sys.modules`` before each call.

Issue: #1342
"""

from __future__ import annotations

import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import HTTPException

from app.fda_export import merkle as merkle_mod


# ---------------------------------------------------------------------------
# Stub factories
# ---------------------------------------------------------------------------


class _FakeSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _FakePersistence:
    """Captures last call; configurable return or raise."""

    def __init__(self, db_session):
        self.db_session = db_session
        self.verify_return = SimpleNamespace(
            valid=True,
            merkle_root="0xabc",
            chain_length=7,
            tree_depth=3,
            errors=[],
            checked_at="2026-04-19T00:00:00Z",
        )
        self.proof_return = {"event_id": "E1", "proof": ["0xdead"], "leaf_hash": "0xbeef"}
        self.verify_exc: Exception | None = None
        self.proof_exc: Exception | None = None

    def verify_chain_merkle(self, tenant_id):
        if self.verify_exc is not None:
            raise self.verify_exc
        return self.verify_return

    def get_merkle_proof(self, tenant_id, event_id):
        if self.proof_exc is not None:
            raise self.proof_exc
        return self.proof_return


@pytest.fixture
def stub_deps(monkeypatch):
    """Install stub modules for shared.database.SessionLocal and
    shared.cte_persistence.CTEPersistence. Returns a handle to tweak the
    per-call session + persistence state."""
    state = SimpleNamespace(
        session=_FakeSession(),
        persistence_cls=None,
        persistence_instance=None,
        session_factory_exc=None,
    )

    def _session_factory():
        if state.session_factory_exc is not None:
            raise state.session_factory_exc
        # Each call builds a fresh session so tests can assert close().
        state.session = _FakeSession()
        return state.session

    # ``shared.database`` — fresh module with SessionLocal attribute
    db_mod = ModuleType("shared.database")
    db_mod.SessionLocal = _session_factory
    monkeypatch.setitem(sys.modules, "shared.database", db_mod)

    # ``shared.cte_persistence`` — module with CTEPersistence class
    def _persistence_cls(db_session):
        state.persistence_instance = _FakePersistence(db_session)
        return state.persistence_instance

    cp_mod = ModuleType("shared.cte_persistence")
    cp_mod.CTEPersistence = _persistence_cls
    monkeypatch.setitem(sys.modules, "shared.cte_persistence", cp_mod)

    state.persistence_cls = _persistence_cls
    return state


# ---------------------------------------------------------------------------
# get_merkle_root_handler
# ---------------------------------------------------------------------------


class TestMerkleRootHandler:

    def test_happy_path_returns_full_payload(self, stub_deps):
        out = asyncio.run(merkle_mod.get_merkle_root_handler("tenant-1"))
        assert out == {
            "tenant_id": "tenant-1",
            "valid": True,
            "merkle_root": "0xabc",
            "chain_length": 7,
            "tree_depth": 3,
            "errors": [],
            "checked_at": "2026-04-19T00:00:00Z",
        }
        # Session closed on success
        assert stub_deps.session.closed is True

    def test_uses_verify_chain_merkle_result_fields(self, stub_deps):
        """Any field from the verify_chain_merkle result should be forwarded."""
        stub_deps_session = stub_deps  # alias for clarity
        # Pre-load a custom result BEFORE invocation. Because the stub rebuilds
        # the persistence_instance on every call, we patch the class factory.
        from unittest.mock import patch

        custom = SimpleNamespace(
            valid=False,
            merkle_root="0xdeadbeef",
            chain_length=99,
            tree_depth=6,
            errors=["leaf 3 corrupted"],
            checked_at="2026-01-01T12:00:00Z",
        )

        def _cls(db_session):
            inst = _FakePersistence(db_session)
            inst.verify_return = custom
            return inst

        cp_mod = sys.modules["shared.cte_persistence"]
        with patch.object(cp_mod, "CTEPersistence", _cls):
            out = asyncio.run(merkle_mod.get_merkle_root_handler("t"))
        assert out["valid"] is False
        assert out["merkle_root"] == "0xdeadbeef"
        assert out["errors"] == ["leaf 3 corrupted"]
        assert out["tree_depth"] == 6

    def test_http_exception_passes_through(self, stub_deps):
        """A raised HTTPException should propagate unchanged, not be wrapped."""
        from unittest.mock import patch

        def _cls(db_session):
            inst = _FakePersistence(db_session)
            inst.verify_exc = HTTPException(status_code=418, detail="teapot")
            return inst

        cp_mod = sys.modules["shared.cte_persistence"]
        with patch.object(cp_mod, "CTEPersistence", _cls):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(merkle_mod.get_merkle_root_handler("t"))
        assert exc_info.value.status_code == 418
        assert exc_info.value.detail == "teapot"
        assert stub_deps.session.closed is True

    def test_generic_exception_becomes_500(self, stub_deps):
        from unittest.mock import patch

        def _cls(db_session):
            inst = _FakePersistence(db_session)
            inst.verify_exc = RuntimeError("database gone")
            return inst

        cp_mod = sys.modules["shared.cte_persistence"]
        with patch.object(cp_mod, "CTEPersistence", _cls):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(merkle_mod.get_merkle_root_handler("t"))
        assert exc_info.value.status_code == 500
        assert "Merkle root computation failed" in exc_info.value.detail
        # Session still closed in finally
        assert stub_deps.session.closed is True

    def test_finally_skipped_when_sessionlocal_raises(self, stub_deps):
        """If SessionLocal() raises, db_session remains None, finally no-ops."""
        stub_deps.session_factory_exc = OSError("cannot connect")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(merkle_mod.get_merkle_root_handler("t"))
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# get_merkle_proof_handler
# ---------------------------------------------------------------------------


class TestMerkleProofHandler:

    def test_happy_path_returns_proof_with_tenant_id(self, stub_deps):
        out = asyncio.run(
            merkle_mod.get_merkle_proof_handler("tenant-1", "E1")
        )
        assert out["tenant_id"] == "tenant-1"
        assert out["event_id"] == "E1"
        assert out["proof"] == ["0xdead"]
        assert out["leaf_hash"] == "0xbeef"
        assert stub_deps.session.closed is True

    def test_none_proof_raises_404(self, stub_deps):
        from unittest.mock import patch

        def _cls(db_session):
            inst = _FakePersistence(db_session)
            inst.proof_return = None  # Event not found
            return inst

        cp_mod = sys.modules["shared.cte_persistence"]
        with patch.object(cp_mod, "CTEPersistence", _cls):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(merkle_mod.get_merkle_proof_handler("t", "E-missing"))
        assert exc_info.value.status_code == 404
        assert "E-missing" in exc_info.value.detail
        assert "'t'" in exc_info.value.detail
        # db_session should still be closed on 404
        assert stub_deps.session.closed is True

    def test_http_exception_passes_through(self, stub_deps):
        from unittest.mock import patch

        def _cls(db_session):
            inst = _FakePersistence(db_session)
            inst.proof_exc = HTTPException(status_code=403, detail="forbidden")
            return inst

        cp_mod = sys.modules["shared.cte_persistence"]
        with patch.object(cp_mod, "CTEPersistence", _cls):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(merkle_mod.get_merkle_proof_handler("t", "E1"))
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "forbidden"
        assert stub_deps.session.closed is True

    def test_generic_exception_becomes_500(self, stub_deps):
        from unittest.mock import patch

        def _cls(db_session):
            inst = _FakePersistence(db_session)
            inst.proof_exc = ValueError("bad tree")
            return inst

        cp_mod = sys.modules["shared.cte_persistence"]
        with patch.object(cp_mod, "CTEPersistence", _cls):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(merkle_mod.get_merkle_proof_handler("t", "E1"))
        assert exc_info.value.status_code == 500
        assert "Merkle proof generation failed" in exc_info.value.detail
        assert stub_deps.session.closed is True

    def test_finally_skipped_when_sessionlocal_raises(self, stub_deps):
        stub_deps.session_factory_exc = OSError("cannot connect")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(merkle_mod.get_merkle_proof_handler("t", "E1"))
        assert exc_info.value.status_code == 500
