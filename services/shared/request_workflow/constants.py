"""Constants for the FDA 24-Hour Request-Response Workflow."""

WORKFLOW_STAGES = [
    "intake",
    "scoping",
    "collecting",
    "gap_analysis",
    "exception_triage",
    "assembling",
    "internal_review",
    "ready",
    "submitted",
    "amended",
]

VALID_SIGNOFF_TYPES = [
    "scope_approval",
    "package_review",
    "final_approval",
    "submission_authorization",
]

VALID_SCOPE_TYPES = [
    "tlc_trace",
    "product_recall",
    "facility_audit",
    "date_range",
    "custom",
]

# Signoff types REQUIRED before a case can reach "submitted" status.
REQUIRED_SIGNOFF_TYPES = {"scope_approval", "final_approval"}

VALID_SUBMISSION_TYPES = ["initial", "amendment", "supplement", "correction"]
VALID_SUBMISSION_METHODS = ["export", "email", "portal", "mail", "other"]
VALID_REQUEST_CHANNELS = ["email", "phone", "portal", "letter", "drill", "other"]

DEFAULT_RESPONSE_HOURS = 24
