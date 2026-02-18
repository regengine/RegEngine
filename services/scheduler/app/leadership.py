from app.distributed import DistributedContext
import functools

# Global context for leadership checks
_dist_ctx = None

def get_distributed_context():
    global _dist_ctx
    if _dist_ctx is None:
        _dist_ctx = DistributedContext()
    return _dist_ctx

def is_leader():
    """Check if the current instance is the leader."""
    ctx = get_distributed_context()
    return ctx._is_leader
