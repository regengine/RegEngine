"""Phase 2b: FSMA-204 golden-corpus structural verification (#2924).

History
-------
This module used to hold two empty function bodies. ``test_obligation_mapping_logic``
was a docstring plus a bare ``pass`` with no marker at all, so it contributed a
green PASS to every run and to the collected-test floor that CI reads as
evidence the suite is intact. ``test_ingestion_pipeline_correctness`` was a
``pass  # TODO`` behind ``skipif(not DOCKER_RUNNING)`` — it asserted nothing
even when the Docker stack was up. A compliance platform's data-integrity
directory advertised golden-corpus verification of the FSMA-204 obligation
mapping and delivered nothing.

What the golden corpus actually is
----------------------------------
The FSMA-204 "golden standard" in this repo is a pair of Alembic SQL files
that a live revision ``op.execute``s, so a fresh ``alembic upgrade head``
depends on them:

* ``alembic/sql/V036__fsma_204_regulatory_seed_data.sql`` seeds the
  ``obligations`` rows (the regulatory requirements themselves).
* ``alembic/sql/V037__obligation_cte_rules.sql`` maps each obligation to a
  CTE type and the Key Data Element that satisfies it — the
  extracted-fact-to-obligation mapping this module's class docstring
  advertises.

The consumer is ``_check_obligations`` in
``services/ingestion/app/webhook_router_v2/validation.py``. For every ingested
CTE event it selects the rules whose ``cte_type`` matches the event (or
``'all'``), joins them to ``obligations``, and evaluates the rule's
``validation_rule`` against the event's KDEs.

Both tests below assert couplings that are load-bearing for that flow and
that fail *silently* when broken — an obligation whose row is missing, or
whose ``validation_rule`` the consumer does not implement, does not raise:
it is quietly treated as satisfied. That is the same false-assurance defect
class these tests themselves used to be.

Everything here is parsed from committed files plus one in-process import.
No Docker, no database, no network — so this module runs in the ordinary
offline suite rather than skipping.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Mirror tests/data_integrity/test_fsma_204_verification_phase2b.py — this
# package has no conftest of its own.
for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "services")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_SEED_SQL = _REPO_ROOT / "alembic" / "sql" / "V036__fsma_204_regulatory_seed_data.sql"
_RULES_SQL = _REPO_ROOT / "alembic" / "sql" / "V037__obligation_cte_rules.sql"
_CONSUMER_PY = _REPO_ROOT / "services" / "ingestion" / "app" / "webhook_router_v2" / "validation.py"

# ``cte_type`` values in the rules table that are not CTE events at all:
# ``all`` fans out to every event, ``record_maintenance`` covers record-level
# duties (translations, 24-hour FDA production) with no ingest event to hang
# off. Both are declared in V037's own CHECK constraint.
_NON_EVENT_CTE_TYPES = frozenset({"all", "record_maintenance"})

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"


# ---------------------------------------------------------------------------
# Corpus parsing helpers
# ---------------------------------------------------------------------------


def _split_sql_values(values: str) -> list[str]:
    """Split a SQL VALUES tuple body on top-level commas, honouring quotes."""
    parts: list[str] = []
    current = ""
    in_quote = False
    i = 0
    while i < len(values):
        ch = values[i]
        if ch == "'":
            if in_quote and i + 1 < len(values) and values[i + 1] == "'":
                current += "''"
                i += 2
                continue
            in_quote = not in_quote
            current += ch
        elif ch == "," and not in_quote:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
        i += 1
    parts.append(current.strip())
    return parts


def _unquote(field: str) -> str | None:
    field = field.strip()
    if field.upper() == "NULL":
        return None
    if field.startswith("'") and field.endswith("'"):
        return field[1:-1].replace("''", "'")
    return field


def _read(path: Path) -> str:
    assert path.is_file(), (
        f"golden corpus file is missing: {path.relative_to(_REPO_ROOT)}. "
        "A fresh `alembic upgrade head` op.executes this file — losing it "
        "silently drops the FSMA-204 obligation mapping."
    )
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def obligation_rules() -> list[dict]:
    """Every row seeded into ``obligation_cte_rules`` by V037."""
    text = _read(_RULES_SQL)
    rows = re.findall(
        r"INSERT\s+INTO\s+obligation_cte_rules\s*\([^)]*\)\s*VALUES\s*\((.*?)\);",
        text,
        re.S | re.I,
    )
    assert rows, "V037 seeded no obligation_cte_rules — the mapping corpus is empty"
    parsed = []
    for raw in rows:
        fields = _split_sql_values(raw)
        assert len(fields) == 6, f"unexpected obligation_cte_rules arity {len(fields)}: {raw[:120]}"
        parsed.append(
            {
                "id": _unquote(fields[0]),
                "obligation_id": _unquote(fields[1]),
                "cte_type": _unquote(fields[2]),
                "required_kde_key": _unquote(fields[3]),
                "validation_rule": _unquote(fields[4]),
                "description": _unquote(fields[5]),
            }
        )
    return parsed


@pytest.fixture(scope="module")
def seeded_obligation_ids() -> set[str]:
    """Every ``obligations.id`` seeded by V036."""
    text = _read(_SEED_SQL)
    ids = set(re.findall(rf"INSERT\s+INTO\s+obligations\s*\([^)]*\)\s*VALUES\s*\('({_UUID})'", text, re.S | re.I))
    assert ids, "V036 seeded no obligations — the golden corpus is empty"
    return ids


def _check_constraint_values(text: str, constraint: str) -> set[str]:
    """Pull the IN (...) literal set out of a named CHECK constraint."""
    match = re.search(
        re.escape(constraint) + r"[\s\S]{0,400}?IN\s*\(([^)]*)\)",
        text,
        re.I,
    )
    assert match, f"could not locate CHECK constraint {constraint!r}"
    return set(re.findall(r"'([^']+)'", match.group(1)))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFSMA204GoldenCorpus:
    """
    Phase 2b: Golden Corpus Verification.

    Verifies the committed FSMA-204 golden corpus (V036 obligations + V037
    obligation-to-CTE rules) against the ingestion pipeline that consumes it:

    1. Every mapping rule resolves to a seeded obligation, and every seeded
       obligation is mapped (nothing unenforceable, nothing dangling).
    2. Every ``validation_rule`` in the corpus is one the ingest-time checker
       actually implements.
    3. The corpus's CTE-type vocabulary matches, in both directions, the CTE
       types the ingestion pipeline accepts and the database will store.
    """

    def test_ingestion_pipeline_correctness(self, obligation_rules):
        """The corpus's CTE vocabulary matches the ingestion pipeline's, both ways.

        ``_check_obligations`` selects rules with
        ``WHERE r.cte_type IN (:cte_type, 'all')`` using ``event.cte_type.value``
        straight off the validated ``IngestEvent``. So the two vocabularies are
        a live coupling:

        * A CTE type the webhook accepts but the corpus never mentions is
          ingested with **zero** obligation evaluation — a silently unpoliced
          event type.
        * A ``cte_type`` in the corpus that no ingest event can carry is a dead
          rule: an FSMA-204 obligation that can never be evaluated.

        Neither shows up as an error at runtime; both just quietly check
        nothing. This is also the invariant the previous ``pass``-bodied,
        Docker-gated stub claimed to cover.
        """
        from services.ingestion.app.webhook_models import WebhookCTEType

        # GROWING is documented in WebhookCTEType as legacy/internal — "not an
        # FDA-defined CTE", it normalises to farm metadata. It is the one
        # accepted value with no CTE obligations, so it is excluded explicitly
        # rather than by letting the assertion be one-directional.
        pipeline_cte_types = {m.value for m in WebhookCTEType} - {WebhookCTEType.GROWING.value}
        assert pipeline_cte_types, "WebhookCTEType exposes no FDA-defined CTE types"

        corpus_cte_types = {r["cte_type"] for r in obligation_rules}
        corpus_event_types = corpus_cte_types - _NON_EVENT_CTE_TYPES

        unpoliced = sorted(pipeline_cte_types - corpus_event_types)
        assert not unpoliced, (
            f"CTE types the webhook accepts but the golden corpus has no obligation rule for: "
            f"{unpoliced}. Events of these types are ingested with no obligation check at all."
        )

        dead_rules = sorted(corpus_event_types - pipeline_cte_types)
        assert not dead_rules, (
            f"golden-corpus cte_type values no IngestEvent can carry: {dead_rules}. "
            f"_check_obligations matches on event.cte_type.value, so these rules never fire."
        )

        # The database side must accept the same set: V037 rewrites the
        # fsma.cte_events event_type CHECK in the same migration that seeds the
        # rules, so a divergence here means a rule matches an event the table
        # will reject on insert.
        rules_text = _read(_RULES_SQL)
        storable = _check_constraint_values(rules_text, "cte_events_event_type_check")
        assert corpus_event_types == storable, (
            "golden-corpus CTE types and fsma.cte_events.event_type disagree: "
            f"corpus-only={sorted(corpus_event_types - storable)}, "
            f"table-only={sorted(storable - corpus_event_types)}"
        )

        # And every cte_type seeded must satisfy V037's own CHECK constraint,
        # or the migration aborts partway through on a fresh database.
        allowed = _check_constraint_values(rules_text, "obligation_cte_rules_cte_type_check")
        illegal = sorted(corpus_cte_types - allowed)
        assert not illegal, f"seeded cte_type values rejected by V037's own CHECK constraint: {illegal}"

    def test_obligation_mapping_logic(self, obligation_rules, seeded_obligation_ids):
        """Extracted facts map to real, evaluable Compliance Obligations.

        Three couplings, each of which fails silently rather than loudly:

        1. ``obligation_cte_rules.obligation_id`` is a FK to ``obligations.id``.
           A rule pointing at an unseeded obligation aborts the migration on a
           fresh database; on an existing one the ``JOIN obligations`` in
           ``_check_obligations`` simply drops the rule, so the obligation is
           never checked and nothing reports an error.
        2. An obligation with no rule is unreachable from the ingest path — a
           regulatory requirement in the corpus that no event can ever be
           measured against.
        3. ``_check_obligations`` dispatches on ``validation_rule`` through an
           if/elif chain with no else. A ``validation_rule`` the consumer does
           not implement leaves ``passed = True``: the obligation reports as
           met without anything having been evaluated.
        """
        rule_obligation_ids = {r["obligation_id"] for r in obligation_rules}

        dangling = sorted(rule_obligation_ids - seeded_obligation_ids)
        assert not dangling, (
            f"{len(dangling)} obligation_cte_rules row(s) reference obligations V036 never seeds: "
            f"{dangling[:5]}. The FK aborts a fresh migration; on a live DB the "
            f"JOIN in _check_obligations silently drops the rule."
        )

        unmapped = sorted(seeded_obligation_ids - rule_obligation_ids)
        assert not unmapped, (
            f"{len(unmapped)} seeded FSMA-204 obligation(s) have no obligation_cte_rules row: "
            f"{unmapped[:5]}. _check_obligations can never evaluate them."
        )

        # Every rule must carry a validation_rule at all.
        ruleless = [r["id"] for r in obligation_rules if not r["validation_rule"]]
        assert not ruleless, f"obligation_cte_rules rows with no validation_rule: {ruleless[:5]}"

        implemented = _implemented_validation_rules()
        assert implemented, (
            f"parsed no validation_rule branches out of {_CONSUMER_PY.relative_to(_REPO_ROOT)} — "
            "the consumer moved; this assertion must be repointed, not deleted."
        )

        corpus_rules = {r["validation_rule"] for r in obligation_rules}
        unimplemented = sorted(corpus_rules - implemented)
        assert not unimplemented, (
            f"golden-corpus validation_rule value(s) with no branch in _check_obligations: "
            f"{unimplemented}. Those obligations fall through the if/elif chain with "
            f"passed=True — reported as satisfied without being evaluated. "
            f"Implemented branches: {sorted(implemented)}"
        )


def _implemented_validation_rules() -> set[str]:
    """String literals ``_check_obligations`` compares ``validation_rule`` against.

    Read via ``ast`` from the consumer's source rather than by importing it:
    the set of branches is a source-level fact, and parsing keeps this module
    collectable without the ingestion router's runtime dependencies.
    """
    source = _read(_CONSUMER_PY)
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        left = node.left
        if not (isinstance(left, ast.Name) and left.id == "validation_rule"):
            continue
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, (ast.Eq, ast.In)) and isinstance(comparator, ast.Constant):
                if isinstance(comparator.value, str):
                    found.add(comparator.value)
            elif isinstance(op, ast.In) and isinstance(comparator, (ast.Tuple, ast.List, ast.Set)):
                for elt in comparator.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        found.add(elt.value)
    return found
