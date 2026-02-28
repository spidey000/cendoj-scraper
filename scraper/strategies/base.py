"""Base discovery strategy interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from cendoj.utils.logger import get_logger


@dataclass
class StrategyResult:
    """Container for discovery outputs produced by a strategy."""

    seed_urls: List[str] = field(default_factory=list)
    pdf_links: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class DiscoveryStrategy(ABC):
    """Abstract base class for discovery strategies."""

    name: str = "base"

    def __init__(
        self,
        config,
        browser_manager=None,
        rate_limiter=None,
        proxy_manager=None,
        ua_pool=None,
    ):
        self.config = config
        self.browser_manager = browser_manager
        self.rate_limiter = rate_limiter
        self.proxy_manager = proxy_manager
        self.ua_pool = ua_pool
        self.logger = get_logger(f"{self.__class__.__name__}")

    @property
    def enabled(self) -> bool:
        """Whether the strategy should run."""
        return True

    async def initialize(self):
        """Optional async initialization before running."""

    @abstractmethod
    async def discover(self) -> StrategyResult:
        """Execute discovery and return structured results."""

    async def cleanup(self):
        """Optional cleanup hook."""

