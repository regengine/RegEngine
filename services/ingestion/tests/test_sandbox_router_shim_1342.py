"""Unit tests for ``app.sandbox_router`` — issue #1342.

This module is a backward-compatibility shim: every symbol is
re-exported from the ``app.sandbox`` package after the original
``sandbox_router.py`` god-file was decomposed.

There's no business logic — but ``main.py`` still imports
``from app.sandbox_router import router as sandbox_router`` (line 229),
so any silent breakage of a re-export immediately breaks the FastAPI
app boot. These tests pin the public surface so that:

  - The shim re-export list and ``app.sandbox`` package don't drift
    apart (anyone who deletes a symbol from ``app.sandbox`` without
    pulling it from the shim will see this test fail rather than
    discovering it at runtime).
  - Each re-exported symbol is the *same object* the source module
    exposes — not a stale copy or a stub. Identity matters because
    test code (and the previous monolith's API) often does
    ``monkeypatch.setattr(sandbox_router, "...", ...)`` and expects
    the patch to land on the live object.
  - ``router`` is a FastAPI ``APIRouter`` instance with at least one
    route — guards against ``main.py``'s ``app.include_router(...)``
    silently mounting an empty router.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import APIRouter

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))


from app import sandbox_router as shim  # noqa: E402

# Force the submodules to load, then pull the module objects from
# sys.modules — the ``import x.y.z as _name`` form resolves via
# ``getattr(x.y, 'z')`` which, for packages that re-export a symbol
# of the same name as a submodule (``from .router import router``
# in ``app/sandbox/__init__.py``), binds the name to the *symbol*
# (APIRouter instance) instead of the submodule.
import app.sandbox.csv_parser  # noqa: E402,F401
import app.sandbox.evaluators  # noqa: E402,F401
import app.sandbox.models  # noqa: E402,F401
import app.sandbox.rate_limiting  # noqa: E402,F401
import app.sandbox.router  # noqa: E402,F401
import app.sandbox.rule_loader  # noqa: E402,F401
import app.sandbox.tracer  # noqa: E402,F401
import app.sandbox.validation  # noqa: E402,F401

_csv_parser = sys.modules["app.sandbox.csv_parser"]
_evaluators = sys.modules["app.sandbox.evaluators"]
_models = sys.modules["app.sandbox.models"]
_rate_limiting = sys.modules["app.sandbox.rate_limiting"]
_router_mod = sys.modules["app.sandbox.router"]
_rule_loader = sys.modules["app.sandbox.rule_loader"]
_tracer = sys.modules["app.sandbox.tracer"]
_validation = sys.modules["app.sandbox.validation"]


# ---------------------------------------------------------------------------
# Public surface — every documented re-export resolves
# ---------------------------------------------------------------------------


class TestPublicSurface:
    @pytest.mark.parametrize(
        "name",
        [
            # router.py
            "router",
            "sandbox_evaluate",
            "sandbox_trace",
            # tracer.py
            "_trace_in_memory",
            # csv_parser.py
            "_CSV_COLUMN_MAP",
            "_parse_csv_to_events",
            "_normalize_for_rules",
            # rate_limiting.py
            "_check_sandbox_rate_limit",
            # rule_loader.py
            "_build_rules_from_seeds",
            "_get_applicable_rules",
            "_SANDBOX_RULES",
            # evaluators.py
            "_evaluate_event_stateless",
            "_evaluate_relational_in_memory",
            # validation.py
            "_validate_kdes",
            "_detect_duplicate_lots",
            "_normalize_entity_name",
            "_detect_entity_mismatches",
            # models.py
            "SandboxEvent",
            "SandboxRequest",
            "RuleResultResponse",
            "EventEvaluationResponse",
            "SandboxResponse",
            "TraceDirection",
            "TraceNode",
            "TraceEdge",
            "TraceGraphResponse",
            "SandboxTraceRequest",
        ],
    )
    def test_symbol_present(self, name):
        assert hasattr(shim, name), (
            f"{name} missing from app.sandbox_router shim — "
            f"main.py + legacy callers expect this re-export."
        )


# ---------------------------------------------------------------------------
# Identity — re-exports are the live source objects
# ---------------------------------------------------------------------------


class TestReExportIdentity:
    """Re-exports must be the source object, not a copy.

    Tests + the legacy module API frequently do
    ``monkeypatch.setattr(sandbox_router, "_check_sandbox_rate_limit", ...)``
    expecting the patch to land where the route actually calls it.
    If a re-export is a stale copy or a wrapped version, the patch
    silently misses and the test gives a false positive.
    """

    def test_router_is_app_sandbox_router_router(self):
        assert shim.router is _router_mod.router

    def test_sandbox_evaluate_identity(self):
        assert shim.sandbox_evaluate is _router_mod.sandbox_evaluate

    def test_sandbox_trace_identity(self):
        assert shim.sandbox_trace is _router_mod.sandbox_trace

    def test_trace_in_memory_identity(self):
        assert shim._trace_in_memory is _tracer._trace_in_memory

    def test_csv_parser_reexports_identity(self):
        assert shim._CSV_COLUMN_MAP is _csv_parser._CSV_COLUMN_MAP
        assert shim._parse_csv_to_events is _csv_parser._parse_csv_to_events
        assert shim._normalize_for_rules is _csv_parser._normalize_for_rules

    def test_rate_limiting_identity(self):
        assert shim._check_sandbox_rate_limit is _rate_limiting._check_sandbox_rate_limit

    def test_rule_loader_identity(self):
        assert shim._build_rules_from_seeds is _rule_loader._build_rules_from_seeds
        assert shim._get_applicable_rules is _rule_loader._get_applicable_rules
        assert shim._SANDBOX_RULES is _rule_loader._SANDBOX_RULES

    def test_evaluators_identity(self):
        assert shim._evaluate_event_stateless is _evaluators._evaluate_event_stateless
        assert shim._evaluate_relational_in_memory is _evaluators._evaluate_relational_in_memory

    def test_validation_identity(self):
        assert shim._validate_kdes is _validation._validate_kdes
        assert shim._detect_duplicate_lots is _validation._detect_duplicate_lots
        assert shim._normalize_entity_name is _validation._normalize_entity_name
        assert shim._detect_entity_mismatches is _validation._detect_entity_mismatches

    def test_models_identity(self):
        for name in [
            "SandboxEvent", "SandboxRequest", "RuleResultResponse",
            "EventEvaluationResponse", "SandboxResponse", "TraceDirection",
            "TraceNode", "TraceEdge", "TraceGraphResponse", "SandboxTraceRequest",
        ]:
            assert getattr(shim, name) is getattr(_models, name), (
                f"{name} is not the same object on shim and source"
            )


# ---------------------------------------------------------------------------
# Router shape — guards against empty-router footgun
# ---------------------------------------------------------------------------


class TestRouterShape:
    def test_router_is_fastapi_apirouter(self):
        assert isinstance(shim.router, APIRouter)

    def test_router_has_at_least_one_route(self):
        # main.py does `app.include_router(sandbox_router, ...)` — if
        # the underlying router silently lost all its routes (e.g.
        # someone refactored router.py and forgot to register the
        # endpoints), the FastAPI app would boot with no /sandbox/*
        # endpoints and 404 every request. This catches that.
        assert len(shim.router.routes) > 0
