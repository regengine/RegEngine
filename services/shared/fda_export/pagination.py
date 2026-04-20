"""Streaming pagination for FDA / FSMA-204 exports.

Before EPIC-L, both service exports loaded the full result set into
memory and silently truncated at a hard cap (10k events in ingestion,
50k in compliance). A truncated export to an FDA auditor is
indistinguishable from a complete one — which is the worst possible
failure mode for a compliance product.

This module provides :func:`paginate`, an async generator that yields
events in batches of ``batch_size`` (default 500) until the caller's
fetcher signals ``has_more=False``. The caller decides what to do with
each batch (stream to CSV writer, accumulate for hashing, etc.).

Fetcher contract::

    async def fetcher(*, cursor: str | None, limit: int) -> tuple[list, str | None]:
        ...
        return (events, next_cursor_or_None)

Related issue: EPIC-L (#1655).
"""
from __future__ import annotations

from typing import AsyncIterator, Awaitable, Callable, Optional, TypeVar

T = TypeVar("T")

# Default batch size — matches the graph service's internal cap.
DEFAULT_BATCH_SIZE = 500


async def paginate(
    fetcher: Callable[..., Awaitable[tuple[list[T], Optional[str]]]],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_events: Optional[int] = None,
) -> AsyncIterator[list[T]]:
    """Yield batches of events until the fetcher is drained.

    Parameters
    ----------
    fetcher:
        Async callable accepting ``cursor`` and ``limit`` keyword
        arguments, returning ``(batch, next_cursor)``. A ``None``
        cursor signals "end of result set".
    batch_size:
        Hint passed through as ``limit`` — the fetcher may choose to
        honor a smaller batch but must never return more.
    max_events:
        Hard cap across all yielded batches. When set, the generator
        raises ``ValueError`` rather than silently truncating — the
        caller must either widen the cap or narrow the query.

    Yields
    ------
    list[T]
        Each non-empty batch. Empty batches are *not* yielded; the
        iteration ends instead.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    cursor: Optional[str] = None
    total = 0
    while True:
        batch, next_cursor = await fetcher(cursor=cursor, limit=batch_size)
        if not batch:
            return
        total += len(batch)
        if max_events is not None and total > max_events:
            raise ValueError(
                f"export exceeded the {max_events:,}-event hard cap — "
                "narrow the query or request an async batched job"
            )
        yield batch
        if not next_cursor:
            return
        cursor = next_cursor


__all__ = ["DEFAULT_BATCH_SIZE", "paginate"]
