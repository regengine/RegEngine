"""Retry utilities for resilient service connections."""

from __future__ import annotations

import time
from functools import wraps
from typing import Callable, TypeVar, Any

import structlog

log = structlog.get_logger("retry")

T = TypeVar("T")


def with_retry(
    max_attempts: int = 5,
    delay_seconds: float = 2.0,
    backoff_multiplier: float = 1.5,
    exceptions: tuple = (Exception,),
) -> Callable:
    """
    Decorator for retrying failed operations with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay_seconds: Initial delay between retries
        backoff_multiplier: Multiplier for exponential backoff
        exceptions: Tuple of exception types to catch and retry
    
    Example:
        @with_retry(max_attempts=3, delay_seconds=1.0)
        def connect_to_database():
            return Database.connect()
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_error: Exception | None = None
            current_delay = delay_seconds
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_error = e
                    log.warning(
                        "operation_retry",
                        function=func.__name__,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        delay=current_delay,
                        error=str(e),
                    )
                    if attempt < max_attempts:
                        time.sleep(current_delay)
                        current_delay *= backoff_multiplier
            
            log.error(
                "operation_failed_after_retries",
                function=func.__name__,
                max_attempts=max_attempts,
                error=str(last_error),
            )
            raise last_error  # type: ignore
        
        return wrapper
    return decorator


async def with_async_retry(
    max_attempts: int = 5,
    delay_seconds: float = 2.0,
    backoff_multiplier: float = 1.5,
    exceptions: tuple = (Exception,),
) -> Callable:
    """Async version of retry decorator."""
    import asyncio
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_error: Exception | None = None
            current_delay = delay_seconds
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_error = e
                    log.warning(
                        "async_operation_retry",
                        function=func.__name__,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        delay=current_delay,
                        error=str(e),
                    )
                    if attempt < max_attempts:
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff_multiplier
            
            log.error(
                "async_operation_failed_after_retries",
                function=func.__name__,
                max_attempts=max_attempts,
                error=str(last_error),
            )
            raise last_error  # type: ignore
        
        return wrapper
    return decorator
