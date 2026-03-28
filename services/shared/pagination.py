"""Shared pagination utility for FastAPI list endpoints.

Provides a reusable dependency for pagination query parameters and a generic
paginated response model.  Import ``PaginationParams`` as a FastAPI ``Depends``
and ``PaginatedResponse`` as a generic response wrapper.

Usage::

    from shared.pagination import PaginationParams, PaginatedResponse

    @router.get("/items", response_model=PaginatedResponse[ItemSchema])
    async def list_items(pagination: PaginationParams = Depends()):
        query = select(Item).offset(pagination.skip).limit(pagination.limit)
        ...
        return PaginatedResponse(items=items, total=total,
                                  skip=pagination.skip, limit=pagination.limit)
"""

from __future__ import annotations

from typing import Generic, List, TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")


class PaginationParams:
    """FastAPI dependency for pagination query parameters."""

    def __init__(
        self,
        skip: int = Query(default=0, ge=0, description="Number of records to skip"),
        limit: int = Query(default=50, ge=1, le=500, description="Max records to return"),
    ):
        self.skip = skip
        self.limit = limit


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response envelope."""

    items: List[T]
    total: int
    skip: int
    limit: int
