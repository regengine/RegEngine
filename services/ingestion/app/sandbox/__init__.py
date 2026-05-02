"""
Sandbox Evaluation — modular package.

Split from the original monolithic sandbox_router.py (1,576 lines) into:
    sandbox/models.py        — Pydantic request/response models
    sandbox/rate_limiting.py — per-IP rate limiting
    sandbox/rule_loader.py   — build rules from FSMA_RULE_SEEDS
    sandbox/evaluators.py    — stateless + relational evaluators
    sandbox/csv_parser.py    — CSV column mapping + normalization
    sandbox/validation.py    — KDE validation, duplicate/entity detection
    sandbox/tracer.py        — in-memory BFS lot tracing
    sandbox/router.py        — FastAPI router + endpoints

All public names are re-exported here for backward compatibility:
    from app.sandbox import router
"""

from .router import router  # noqa: F401

# Re-export commonly imported internals for backward compatibility
from .tracer import _trace_in_memory  # noqa: F401
from .csv_parser import _parse_csv_to_events  # noqa: F401
from .models import (  # noqa: F401
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
from .validation import (  # noqa: F401
    _validate_kdes,
    _detect_duplicate_lots,
    _normalize_entity_name,
    _detect_entity_mismatches,
)
from .evaluators import (  # noqa: F401
    _evaluate_event_stateless,
    _evaluate_relational_in_memory,
)
from .csv_parser import (  # noqa: F401
    _CSV_COLUMN_MAP,
    _normalize_for_rules,
)
from .rate_limiting import _check_sandbox_rate_limit  # noqa: F401

__all__ = [
    "router",
    "_trace_in_memory",
    "_parse_csv_to_events",
    "_CSV_COLUMN_MAP",
    "_normalize_for_rules",
    "_validate_kdes",
    "_detect_duplicate_lots",
    "_normalize_entity_name",
    "_detect_entity_mismatches",
    "_evaluate_event_stateless",
    "_evaluate_relational_in_memory",
    "_check_sandbox_rate_limit",
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
]
