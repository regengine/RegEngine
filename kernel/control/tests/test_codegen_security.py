"""
Security + correctness tests for ``kernel.control.codegen``.

Covers two P0 audit findings:

* **#1275** — ``generate_fastapi_routes()`` crashes at format time with
  ``NameError`` because the ``{evidence_contract_placeholder}`` slot is never
  bound. These tests assert the function returns valid, parseable source
  for a minimal input and that the generated module contains an
  ``EVIDENCE_CONTRACT`` literal.

* **#1285** — Vertical metadata values are interpolated directly into
  generated Python with no escaping. These tests feed the generator
  adversarial inputs (inputs that would produce RCE-capable source under
  the old implementation) and assert :class:`CodegenValidationError` is
  raised **before** any emission occurs.

These tests are deliberately framework-free: the codegen stack is currently
orphaned (no app imports ``kernel.control``) so we only need ``ast`` and
``pytest``. The tests are the canary for anyone who later wires the
compiler into the monolith.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import List

import pytest

from kernel.control.codegen import (
    CodegenValidationError,
    generate_fastapi_routes,
    generate_pydantic_models,
    generate_test_scaffolds,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_meta(
    *,
    name: str = "finance",
    decision_types: List[str] | None = None,
    regulators: List[str] | None = None,
    regulatory_domains: List[str] | None = None,
    evidence_contract: dict | None = None,
) -> SimpleNamespace:
    if decision_types is None:
        decision_types = ["credit_denial"]
    if regulators is None:
        regulators = ["CFPB"]
    if regulatory_domains is None:
        regulatory_domains = ["ECOA"]
    if evidence_contract is None:
        evidence_contract = {
            "credit_denial": {
                "required": [
                    "adverse_action_notice",
                    "reason_codes",
                ]
            }
        }
    return SimpleNamespace(
        name=name,
        decision_types=decision_types,
        regulators=regulators,
        regulatory_domains=regulatory_domains,
        evidence_contract=evidence_contract,
    )


def _make_obligation(
    *,
    oid: str = "TEST_OBLIGATION_ONE",
    citation: str = "12 CFR 1002.9",
) -> SimpleNamespace:
    return SimpleNamespace(id=oid, citation=citation)


# ---------------------------------------------------------------------------
# #1275 — NameError regression
# ---------------------------------------------------------------------------


class TestCodegenDoesNotCrashOnCannedInput:
    """#1275 — ``generate_fastapi_routes`` must not raise NameError."""

    def test_routes_returns_string(self):
        """Smoke test: a minimal vertical produces a non-empty string."""
        meta = _make_meta()
        result = generate_fastapi_routes(meta, [_make_obligation()])
        assert isinstance(result, str)
        assert len(result) > 0

    def test_routes_are_valid_python(self):
        """The generated file must be parseable Python (catches #1275 + #1295)."""
        meta = _make_meta()
        source = generate_fastapi_routes(meta, [_make_obligation()])
        # If this raises SyntaxError the whole generator is broken.
        ast.parse(source)

    def test_routes_contain_evidence_contract_literal(self):
        """The ``{evidence_contract_placeholder}`` slot must be filled with a
        real ``EVIDENCE_CONTRACT = {...}`` literal."""
        meta = _make_meta()
        source = generate_fastapi_routes(meta, [_make_obligation()])
        assert "EVIDENCE_CONTRACT =" in source
        assert "{evidence_contract_placeholder}" not in source

    def test_routes_import_datetime(self):
        """#1295 — routes reference ``datetime.utcnow()`` so the import is mandatory."""
        meta = _make_meta()
        source = generate_fastapi_routes(meta, [_make_obligation()])
        assert "from datetime import datetime" in source

    def test_models_returns_string(self):
        meta = _make_meta()
        result = generate_pydantic_models(meta, [_make_obligation()])
        assert isinstance(result, str)
        ast.parse(result)

    def test_models_and_routes_decision_response_fields_align(self):
        """#1295 — ``DecisionResponse`` construction in routes must reference
        fields that exist on the generated model.
        """
        meta = _make_meta()
        routes = generate_fastapi_routes(meta, [_make_obligation()])
        models = generate_pydantic_models(meta, [_make_obligation()])

        # Route constructs these kwargs on DecisionResponse.
        for field in ("envelope_id", "obligations_evaluated", "obligations_met"):
            assert f"{field}=" in routes, f"route must pass {field}"
            assert f"{field}:" in models, f"model must declare {field}"


