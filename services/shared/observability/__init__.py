"""Observability package — consolidates OTel, logging, metrics, health, and correlation.

Re-exports the public API from the original shared.observability module so that
``from shared.observability import add_observability`` continues to work.
"""

from shared.observability.correlation import (  # noqa: F401
    CORRELATION_ID_HEADER,
    CorrelationIdMiddleware,
    correlation_id_ctx,
    generate_correlation_id,
    get_correlation_id,
    set_correlation_id,
)
from shared.observability.context import (  # noqa: F401
    make_job_context_wrapper,
    spawn_tracked,
    wrap_job_with_new_correlation,
)
from shared.observability.fastapi_metrics import install_metrics  # noqa: F401
from shared.observability.otel import (  # noqa: F401
    add_observability,
    get_shared_resource,
    setup_standalone_observability,
)
