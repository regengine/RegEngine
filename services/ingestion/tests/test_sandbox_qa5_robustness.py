"""QA5 robustness pass for ``app/sandbox``: real-behavior regression tests.

Covers failure paths the existing #1342 sweep left open:

* Relational evaluation must never turn one bad value into a whole-batch
  500: non-numeric quantities (per-TLC and cross-TLC transformation),
  malformed timestamps, and mixed naive/aware timestamps.
* ``_validate_kdes`` must flag non-numeric quantities and unparseable
  timestamps so bad input cannot score a false "pass".
* CSV with a UTF-8 BOM must parse instead of reporting a missing column.
* In-memory rate buckets must not grow without bound (parity with the
  #2711 share-bucket cap); Redis zset members must be unique per request.
* ``POST /share`` must enforce the same 2MB CSV cap as ``/evaluate``;
  ``GET /share`` must return 404 (not 500) for stale result shapes.
* Entity-mismatch warnings must be capped so adversarial input cannot
  produce a megabyte-scale response.
* Tenant/auth boundaries: ``/evaluate`` is public by design but must be
  stateless (works with the database down) and must ignore forged
  ``tenant_id`` values; rotating ``X-Forwarded-For`` without a trusted
  proxy must not mint fresh rate-limit buckets end to end.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
if str(service_dir) not in sys.path:
    sys.path.insert(0, str(service_dir))
services_dir = service_dir.parent
if str(services_dir) not in sys.path:
    sys.path.insert(0, str(services_dir))

pytest.importorskip("fastapi")

from app.sandbox import rate_limiting  # noqa: E402
from app.sandbox.csv_parser import (  # noqa: E402
    _normalize_for_rules,
    _parse_csv_to_events,
)
from app.sandbox.evaluators import _evaluate_relational_in_memory  # noqa: E402
from app.sandbox.router import router as sandbox_router  # noqa: E402
from app.sandbox.validation import (  # noqa: E402
    _detect_entity_mismatches,
    _validate_kdes,
)

sandbox_router_mod = sys.modules["app.sandbox.router"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_limiter_state(monkeypatch):
    """Reset limiter globals so tests are isolated."""
    monkeypatch.delenv("SANDBOX_TRUSTED_PROXY_CIDRS", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
    rate_limiting._rate_buckets.clear()
    rate_limiting._redis_client = None
    rate_limiting._redis_failed = False
    rate_limiting._redis_retry_at = 0.0
    sandbox_router_mod._share_buckets.clear()
    yield
    rate_limiting._rate_buckets.clear()
    rate_limiting._redis_client = None
    rate_limiting._redis_failed = False
    rate_limiting._redis_retry_at = 0.0
    sandbox_router_mod._share_buckets.clear()


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    """Evaluate client with the rate limiter disabled (isolation)."""
    monkeypatch.setattr(sandbox_router_mod, "_check_sandbox_rate_limit", lambda ip: None)
    app = FastAPI()
    app.include_router(sandbox_router)
    return TestClient(app)


def _canon(csv_text: str):
    return [_normalize_for_rules(e) for e in _parse_csv_to_events(csv_text)]


def _harvesting_event(**overrides):
    base = {
        "cte_type": "harvesting",
        "traceability_lot_code": "LOT-QA5",
        "product_description": "Spinach",
        "quantity": 100,
        "unit_of_measure": "lb",
        "location_name": "Green Farm",
        "timestamp": "2024-01-01T10:00:00+00:00",
        "kdes": {"harvest_date": "2024-01-01", "reference_document": "DOC-1"},
    }
    base.update(overrides)
    return base


# ===========================================================================
# Relational evaluator: bad values must not crash the batch
# ===========================================================================


class TestRelationalBadDataNoCrash:
    def test_non_numeric_quantity_per_tlc_does_not_crash(self):
        csv_text = (
            "cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,timestamp\n"
            "harvesting,LOT-Q,Spinach,abc,lb,2024-01-01T10:00:00+00:00\n"
            "shipping,LOT-Q,Spinach,50,lb,2024-01-02T10:00:00+00:00\n"
        )
        canon = _canon(csv_text)
        assert canon[0]["quantity"] == "abc"
        # Must not raise; garbage quantity is skipped like a missing one.
        results = _evaluate_relational_in_memory(canon)
        assert isinstance(results, dict)

    def test_non_numeric_quantity_cross_tlc_does_not_crash(self):
        csv_text = (
            "cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,timestamp,input_lot_codes\n"
            "harvesting,LOT-A,Spinach,oops,lb,2024-01-01T10:00:00+00:00,\n"
            "transformation,LOT-Z,Chopped Spinach,ten,lb,2024-01-03T10:00:00+00:00,LOT-A\n"
        )
        canon = _canon(csv_text)
        results = _evaluate_relational_in_memory(canon)
        assert isinstance(results, dict)

    def test_malformed_timestamp_does_not_crash(self):
        csv_text = (
            "cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,timestamp\n"
            "harvesting,LOT-T,Spinach,100,lb,yesterday\n"
            "shipping,LOT-T,Spinach,50,lb,2024-01-02T10:00:00+00:00\n"
        )
        canon = _canon(csv_text)
        results = _evaluate_relational_in_memory(canon)
        assert isinstance(results, dict)

    def test_mixed_naive_and_aware_timestamps_do_not_crash(self):
        csv_text = (
            "cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,timestamp\n"
            "harvesting,LOT-M,Spinach,100,lb,2024-01-01\n"
            "shipping,LOT-M,Spinach,50,lb,2024-01-02T10:00:00+00:00\n"
        )
        canon = _canon(csv_text)
        results = _evaluate_relational_in_memory(canon)
        assert isinstance(results, dict)

    def test_real_paradox_still_detected_with_naive_timestamps(self):
        """Naive timestamps are read as UTC; a genuine chronology paradox
        across the naive/aware boundary must still fail."""
        csv_text = (
            "cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,timestamp\n"
            "harvesting,LOT-P,Spinach,100,lb,2024-01-03\n"
            "shipping,LOT-P,Spinach,50,lb,2024-01-02T10:00:00+00:00\n"
        )
        canon = _canon(csv_text)
        results = _evaluate_relational_in_memory(canon)
        temporal = [
            r for rs in results.values() for r in rs if "Temporal Order" in (r.rule_title or "")
        ]
        assert temporal, "expected temporal order results for the batch"
        assert any(r.result == "fail" for r in temporal)

    def test_evaluate_endpoint_returns_200_on_garbage_csv_values(self, client):
        csv_text = (
            "cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,timestamp\n"
            "harvesting,LOT-Q,Spinach,abc,lb,yesterday\n"
            "shipping,LOT-Q,Spinach,50,lb,2024-01-02T10:00:00+00:00\n"
        )
        resp = client.post("/api/v1/sandbox/evaluate", json={"csv": csv_text})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_events"] == 2
        assert body["total_kde_errors"] >= 2


# ===========================================================================
# KDE validation: bad values must be flagged, good values left alone
# ===========================================================================


class TestKdeNumericAndTimestampChecks:
    def test_non_numeric_quantity_flagged(self):
        event = _harvesting_event(quantity="abc")
        errors = _validate_kdes(event)
        assert any("quantity" in e.lower() for e in errors)

    def test_infinite_quantity_flagged(self):
        event = _harvesting_event(quantity="inf")
        errors = _validate_kdes(event)
        assert any("quantity" in e.lower() for e in errors)

    def test_numeric_string_quantity_accepted(self):
        event = _harvesting_event(quantity="10")
        errors = _validate_kdes(event)
        assert not any("quantity" in e.lower() for e in errors)

    def test_zero_quantity_not_flagged_as_missing_or_bad(self):
        event = _harvesting_event(quantity=0)
        errors = _validate_kdes(event)
        assert not any("quantity" in e.lower() for e in errors)

    def test_malformed_timestamp_flagged(self):
        event = _harvesting_event(timestamp="yesterday")
        errors = _validate_kdes(event)
        assert any("timestamp" in e.lower() for e in errors)

    def test_valid_iso_timestamp_accepted(self):
        event = _harvesting_event(timestamp="2024-01-01T10:00:00+00:00")
        errors = _validate_kdes(event)
        assert not any("timestamp" in e.lower() for e in errors)

    def test_naive_date_timestamp_accepted(self):
        event = _harvesting_event(timestamp="2024-01-01")
        errors = _validate_kdes(event)
        assert not any("timestamp" in e.lower() for e in errors)


# ===========================================================================
# CSV: BOM handling
# ===========================================================================


class TestCsvBomHandling:
    def test_bom_prefixed_header_parses(self):
        csv_text = (
            "\ufeffcte_type,traceability_lot_code,product_description\n"
            "harvesting,LOT-B,Spinach\n"
        )
        events = _parse_csv_to_events(csv_text)
        assert len(events) == 1
        assert events[0]["cte_type"] == "harvesting"
        assert events[0]["traceability_lot_code"] == "LOT-B"


# ===========================================================================
# Rate limiting: bounded memory, unique members, spoof resistance end to end
# ===========================================================================


class TestRateLimiterMemoryBound:
    def test_stale_buckets_evicted_once_over_cap(self, monkeypatch):
        cap = 10000
        assert rate_limiting._RATE_BUCKET_CAP == cap
        # Seed just over the cap with buckets whose newest entry is stale.
        for i in range(cap + 5):
            rate_limiting._rate_buckets[f"10.9.{i // 256}.{i % 256}"] = [0.0]
        rate_limiting._check_in_memory("203.0.113.7", now=10_000.0)
        assert "203.0.113.7" in rate_limiting._rate_buckets
        assert len(rate_limiting._rate_buckets) <= cap + 1

    def test_fresh_buckets_survive_eviction(self):
        for i in range(rate_limiting._RATE_BUCKET_CAP + 5):
            rate_limiting._rate_buckets[f"10.8.{i // 256}.{i % 256}"] = [0.0]
        rate_limiting._rate_buckets["198.51.100.9"] = [10_000.0]
        rate_limiting._check_in_memory("203.0.113.8", now=10_000.0)
        assert "198.51.100.9" in rate_limiting._rate_buckets

    def test_small_table_never_evicted(self):
        rate_limiting._rate_buckets["192.0.2.1"] = [0.0]
        rate_limiting._check_in_memory("192.0.2.2", now=10_000.0)
        assert "192.0.2.1" in rate_limiting._rate_buckets


class _FakeRedis:
    """Minimal Redis surrogate for the zset sliding-window path."""

    def __init__(self, zcard_value=0):
        self._zcard = zcard_value
        self.zadd_calls = []

    def pipeline(self):
        class _Pipe:
            def zremrangebyscore(self, *a):
                pass

            def zcard(self, *a):
                pass

            def execute(self):
                pass

        return _Pipe()

    def zcard(self, key):
        return self._zcard

    def zrange(self, key, start, stop, withscores=False):
        return []

    def zadd(self, key, mapping):
        self.zadd_calls.append((key, mapping))

    def expire(self, key, ttl):
        pass


class TestRedisMemberUniqueness:
    def test_same_instant_requests_create_distinct_members(self, monkeypatch):
        fake = _FakeRedis(zcard_value=0)
        monkeypatch.setattr(rate_limiting, "_get_redis", lambda: fake)
        assert rate_limiting._check_redis("1.2.3.4", now=1000.0) == 0
        assert rate_limiting._check_redis("1.2.3.4", now=1000.0) == 0
        assert len(fake.zadd_calls) == 2
        members = [list(mapping.keys())[0] for _, mapping in fake.zadd_calls]
        assert members[0] != members[1]
        assert all(m.startswith("1000.0") for m in members)


class TestXffSpoofEndToEnd:
    def test_rotating_spoofed_xff_does_not_mint_buckets(self):
        """No trusted proxy configured: 30 requests from one peer with a
        different spoofed X-Forwarded-For each time must still trip the
        30/minute limit on the 31st request."""
        app = FastAPI()
        app.include_router(sandbox_router)
        spoof_client = TestClient(app, raise_server_exceptions=False)
        for i in range(30):
            resp = spoof_client.post(
                "/api/v1/sandbox/evaluate",
                json={"events": [_harvesting_event()]},
                headers={"X-Forwarded-For": f"9.9.9.{i % 250 + 1}"},
            )
            assert resp.status_code == 200, resp.text
        resp = spoof_client.post(
            "/api/v1/sandbox/evaluate",
            json={"events": [_harvesting_event()]},
            headers={"X-Forwarded-For": "9.9.9.250"},
        )
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers


# ===========================================================================
# Share endpoints: size cap and stale-shape handling
# ===========================================================================


def _share_payload(**overrides):
    payload = {
        "csv": "cte_type,traceability_lot_code\nshipping,TLC-1\n",
        "result": {
            "total_events": 1,
            "compliant_events": 1,
            "non_compliant_events": 0,
            "total_kde_errors": 0,
            "total_rule_failures": 0,
            "submission_blocked": False,
            "blocking_reasons": [],
            "events": [],
        },
    }
    payload.update(overrides)
    return payload


class TestShareSizeCap:
    def test_oversize_csv_rejected_with_413(self, client):
        payload = _share_payload(csv="x" * 2_000_001)
        resp = client.post("/api/v1/sandbox/share", json=payload)
        assert resp.status_code == 413

    def test_normal_csv_not_rejected_by_cap(self, client):
        resp = client.post("/api/v1/sandbox/share", json=_share_payload())
        # Either stored (201/200) or DB-unavailable (503 without a real DB);
        # it must NOT be a size rejection.
        assert resp.status_code != 413


class TestShareStaleShape:
    def test_unparseable_stored_result_returns_404_not_500(self, client, monkeypatch):
        import shared.database as shared_db

        @contextmanager
        def _fake_get_db():
            db = MagicMock()
            # Stored JSON missing every required SandboxResponse field.
            db.execute.return_value.fetchone.return_value = ('{"nope": true}',)
            yield db

        monkeypatch.setattr(shared_db, "get_db", _fake_get_db)
        resp = client.get("/api/v1/sandbox/share/abc123")
        assert resp.status_code == 404


# ===========================================================================
# Entity warnings: capped output
# ===========================================================================


class TestEntityWarningCap:
    def test_many_variants_produce_bounded_warnings(self):
        firsts = ["Acme", "ACME", "acme", "aCmE", "AcMe", "ACME", "Acme", "ACme"]
        seconds = ["Foods", "FOODS", "foods", "fOoDs", "Foods", "FOODS", "foods", "FOODS"]
        events = []
        for i in range(150):
            name = firsts[i % 8] + " " * ((i // 8) % 5 + 1) + seconds[(i // 40) % 8] + "." * (i % 3)
            events.append({"location_name": name})
        warnings = _detect_entity_mismatches(events)
        assert len(warnings) <= 101
        assert any("more" in w and "omitted" in w for w in warnings)

    def test_small_case_still_lists_every_pair(self):
        events = [
            {"location_name": "Acme Inc"},
            {"location_name": "Acme Corp"},
        ]
        warnings = _detect_entity_mismatches(events)
        assert len(warnings) == 1
        assert "standardizing" in warnings[0]


# ===========================================================================
# Tenant/auth boundaries: public but stateless, forged tenant ignored
# ===========================================================================


class TestSandboxBoundaries:
    def test_evaluate_is_stateless_when_database_is_down(self, client, monkeypatch):
        """evaluate must never touch Postgres: with get_db raising, a JSON
        evaluation still returns 200 (no persistence, no tenant lookup)."""
        import shared.database as shared_db

        @contextmanager
        def _boom():
            raise RuntimeError("db is down")
            yield  # pragma: no cover

        monkeypatch.setattr(shared_db, "get_db", _boom)
        resp = client.post("/api/v1/sandbox/evaluate", json={"events": [_harvesting_event()]})
        assert resp.status_code == 200

    def test_forged_tenant_id_in_kdes_changes_nothing(self, client):
        """A caller-supplied tenant_id inside kdes must not alter scoring
        and must never be echoed back (the sandbox has no tenant concept)."""
        plain = {"events": [_harvesting_event()]}
        forged = {"events": [_harvesting_event(kdes={
            "harvest_date": "2024-01-01",
            "reference_document": "DOC-1",
            "tenant_id": "other-tenant-uuid",
        })]}
        r1 = client.post("/api/v1/sandbox/evaluate", json=plain)
        r2 = client.post("/api/v1/sandbox/evaluate", json=forged)
        assert r1.status_code == 200
        assert r2.status_code == 200
        b1, b2 = r1.json(), r2.json()
        for key in ("total_events", "compliant_events", "non_compliant_events",
                    "total_kde_errors", "total_rule_failures", "submission_blocked"):
            assert b1[key] == b2[key], key
        assert "tenant" not in r2.text.lower()