# ---------------------------------------------------------------------------
# #1285 — RCE via unvalidated template interpolation
# ---------------------------------------------------------------------------


class TestCodegenRejectsInjectionInVerticalName:
    """#1285 — ``vertical_meta.name`` must not flow unchecked into source."""

    def test_rejects_double_quote(self):
        meta = _make_meta(name='finance"\nimport os\nos.system("pwn")\n#')
        with pytest.raises(CodegenValidationError):
            generate_fastapi_routes(meta, [_make_obligation()])

    def test_rejects_newline(self):
        meta = _make_meta(name="finance\nprint(42)")
        with pytest.raises(CodegenValidationError):
            generate_fastapi_routes(meta, [_make_obligation()])

    def test_rejects_hyphen(self):
        meta = _make_meta(name="finance-eu")
        with pytest.raises(CodegenValidationError):
            generate_fastapi_routes(meta, [_make_obligation()])

    def test_rejects_uppercase(self):
        meta = _make_meta(name="Finance")
        with pytest.raises(CodegenValidationError):
            generate_fastapi_routes(meta, [_make_obligation()])

    def test_accepts_plain_identifier(self):
        meta = _make_meta(name="food_beverage")
        result = generate_fastapi_routes(meta, [_make_obligation()])
        assert "food_beverage" in result


class TestCodegenRejectsInjectionInDecisionTypes:
    """#1285 — ``decision_types`` items flow into enum members and template
    body; must be pure identifiers."""

    def test_rejects_quote_in_decision_type(self):
        meta = _make_meta(
            decision_types=['credit_denial"\nimport os\n#']
        )
        with pytest.raises(CodegenValidationError):
            generate_fastapi_routes(meta, [_make_obligation()])

    def test_rejects_quote_in_decision_type_for_models(self):
        meta = _make_meta(
            decision_types=['credit_denial"\nimport os\n#']
        )
        with pytest.raises(CodegenValidationError):
            generate_pydantic_models(meta, [_make_obligation()])

    def test_rejects_hyphen_in_decision_type(self):
        meta = _make_meta(decision_types=["credit-denial"])
        with pytest.raises(CodegenValidationError):
            generate_fastapi_routes(meta, [_make_obligation()])

    def test_rejects_backtick_in_decision_type(self):
        meta = _make_meta(decision_types=["credit_denial`ls`"])
        with pytest.raises(CodegenValidationError):
            generate_fastapi_routes(meta, [_make_obligation()])

    def test_rejects_empty_decision_types(self):
        meta = _make_meta(decision_types=[])
        with pytest.raises(CodegenValidationError):
            generate_fastapi_routes(meta, [_make_obligation()])


class TestCodegenRejectsInjectionInObligations:
    """#1285 — obligation ``id`` / ``citation`` flow into codegen; must be
    allow-listed."""

    def test_rejects_injection_in_obligation_citation(self):
        bad = _make_obligation(
            citation='12 CFR 1002.9"\nimport os\nos.system("pwn")\n#'
        )
        with pytest.raises(CodegenValidationError):
            generate_fastapi_routes(_make_meta(), [bad])

    def test_rejects_lowercase_obligation_id(self):
        bad = _make_obligation(oid="lower_case_id")
        with pytest.raises(CodegenValidationError):
            generate_fastapi_routes(_make_meta(), [bad])

    def test_accepts_normal_obligation(self):
        good = _make_obligation(oid="FSMA_204_CTE", citation="21 CFR 1.1320")
        source = generate_fastapi_routes(_make_meta(), [good])
        ast.parse(source)


class TestCodegenRejectsInjectionInEvidenceContract:
    """#1285 — ``evidence_contract`` keys & values flow through ``repr`` but
    the keys also appear in the EVIDENCE_CONTRACT literal. Both sides must
    be identifier-safe."""

    def test_rejects_evil_evidence_contract_key(self):
        bad = {
            'credit_denial"\nimport os; os.system("pwn")\n#"': {
                "required": ["field_a"]
            }
        }
        meta = _make_meta(evidence_contract=bad)
        with pytest.raises(CodegenValidationError):
            generate_fastapi_routes(meta, [_make_obligation()])

    def test_rejects_evil_evidence_contract_value(self):
        bad = {
            "credit_denial": {
                "required": ['field_a"\nimport os\n#']
            }
        }
        meta = _make_meta(evidence_contract=bad)
        with pytest.raises(CodegenValidationError):
            generate_fastapi_routes(meta, [_make_obligation()])

    def test_emits_evidence_contract_as_repr_not_template(self):
        """Defence in depth: the emitted contract is a Python literal the
        parser frames itself, not a template-substituted blob."""
        contract = {
            "credit_denial": {
                "required": ["adverse_action_notice", "reason_codes"]
            }
        }
        meta = _make_meta(evidence_contract=contract)
        source = generate_fastapi_routes(meta, [_make_obligation()])

        # The literal should parse as a dict when we extract it.
        # We find the line that starts the assignment.
        marker = "EVIDENCE_CONTRACT = "
        assert marker in source
        start = source.index(marker) + len(marker)
        end = source.index("\n", start)
        literal = source[start:end]
        # Evaluating a ``repr(dict)`` output is safe via ast.literal_eval.
        parsed = ast.literal_eval(literal)
        assert parsed == {"credit_denial": ["adverse_action_notice", "reason_codes"]}


