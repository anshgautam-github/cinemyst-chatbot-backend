import functools
import logging
import time
from typing import Any, Callable, TypeVar, cast

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def ttl_cache(ttl_seconds: int = 300) -> Callable[[F], F]:
    """
    An in-memory Time-To-Live (TTL) cache decorator.

    This caches the string results of identical tool calls for a specified duration.
    It's particularly useful for read-heavy operations like searching mentors or jobs,
    where multiple users might ask similar questions, or a single user might repeat
    a query within the same session.

    Args:
        ttl_seconds: How long to keep the cached result before expiring it.
                     Defaults to 300 seconds (5 minutes).
    """
    cache: dict[str, tuple[float, Any]] = {}

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Create a deterministic cache key from the arguments
            # e.g., "search_mentors_args:('Drama',)_kwargs:{'limit': 5}"
            key_parts = [func.__name__, "args:", str(args), "kwargs:", str(sorted(kwargs.items()))]
            key = "_".join(key_parts)

            now = time.time()

            # Check if the key exists and has not expired
            if key in cache:
                timestamp, result = cache[key]
                if now - timestamp < ttl_seconds:
                    logger.debug(f"Cache HIT for {func.__name__} (TTL: {ttl_seconds}s)")
                    return result
                else:
                    logger.debug(f"Cache EXPIRED for {func.__name__}")
                    # Delete the expired key to free memory
                    del cache[key]
            else:
                logger.debug(f"Cache MISS for {func.__name__}")

            # Call the actual function
            result = func(*args, **kwargs)

            # Store the result with the current timestamp
            cache[key] = (now, result)
            return result

        return cast(F, wrapper)

    return decorator
