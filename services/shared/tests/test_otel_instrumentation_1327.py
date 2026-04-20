"""Smoke tests for OTel downstream instrumentation -- #1327.

Verifies that SQLAlchemyInstrumentor and HTTPXClientInstrumentor are called
during the shared observability setup functions.  These are pure unit tests:
no real OTel exporter, no database, no network.

Strategy
--------
We test ``_instrument_downstream_clients`` in isolation (verifying it calls
the two instrumentors), and separately verify that ``add_observability`` /
``setup_standalone_observability`` call ``_instrument_downstream_clients``
when OTel is enabled.  This avoids fighting the full SDK stub tree.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest


# ---------------------------------------------------------------------------
# Minimal stubs for opentelemetry packages (may not be installed in CI)
# ---------------------------------------------------------------------------

_STUB_NAMES = [
    "opentelemetry",
    "opentelemetry._logs",
    "opentelemetry.trace",
    "opentelemetry.baggage",
    "opentelemetry.instrumentation",
    "opentelemetry.instrumentation.fastapi",
    "opentelemetry.instrumentation.sqlalchemy",
    "opentelemetry.instrumentation.httpx",
    "opentelemetry.sdk",
    "opentelemetry.sdk.trace",
    "opentelemetry.sdk.trace.export",
    "opentelemetry.sdk.trace.sampling",
    "opentelemetry.sdk.resources",
    "opentelemetry.sdk._logs",
    "opentelemetry.sdk._logs.export",
    "opentelemetry.exporter",
    "opentelemetry.exporter.otlp",
    "opentelemetry.exporter.otlp.proto",
    "opentelemetry.exporter.otlp.proto.grpc",
    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
    "opentelemetry.exporter.otlp.proto.grpc._log_exporter",
]


def _ensure_stubs():
    for name in _STUB_NAMES:
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)

    root = sys.modules["opentelemetry"]
    root._logs = sys.modules["opentelemetry._logs"]
    root.trace = sys.modules["opentelemetry.trace"]
    root.baggage = sys.modules["opentelemetry.baggage"]

    tr = sys.modules["opentelemetry.trace"]
    if not hasattr(tr, "NoOpTracerProvider"):
        tr.NoOpTracerProvider = type("NoOpTracerProvider", (), {})
    if not hasattr(tr, "set_tracer_provider"):
        tr.set_tracer_provider = MagicMock()
    if not hasattr(tr, "get_tracer"):
        tr.get_tracer = MagicMock()

    logs = sys.modules["opentelemetry._logs"]
    if not hasattr(logs, "set_logger_provider"):
        logs.set_logger_provider = MagicMock()

    sdk_t = sys.modules["opentelemetry.sdk.trace"]
    if not hasattr(sdk_t, "TracerProvider"):
        sdk_t.TracerProvider = type("TracerProvider", (), {"__init__": lambda s, **kw: None,
                                                           "add_span_processor": lambda s, p: None,
                                                           "set_tracer_provider": lambda s: None})

    sdk_e = sys.modules["opentelemetry.sdk.trace.export"]
    if not hasattr(sdk_e, "BatchSpanProcessor"):
        sdk_e.BatchSpanProcessor = type("BatchSpanProcessor", (), {"__init__": lambda s, e: None})

    sdk_s = sys.modules["opentelemetry.sdk.trace.sampling"]
    if not hasattr(sdk_s, "TraceIdRatioBased"):
        sdk_s.TraceIdRatioBased = type("TraceIdRatioBased", (), {"__init__": lambda s, r: None})

    sdk_r = sys.modules["opentelemetry.sdk.resources"]
    if not hasattr(sdk_r, "Resource"):
        _res = MagicMock()
        _res.create = staticmethod(lambda attrs: MagicMock())
        sdk_r.Resource = _res

    sdk_l = sys.modules["opentelemetry.sdk._logs"]
    if not hasattr(sdk_l, "LoggerProvider"):
        sdk_l.LoggerProvider = type("LoggerProvider", (), {"__init__": lambda s, **kw: None,
                                                           "add_log_record_processor": lambda s, p: None})
    if not hasattr(sdk_l, "LoggingHandler"):
        sdk_l.LoggingHandler = type("LoggingHandler", (), {})

    sdk_le = sys.modules["opentelemetry.sdk._logs.export"]
    if not hasattr(sdk_le, "BatchLogRecordProcessor"):
        sdk_le.BatchLogRecordProcessor = type("BatchLogRecordProcessor", (), {"__init__": lambda s, e: None})

    grpc_t = sys.modules["opentelemetry.exporter.otlp.proto.grpc.trace_exporter"]
    if not hasattr(grpc_t, "OTLPSpanExporter"):
        grpc_t.OTLPSpanExporter = type("OTLPSpanExporter", (), {"__init__": lambda s, endpoint=None: None})

    grpc_l = sys.modules["opentelemetry.exporter.otlp.proto.grpc._log_exporter"]
    if not hasattr(grpc_l, "OTLPLogExporter"):
        grpc_l.OTLPLogExporter = type("OTLPLogExporter", (), {"__init__": lambda s, endpoint=None: None})

    fi = sys.modules["opentelemetry.instrumentation.fastapi"]
    if not hasattr(fi, "FastAPIInstrumentor"):
        _fa = MagicMock()
        _fa.instrument_app = MagicMock()
        fi.FastAPIInstrumentor = _fa

    sa = sys.modules["opentelemetry.instrumentation.sqlalchemy"]
    if not hasattr(sa, "SQLAlchemyInstrumentor"):
        sa.SQLAlchemyInstrumentor = MagicMock

    hx = sys.modules["opentelemetry.instrumentation.httpx"]
    if not hasattr(hx, "HTTPXClientInstrumentor"):
        hx.HTTPXClientInstrumentor = MagicMock


_ensure_stubs()


# ---------------------------------------------------------------------------
# Load the module under test
# ---------------------------------------------------------------------------

_OTEL_PATH = Path(__file__).parent.parent / "observability" / "otel.py"


def _load_fresh_otel_module() -> types.ModuleType:
    """Load otel.py fresh, removing any cached version first."""
    mod_name = "shared.observability.otel_test_fresh"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    for pkg in ("shared", "shared.observability"):
        sys.modules.setdefault(pkg, types.ModuleType(pkg))
    spec = importlib.util.spec_from_file_location(mod_name, _OTEL_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _enable_otel(monkeypatch):
    monkeypatch.setenv("ENABLE_OTEL", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")


# ---------------------------------------------------------------------------
# Unit tests for _instrument_downstream_clients directly
# ---------------------------------------------------------------------------

class TestInstrumentDownstreamClients:
    def test_sqlalchemy_instrument_called(self):
        otel_mod = _load_fresh_otel_module()
        mock_sa = MagicMock()
        mock_hx = MagicMock()
        otel_mod.SQLAlchemyInstrumentor = MagicMock(return_value=mock_sa)
        otel_mod.HTTPXClientInstrumentor = MagicMock(return_value=mock_hx)

        otel_mod._instrument_downstream_clients()

        mock_sa.instrument.assert_called_once()

    def test_httpx_instrument_called(self):
        otel_mod = _load_fresh_otel_module()
        mock_sa = MagicMock()
        mock_hx = MagicMock()
        otel_mod.SQLAlchemyInstrumentor = MagicMock(return_value=mock_sa)
        otel_mod.HTTPXClientInstrumentor = MagicMock(return_value=mock_hx)

        otel_mod._instrument_downstream_clients()

        mock_hx.instrument.assert_called_once()

    def test_sqlalchemy_failure_does_not_stop_httpx(self):
        """Exception in SQLAlchemy instrumentation must not prevent httpx."""
        otel_mod = _load_fresh_otel_module()
        mock_sa = MagicMock()
        mock_sa.instrument.side_effect = RuntimeError("boom")
        mock_hx = MagicMock()
        otel_mod.SQLAlchemyInstrumentor = MagicMock(return_value=mock_sa)
        otel_mod.HTTPXClientInstrumentor = MagicMock(return_value=mock_hx)

        otel_mod._instrument_downstream_clients()  # should not raise

        mock_hx.instrument.assert_called_once()


# ---------------------------------------------------------------------------
# Integration: add_observability calls _instrument_downstream_clients
# ---------------------------------------------------------------------------

class TestAddObservabilityCallsInstrumentation:
    def test_downstream_instrumented_when_otel_enabled(self, monkeypatch):
        _enable_otel(monkeypatch)
        otel_mod = _load_fresh_otel_module()

        called = []
        otel_mod._instrument_downstream_clients = lambda: called.append(True)

        from fastapi import FastAPI
        otel_mod.add_observability(FastAPI(), "svc")

        assert called, "_instrument_downstream_clients was not called"

    def test_downstream_not_instrumented_when_otel_disabled(self, monkeypatch):
        monkeypatch.setenv("ENABLE_OTEL", "false")
        otel_mod = _load_fresh_otel_module()

        called = []
        otel_mod._instrument_downstream_clients = lambda: called.append(True)

        from fastapi import FastAPI
        otel_mod.add_observability(FastAPI(), "svc")

        assert not called, "_instrument_downstream_clients must not be called when OTel is off"


# ---------------------------------------------------------------------------
# Integration: setup_standalone_observability calls _instrument_downstream_clients
# ---------------------------------------------------------------------------

class TestStandaloneObservabilityCallsInstrumentation:
    def test_downstream_instrumented_when_otel_enabled(self, monkeypatch):
        _enable_otel(monkeypatch)
        otel_mod = _load_fresh_otel_module()

        called = []
        otel_mod._instrument_downstream_clients = lambda: called.append(True)

        otel_mod.setup_standalone_observability("worker")

        assert called, "_instrument_downstream_clients was not called"

    def test_downstream_not_instrumented_when_otel_disabled(self, monkeypatch):
        monkeypatch.setenv("ENABLE_OTEL", "false")
        otel_mod = _load_fresh_otel_module()

        called = []
        otel_mod._instrument_downstream_clients = lambda: called.append(True)

        otel_mod.setup_standalone_observability("worker")

        assert not called