class TestCodegenRejectsInjectionInRegulators:
    def test_rejects_regulator_with_injection(self):
        meta = _make_meta(regulators=['OCC"\nimport os\n#'])
        with pytest.raises(CodegenValidationError):
            generate_fastapi_routes(meta, [_make_obligation()])

    def test_rejects_domain_with_injection(self):
        meta = _make_meta(regulatory_domains=['ECOA"; import os\n#'])
        with pytest.raises(CodegenValidationError):
            generate_fastapi_routes(meta, [_make_obligation()])


class TestTestScaffoldsAreAlsoProtected:
    """The scaffolding generator also interpolates ``decision_types``; must
    follow the same allowlist discipline."""

    def test_scaffolds_reject_injection(self, tmp_path: Path):
        meta = _make_meta(decision_types=['credit_denial"\nimport os\n#'])
        with pytest.raises(CodegenValidationError):
            generate_test_scaffolds(meta, [_make_obligation()], tmp_path)

    def test_scaffolds_emit_valid_python(self, tmp_path: Path):
        meta = _make_meta()
        files = generate_test_scaffolds(meta, [_make_obligation()], tmp_path)
        assert len(files) == 2
        for f in files:
            source = f.read_text(encoding="utf-8")
            ast.parse(source)


# ---------------------------------------------------------------------------
# Belt-and-braces: adversarial source never reaches AST with exec semantics
# ---------------------------------------------------------------------------


class TestSiblingGeneratorsAreParseable:
    """graph_adapter + snapshot_adapter_generator had indentation bugs in
    their emitted source (#1295-style). Regression guard: every generator
    in ``kernel/control/`` must produce Python that parses."""

    def _meta_for_siblings(self) -> SimpleNamespace:
        return SimpleNamespace(
            name="finance",
            decision_types=["credit_denial"],
            regulators=["FDA"],
            regulatory_domains=["FSMA"],
            scoring_weights={
                "bias": 0.25,
                "drift": 0.25,
                "documentation": 0.25,
                "regulatory_mapping": 0.25,
            },
        )

    def test_graph_nodes_parses(self):
        from kernel.control.graph_adapter import generate_graph_nodes

        source = generate_graph_nodes(self._meta_for_siblings(), [])
        ast.parse(source)

    def test_graph_relationships_parses(self):
        from kernel.control.graph_adapter import generate_graph_relationships

        source = generate_graph_relationships(self._meta_for_siblings(), [])
        ast.parse(source)

    def test_snapshot_adapter_parses(self):
        from kernel.control.snapshot_adapter_generator import (
            generate_snapshot_adapter,
        )

        source = generate_snapshot_adapter(self._meta_for_siblings(), [])
        ast.parse(source)


class TestCodegenOutputContainsNoUserInjection:
    """Even on the *accepting* path, no user-supplied string should appear
    unquoted in the emitted source at a position that would execute it."""

    def test_no_top_level_os_import_leaks(self):
        """Classic canary: if user input had ``import os`` it must not land
        in the output regardless of the rejection path."""
        # We go through the allowlist-accepted path only, to make sure that
        # input that contains the literal substring "os" elsewhere (e.g. an
        # evidence field named ``os_version`` — not valid, but inside a dict
        # value not a code slot) cannot leak.
        meta = _make_meta(
            name="finance",
            decision_types=["credit_denial"],
            evidence_contract={
                "credit_denial": {"required": ["os_version_hash"]}
            },
        )
        source = generate_fastapi_routes(meta, [_make_obligation()])
        # ``import os`` should never appear in our template; evidence field
        # names land inside a ``repr`` dict literal, not a raw statement.
        assert "\nimport os" not in source
        assert "os.system(" not in source
