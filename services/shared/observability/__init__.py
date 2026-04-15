"""Observability package — consolidates OTel, logging, metrics, health, and correlation.

Re-exports the public API from the original shared.observability module so that
``from shared.observability import add_observability`` continues to work.
"""

from shared.observability.otel import (  # noqa: F401
    add_observability,
    get_shared_resource,
    setup_standalone_observability,
)
