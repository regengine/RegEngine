"""Focused coverage for ``shared.rules.seeds``.

Covers the module's two public surfaces without a database:

- ``FSMA_RULE_SEEDS`` shape (required keys, severity/category values,
  JSON-serializable payloads, unique titles).
- ``seed_rule_definitions`` insert/idempotency behavior against a fake
  session, plus edge cases (empty seed list, pre-seeded titles, DB error
  propagation).

Pure-Python; no network, no real services.
"""

from __future__ import annotations

import json

import pytest
from shared.rules import seeds as seeds_module
from shared.rules.seeds import FSMA_RULE_SEEDS, seed_rule_definitions

REQUIRED_KEYS = {
    "title",
    "description",
    "severity",
    "category",
    "applicability_conditions",
    "citation_reference",
    "evaluation_logic",
    "failure_reason_template",
    "remediation_suggestion",
}

ALLOWED_SEVERITIES = {"critical", "warning"}

KNOWN_LOGIC_TYPES = {
    "field_presence",
    "multi_field_presence",
    "gs1_check_digit",
    "numeric_range",
    "temporal_order",
    "identity_consistency",
    "mass_balance",
}

KNOWN_CTE_TYPES = {
    "harvesting",
    "cooling",
    "initial_packing",
    "first_land_based_receiving",
    "shipping",
    "receiving",
    "transformation",
}


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class FakeSession:
    """Minimal stand-in for a SQLAlchemy Session.

    Answers the SELECT-by-title existence check from an in-memory set
    and records rule/audit inserts. ``fail_on="select"`` or
    ``fail_on="insert"`` raises to simulate a database error.
    """

    def __init__(self, existing_titles=(), fail_on=None):
        self.existing = set(existing_titles)
        self.inserts: list[dict] = []
        self.audits: list[dict] = []
        self.selects = 0
        self.fail_on = fail_on

    def execute(self, clause, params=None):
        sql = str(clause)
        params = dict(params or {})
        if "SELECT" in sql:
            if self.fail_on == "select":
                raise RuntimeError("database unavailable")
            self.selects += 1
            title = params.get("title")
            return _Result(("existing-id",) if title in self.existing else None)
        if "rule_audit_log" in sql:
            self.audits.append(params)
            return _Result(None)
        if self.fail_on == "insert":
            raise RuntimeError("database unavailable")
        self.inserts.append(params)
        self.existing.add(params.get("title"))
        return _Result(None)


def test_seed_list_is_nonempty_with_unique_titles():
    assert len(FSMA_RULE_SEEDS) > 0
    titles = [seed["title"] for seed in FSMA_RULE_SEEDS]
    assert len(set(titles)) == len(titles), "duplicate rule titles would break idempotent seeding"


def test_each_seed_has_required_shape():
    problems = []
    for seed in FSMA_RULE_SEEDS:
        title = seed.get("title", "<missing title>")
        missing = REQUIRED_KEYS - set(seed)
        if missing:
            problems.append(f"{title!r} missing keys: {sorted(missing)}")
            continue
        if seed["severity"] not in ALLOWED_SEVERITIES:
            problems.append(f"{title!r} has unexpected severity {seed['severity']!r}")
        logic = seed["evaluation_logic"]
        if logic.get("type") not in KNOWN_LOGIC_TYPES:
            problems.append(f"{title!r} has unknown logic type {logic.get('type')!r}")
        cte_types = (seed.get("applicability_conditions") or {}).get("cte_types", [])
        unknown = set(cte_types) - KNOWN_CTE_TYPES
        if unknown:
            problems.append(f"{title!r} scopes unknown CTE types: {sorted(unknown)}")
    assert not problems, "seed shape problems:\n" + "\n".join(problems)


def test_seed_payloads_are_json_serializable():
    for seed in FSMA_RULE_SEEDS:
        json.dumps(seed.get("applicability_conditions", {}))
        json.dumps(seed["evaluation_logic"])


def test_seed_inserts_all_rules_on_empty_db():
    session = FakeSession()
    inserted = seed_rule_definitions(session)
    assert inserted == len(FSMA_RULE_SEEDS)
    assert len(session.inserts) == len(FSMA_RULE_SEEDS)
    assert len(session.audits) == len(FSMA_RULE_SEEDS)
    inserted_titles = {params["title"] for params in session.inserts}
    assert inserted_titles == {seed["title"] for seed in FSMA_RULE_SEEDS}
    for params in session.inserts:
        assert params["rule_id"], "each inserted rule needs an id"
        json.loads(params["applicability"])
        json.loads(params["logic"])


def test_seed_is_idempotent_on_second_run():
    session = FakeSession()
    assert seed_rule_definitions(session) == len(FSMA_RULE_SEEDS)
    assert seed_rule_definitions(session) == 0
    assert len(session.inserts) == len(FSMA_RULE_SEEDS)


def test_seed_skips_only_preexisting_titles():
    first_title = FSMA_RULE_SEEDS[0]["title"]
    session = FakeSession(existing_titles={first_title})
    inserted = seed_rule_definitions(session)
    assert inserted == len(FSMA_RULE_SEEDS) - 1
    inserted_titles = {params["title"] for params in session.inserts}
    assert first_title not in inserted_titles


def test_seed_empty_seed_list_inserts_nothing(monkeypatch):
    monkeypatch.setattr(seeds_module, "FSMA_RULE_SEEDS", [])
    session = FakeSession()
    assert seed_rule_definitions(session) == 0
    assert session.inserts == []
    assert session.audits == []


def test_seed_db_error_propagates():
    session = FakeSession(fail_on="insert")
    with pytest.raises(RuntimeError, match="database unavailable"):
        seed_rule_definitions(session)
