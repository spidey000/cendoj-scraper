"""Rate limiting and retry logic."""

import asyncio
import time
from functools import wraps
from typing import Callable, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from ..utils.logger import get_logger

logger = get_logger(__name__)

class RateLimiter:
    """Simple rate limiter for async operations."""

    def __init__(self, rate: float = 1.0):
        """
        Initialize rate limiter.

        Args:
            rate: Minimum seconds between operations
        """
        self.rate = rate
        self.last_call = 0
        self._lock = asyncio.Lock()

    async def wait(self):
        """Wait until enough time has passed since last call."""
        async with self._lock:
            now = time.time()
            time_since_last = now - self.last_call
            if time_since_last < self.rate:
                await asyncio.sleep(self.rate - time_since_last)
            self.last_call = time.time()

def rate_limited(rate: float = 1.0):
    """Decorator for rate limiting async functions."""
    def decorator(func: Callable) -> Callable:
        limiter = RateLimiter(rate)

        @wraps(func)
        async def wrapper(*args, **kwargs):
            await limiter.wait()
            return await func(*args, **kwargs)

        return wrapper
    return decorator

def retry_on_failure(max_attempts: int = 3, wait_min: int = 1, wait_max: int = 10):
    """Decorator for retrying on network failures."""
    def should_retry(exception):
        """Retry on network-related exceptions."""
        return isinstance(exception, (IOError, OSError, ConnectionError))

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
            retry=retry_if_exception(should_retry)
        )
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        return wrapper
    return decorator