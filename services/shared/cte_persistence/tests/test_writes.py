"""Focused tests for the single-event write path (``writes.WritePathMixin.store_event``).

Covers the main public behavior with a mocked SQLAlchemy session (no DB,
no network): happy-path persistence, chain sequencing, the idempotent
replay short-circuit, rejected-event handling, duplicate-hash errors, and
input-validation edge cases. ``store_event`` is LEGACY (#1335), so the
DeprecationWarning it emits is asserted once and ignored elsewhere.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest

from services.shared.cte_persistence.core import CTEPersistence
from services.shared.cte_persistence.models import DuplicateEventError

BASE_KWARGS: Dict[str, Any] = dict(
    tenant_id="tenant-1",
    event_type="receiving",
    traceability_lot_code="LOT-001",
    product_description="Romaine lettuce",
    quantity=50.0,
    unit_of_measure="kg",
    event_timestamp="2026-01-15T10:00:00+00:00",
    source="api",
)


def _make_session(
    *,
    idempotent_row: Optional[Tuple[Any, ...]] = None,
    chain_head: Optional[Tuple[Any, ...]] = None,
    fail_on: Optional[str] = None,
) -> MagicMock:
    """Return a MagicMock session that answers the write-path SELECTs.

    Records every (sql, params) pair on ``session.calls``. INSERTs are
    accepted silently; SELECTs return the canned rows (None by default,
    meaning "no existing row").
    """
    session = MagicMock()
    calls: List[Tuple[str, Any]] = []

    def _execute(stmt: Any, params: Any = None, **kwargs: Any) -> MagicMock:
        sql = str(stmt)
        calls.append((sql, params))
        if fail_on is not None and fail_on in sql:
            raise RuntimeError("simulated insert failure")
        result = MagicMock()
        result.fetchall.return_value = []
        normalized = sql.lstrip().upper()
        if "PG_ADVISORY_XACT_LOCK" in normalized:
            result.fetchone.return_value = None
        elif normalized.startswith("SELECT") and "IDEMPOTENCY_KEY" in normalized:
            result.fetchone.return_value = idempotent_row
        elif normalized.startswith("SELECT") and "HASH_CHAIN" in normalized:
            result.fetchone.return_value = chain_head
        elif "SHA256_HASH = :SHA" in normalized:
            result.fetchone.return_value = None
        else:
            result.fetchone.return_value = None
        return result

    session.execute.side_effect = _execute
    session.calls = calls  # type: ignore[attr-defined]
    session.begin_nested.return_value = MagicMock()
    return session


def _sqls(session: MagicMock) -> List[str]:
    return [sql for sql, _ in session.calls]  # type: ignore[attr-defined]


def _params_for(session: MagicMock, marker: str) -> List[Any]:
    return [params for sql, params in session.calls if marker in sql]  # type: ignore[attr-defined]


def _store(**overrides: Any) -> Tuple[Any, MagicMock]:
    kwargs = dict(BASE_KWARGS)
    kwargs.update(overrides)
    session = _make_session()
    persistence = CTEPersistence(session)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = persistence.store_event(**kwargs)
    return result, session


class TestAcquireChainLock:
    def test_issues_transaction_scoped_advisory_lock(self) -> None:
        session = _make_session()
        CTEPersistence(session)._acquire_chain_lock("tenant-1")
        assert len(session.calls) == 1  # type: ignore[attr-defined]
        sql, params = session.calls[0]  # type: ignore[attr-defined]
        assert "pg_advisory_xact_lock" in sql
        assert params == {"tid": "tenant-1"}

    def test_lock_is_scoped_per_tenant(self) -> None:
        session = _make_session()
        persistence = CTEPersistence(session)
        persistence._acquire_chain_lock("tenant-a")
        persistence._acquire_chain_lock("tenant-b")
        tids = [params["tid"] for _, params in session.calls]  # type: ignore[attr-defined]
        assert tids == ["tenant-a", "tenant-b"]


class TestStoreEventSuccess:
    def test_persists_event_kdes_and_chain_link(self) -> None:
        result, session = _store(kdes={"lot_code": "LOT-001", "origin": "Farm A"})
        assert result.success is True
        assert result.idempotent is False
        assert result.event_id
        assert len(result.sha256_hash) == 64
        assert len(result.chain_hash) == 64
        sqls = _sqls(session)
        assert any("INSERT INTO fsma.cte_events" in sql for sql in sqls)
        assert any("INSERT INTO fsma.cte_kdes" in sql for sql in sqls)
        assert any("INSERT INTO fsma.hash_chain" in sql for sql in sqls)

    def test_acquires_chain_lock_before_idempotency_check(self) -> None:
        _, session = _store()
        sqls = _sqls(session)
        lock_idx = next(i for i, sql in enumerate(sqls) if "pg_advisory_xact_lock" in sql)
        idem_idx = next(
            i
            for i, sql in enumerate(sqls)
            if sql.lstrip().upper().startswith("SELECT") and "IDEMPOTENCY_KEY" in sql.upper()
        )
        assert lock_idx < idem_idx

    def test_genesis_event_starts_chain_at_sequence_one(self) -> None:
        _, session = _store()
        chain_params = _params_for(session, "INSERT INTO fsma.hash_chain")
        assert len(chain_params) == 1
        assert chain_params[0]["sequence_num"] == 1
        assert chain_params[0]["previous_chain_hash"] is None

    def test_sequence_continues_from_existing_chain_head(self) -> None:
        session = _make_session(chain_head=("prev-chain-hash", 4))
        persistence = CTEPersistence(session)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = persistence.store_event(**BASE_KWARGS)
        assert result.success is True
        chain_params = _params_for(session, "INSERT INTO fsma.hash_chain")
        assert chain_params[0]["sequence_num"] == 5
        assert chain_params[0]["previous_chain_hash"] == "prev-chain-hash"

    def test_none_kde_values_are_skipped(self) -> None:
        result, session = _store(kdes={"present": "value", "absent": None})
        assert result.success is True
        kde_params = _params_for(session, "fsma.cte_kdes")
        assert [params["kde_key"] for params in kde_params] == ["present"]

    def test_alert_insert_failure_does_not_fail_event(self) -> None:
        session = _make_session(fail_on="compliance_alerts")
        persistence = CTEPersistence(session)
        alert = {"alert_type": "missing_kde", "severity": "warning", "message": "optional KDE absent"}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = persistence.store_event(**{**BASE_KWARGS, "alerts": [alert]})
        assert result.success is True
        assert any("INSERT INTO fsma.cte_events" in sql for sql in _sqls(session))

    def test_emits_legacy_deprecation_warning(self) -> None:
        session = _make_session()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            CTEPersistence(session).store_event(**BASE_KWARGS)
        dep = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(dep) >= 1
        assert "LEGACY" in str(dep[0].message)


class TestStoreEventIdempotentReplay:
    def test_replay_returns_existing_ids_without_inserting(self) -> None:
        existing = ("existing-event-id", "sha" * 21 + "abc", "chain" * 12 + "abcd")
        session = _make_session(idempotent_row=existing)
        persistence = CTEPersistence(session)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = persistence.store_event(**BASE_KWARGS)
        assert result.success is True
        assert result.idempotent is True
        assert result.event_id == "existing-event-id"
        assert result.sha256_hash == existing[1]
        assert result.chain_hash == existing[2]
        sqls = _sqls(session)
        assert not any("INSERT INTO fsma.cte_events" in sql for sql in sqls)
        assert not any("INSERT INTO fsma.hash_chain" in sql for sql in sqls)


class TestStoreEventRejected:
    def test_rejected_event_persists_row_but_skips_chain(self) -> None:
        session = _make_session()
        persistence = CTEPersistence(session)
        alerts = [{"alert_type": "temperature_excursion", "severity": "reject", "reason": "too warm"}]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = persistence.store_event(**{**BASE_KWARGS, "alerts": alerts})
        assert result.success is False
        assert result.errors == ["too warm"]
        assert result.alerts == alerts
        sqls = _sqls(session)
        assert any("INSERT INTO fsma.cte_events" in sql for sql in sqls)
        assert not any("INSERT INTO fsma.hash_chain" in sql for sql in sqls)

    def test_rejected_validator_result_reports_reason(self) -> None:
        session = _make_session()
        persistence = CTEPersistence(session)
        validators = [{"severity": "error", "reason": "missing required KDE"}]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = persistence.store_event(**{**BASE_KWARGS, "validator_results": validators})
        assert result.success is False
        assert result.errors == ["missing required KDE"]


class TestStoreEventInputValidation:
    def test_unknown_event_type_raises_before_any_write(self) -> None:
        session = _make_session()
        persistence = CTEPersistence(session)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            with pytest.raises(ValueError, match="not a recognized FSMA 204 CTE type"):
                persistence.store_event(**{**BASE_KWARGS, "event_type": "HARVESTING "})
        assert session.execute.call_count == 0

    def test_naive_timestamp_raises(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            with pytest.raises(ValueError, match="timezone-aware"):
                _store(event_timestamp="2026-01-15T10:00:00")

    def test_future_timestamp_raises(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            with pytest.raises(ValueError, match="future"):
                _store(event_timestamp="2999-01-01T00:00:00+00:00")

    def test_duplicate_hash_raises_duplicate_event_error(self) -> None:
        session = _make_session()
        persistence = CTEPersistence(session)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            with (
                patch(
                    "services.shared.cte_persistence.core._assert_not_exists",
                    side_effect=DuplicateEventError("original-id", "s" * 64),
                ),
                pytest.raises(DuplicateEventError),
            ):
                persistence.store_event(**BASE_KWARGS)
