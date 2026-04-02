"""FDA 24-Hour Request-Response Workflow — package entry point.

Backward-compatible: ``from shared.request_workflow import RequestWorkflow``
still works exactly as before.
"""

from .constants import (
    DEFAULT_RESPONSE_HOURS,
    REQUIRED_SIGNOFF_TYPES,
    VALID_REQUEST_CHANNELS,
    VALID_SCOPE_TYPES,
    VALID_SIGNOFF_TYPES,
    VALID_SUBMISSION_METHODS,
    VALID_SUBMISSION_TYPES,
    WORKFLOW_STAGES,
)
from .workflow import RequestWorkflow

__all__ = [
    "RequestWorkflow",
    "WORKFLOW_STAGES",
    "VALID_SIGNOFF_TYPES",
    "VALID_SCOPE_TYPES",
    "REQUIRED_SIGNOFF_TYPES",
    "VALID_SUBMISSION_TYPES",
    "VALID_SUBMISSION_METHODS",
    "VALID_REQUEST_CHANNELS",
    "DEFAULT_RESPONSE_HOURS",
]
