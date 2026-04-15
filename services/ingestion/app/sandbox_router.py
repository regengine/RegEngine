"""
Backward-compatibility shim — all code has moved to app.sandbox package.

Existing imports like ``from app.sandbox_router import router`` continue
to work. New code should import from ``app.sandbox`` directly.

Package layout:
    app/sandbox/models.py        — Pydantic request/response models
    app/sandbox/rate_limiting.py — per-IP rate limiting
    app/sandbox/rule_loader.py   — build rules from FSMA_RULE_SEEDS
    app/sandbox/evaluators.py    — stateless + relational evaluators
    app/sandbox/csv_parser.py    — CSV column mapping + normalization
    app/sandbox/validation.py    — KDE validation, duplicate/entity detection
    app/sandbox/tracer.py        — in-memory BFS lot tracing
    app/sandbox/router.py        — FastAPI router + endpoints
"""

# Re-export everything so existing callers don't break
from app.sandbox.router import router  # noqa: F401
from app.sandbox.router import sandbox_evaluate  # noqa: F401
from app.sandbox.router import sandbox_trace  # noqa: F401
from app.sandbox.tracer import _trace_in_memory  # noqa: F401
from app.sandbox.csv_parser import (  # noqa: F401
    _CSV_COLUMN_MAP,
    _parse_csv_to_events,
    _normalize_for_rules,
)
from app.sandbox.rate_limiting import _check_sandbox_rate_limit  # noqa: F401
from app.sandbox.rule_loader import (  # noqa: F401
    _build_rules_from_seeds,
    _get_applicable_rules,
    _SANDBOX_RULES,
)
from app.sandbox.evaluators import (  # noqa: F401
    _evaluate_event_stateless,
    _evaluate_relational_in_memory,
)
from app.sandbox.validation import (  # noqa: F401
    _validate_kdes,
    _detect_duplicate_lots,
    _normalize_entity_name,
    _detect_entity_mismatches,
)
from app.sandbox.models import (  # noqa: F401
    SandboxEvent,
    SandboxRequest,
    RuleResultResponse,
    EventEvaluationResponse,
    SandboxResponse,
    TraceDirection,
    TraceNode,
    TraceEdge,
    TraceGraphResponse,
    SandboxTraceRequest,
)
