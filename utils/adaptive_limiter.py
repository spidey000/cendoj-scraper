"""Adaptive rate limiter that adjusts based on server responses."""

import asyncio
import time
from collections import deque
from typing import Optional
from cendoj.utils.logger import get_logger

logger = get_logger(__name__)


class AdaptiveRateLimiter:
    """Token bucket rate limiter with adaptive behavior based on responses."""

    def __init__(
        self,
        requests_per_minute: int = 20,
        burst_size: int = 5,
        backoff_on_429: bool = True,
        max_backoff_seconds: int = 300,
        decrease_factor: float = 0.5
    ):
        """
        Initialize adaptive rate limiter.

        Args:
            requests_per_minute: Base rate limit
            burst_size: Max burst of requests allowed
            backoff_on_429: Reduce rate on 429 responses
            max_backoff_seconds: Max backoff time
            decrease_factor: Multiply rate by this on 429 (e.g., 0.5 = 50% reduction)
        """
        self.base_rate = requests_per_minute
        self.current_rate = float(requests_per_minute)
        self.burst_size = burst_size
        self.backoff_on_429 = backoff_on_429
        self.max_backoff = max_backoff_seconds
        self.decrease_factor = decrease_factor

        self.tokens = burst_size
        self.last_refill = time.time()
        self._lock = asyncio.Lock()
        self._waiters = deque()

        # Stats
        self.stats = {
            "total_requests": 0,
            "429_count": 0,
            "current_backoff": 0,
        }

    async def wait(self):
        """Wait for a token to become available."""
        async with self._lock:
            while True:
                self._refill()

                if self.tokens > 0:
                    self.tokens -= 1
                    self.stats["total_requests"] += 1
                    return

                # Calculate wait time
                now = time.time()
                tokens_needed = 1
                refill_rate = self.current_rate / 60.0  # tokens per second
                wait_time = tokens_needed / refill_rate if refilknowledge>0 else 1.0

                # Add jitter (±10%)
                wait_time += random.uniform(-0.1, 0.1) * wait_time
                wait_time = max(0.01, wait_time)

                self.logger.debug(f"Rate limit active, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)

    def _refill(self):
        """Refill tokens based on elapsed time and current rate."""
        now = time.time()
        elapsed = now - self.last_refill
        self.last_refill = now

        refill_rate = self.current_rate / 60.0  # tokens per second
        new_tokens = elapsed * refill_rate

        self.tokens = min(self.burst_size, self.tokens + new_tokens)

    def on_429(self):
        """
        Called when a 429 response is received.
        Reduces the rate limit adaptively.
        """
        if not self.backoff_on_429:
            return

        self.stats["429_count"] += 1
        old_rate = self.current_rate
        self.current_rate = max(1, self.current_rate * self.decrease_factor)

        # Calculate exponential backoff
        backoff_seconds = min(
            self.max_backoff,
            (self.stats["429_count"] ** 2) * 10  # 10s, 40s, 90s, 160s...
        )
        self.stats["current_backoff"] = backoff_seconds

        self.logger.warning(
            f"429 received: rate reduced from {old_rate:.1f} to {self.current_rate:.1f} req/min, "
            f"backoff {backoff_seconds}s"
        )

        # Temporarily reduce tokens to enforce backoff
        self.tokens = 0
        self.last_refill = time.time() - backoff_seconds

    def on_success(self):
        """Called when a request succeeds. Can gradually increase rate."""
        # Slowly recover from rate reduction (10% per successful request)
        if self.current_rate < self.base_rate:
            self.current_rate = min(
                self.base_rate,
                self.current_rate * 1.1
            )
            self.logger.info(f"Rate increased to {self.current_rate:.1f} req/min after success")

    def get_stats(self) -> dict:
        """Get current rate limiter statistics."""
        return {
            "current_rate_req_min": round(self.current_rate, 2),
            "base_rate_req_min": self.base_rate,
            "tokens_available": round(self.tokens, 2),
            "burst_size": self.burst_size,
            "total_requests": self.stats["total_requests"],
            "429_count": self.stats["429_count"],
            "current_backoff_seconds": self.stats["current_backoff"],
        }
