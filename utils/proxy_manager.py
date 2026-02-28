"""Proxy management system with auto-refresh and scoring."""

import asyncio
import aiohttp
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from urllib.parse import urlparse
import random
from cendoj.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ProxyRecord:
    """Individual proxy with metadata and health tracking."""
    proxy_url: str  # Format: "http://ip:port" or "socks5://ip:port"
    source: str
    protocol: str  # http, https, socks4, socks5
    ip: str
    port: int
    country: Optional[str] = None
    anonymity: Optional[str] = None  # elite, anonymous, transparent
    https: bool = False
    score: float = 50.0  # 0-100 score
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time: Optional[float] = None
    last_used: Optional[datetime] = None
    last_success: Optional[datetime] = None
    last_error: Optional[datetime] = None
    last_error_msg: Optional[str] = None
    is_healthy: bool = True
    last_check: Optional[datetime] = None

    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests

    def update_score(self):
        """Update score based on performance metrics."""
        # Base score components
        success_weight = self.success_rate() * 50
        response_weight = 0
        if self.avg_response_time:
            # Faster is better: 0-2s = 25 points, 2-5s = 15 points, >5s = 5 points
            if self.avg_response_time <= 2.0:
                response_weight = 25
            elif self.avg_response_time <= 5.0:
                response_weight = 15
            else:
                response_weight = 5

        # Bonus for recent success (within last hour)
        recency_weight = 0
        if self.last_success:
            hours_ago = (datetime.utcnow() - self.last_success).total_seconds() / 3600
            if hours_ago < 1:
                recency_weight = 15
            elif hours_ago < 6:
                recency_weight = 10

        # Penalty for recent failure
        failure_penalty = 0
        if self.last_error:
            hours_ago = (datetime.utcnow() - self.last_error).total_seconds() / 3600
            if hours_ago < 1:
                failure_penalty = 20
            elif hours_ago < 6:
                failure_penalty = 10

        self.score = max(0, min(100, success_weight + response_weight + recency_weight - failure_penalty))


class ProxyManager:
    """Manages proxy pool: fetching, validation, scoring, rotation."""

    # Public proxy sources (free, no auth required)
    PROXY_SOURCES = {
        "proxifly": "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/all/data.txt",
        "proxyscraper": "https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/http.txt",
        # Alternative sources (can be enabled)
        # "free-proxy": "https://raw.githubusercontent.com/dpangestuw/Free-Proxy/master/proxy-list.txt",
    }

    def __init__(self, config: dict, cache_file: str = "data/proxies_cache.json"):
        """
        Initialize ProxyManager.

        Args:
            config: Configuration dict with proxy settings
            cache_file: Path to cache proxy pool state
        """
        self.config = config
        self.cache_file = Path(cache_file)
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        self.proxies: List[ProxyRecord] = []
        self._round_robin_index = 0
        self.logger = get_logger(__name__)

        # Stats
        self.stats = {
            "total_fetched": 0,
            "total_validated": 0,
            "currently_healthy": 0,
            "last_refresh": None,
        }

    async def initialize(self) -> List[ProxyRecord]:
        """Initialize proxy pool: load cache or fetch fresh."""
        # Try to load from cache first
        if self.cache_file.exists():
            try:
                cached = self._load_cache()
                if cached and len(cached) >= self.config.get("min_proxies_required", 100):
                    self.proxies = cached
                    self.logger.info(f"Loaded {len(self.proxies)} proxies from cache")
                    return self.proxies
            except Exception as e:
                self.logger.warning(f"Failed to load cache: {e}")

        # Fetch fresh proxies
        self.logger.info("Fetching fresh proxy pool...")
        await self.refresh_pool()
        return self.proxies

    def _load_cache(self) -> List[ProxyRecord]:
        """Load proxies from cache file."""
        with open(self.cache_file, 'r') as f:
            data = json.load(f)
        proxies = []
        for item in data.get('proxies', []):
            # Convert datetime strings back to datetime objects
            for field in ['last_used', 'last_success', 'last_error', 'last_check']:
                if item.get(field):
                    item[field] = datetime.fromisoformat(item[field])
            proxies.append(ProxyRecord(**item))
        return proxies

    def _save_cache(self):
        """Save current proxy pool to cache."""
        data = {
            'proxies': [],
            'stats': self.stats,
            'saved_at': datetime.utcnow().isoformat()
        }
        for proxy in self.proxies:
            p_dict = asdict(proxy)
            # Convert datetime to ISO strings
            for field in ['last_used', 'last_success', 'last_error', 'last_check']:
                if p_dict.get(field):
                    p_dict[field] = p_dict[field].isoformat()
            data['proxies'].append(p_dict)

        with open(self.cache_file, 'w') as f:
            json.dump(data, f, indent=2)

    async def refresh_pool(self):
        """Fetch proxies from all sources and validate."""
        all_proxies = await self._fetch_all_sources()
        self.stats["total_fetched"] += len(all_proxies)
        self.logger.info(f"Fetched {len(all_proxies)} proxies from sources")

        # Validate proxies
        validated = await self._validate_proxies(all_proxies)
        self.stats["total_validated"] = len(validated)

        # Merge with existing pool (avoid duplicates)
        existing_urls = {p.proxy_url for p in self.proxies}
        new_proxies = [p for p in validated if p.proxy_url not in existing_urls]
        self.proxies.extend(new_proxies)

        # Update scores for all
        for proxy in self.proxies:
            proxy.update_score()

        # Sort by score (highest first)
        self.proxies.sort(key=lambda p: p.score, reverse=True)

        # Prune very unhealthy proxies
        self.proxies = [p for p in self.proxies if p.score >= 10]

        self.stats["currently_healthy"] = len([p for p in self.proxies if p.is_healthy])
        self.stats["last_refresh"] = datetime.utcnow().isoformat()
        self._save_cache()

        self.logger.info(
            f"Proxy pool refreshed: {len(self.proxies)} total, "
            f"{self.stats['currently_healthy']} healthy"
        )

    async def _fetch_all_sources(self) -> List[ProxyRecord]:
        """Fetch proxies from all configured sources in parallel."""
        tasks = []
        async with aiohttp.ClientSession() as session:
            for source_name, url in self.PROXY_SOURCES.items():
                tasks.append(self._fetch_source(source_name, url, session))
            results = await asyncio.gather(*tasks, return_exceptions=True)

        all_proxies = []
        for result in results:
            if isinstance(result, Exception):
                self.logger.warning(f"Proxy fetch error: {result}")
                continue
            all_proxies.extend(result)

        return all_proxies

    async def _fetch_source(self, source_name: str, url: str, session: aiohttp.ClientSession) -> List[ProxyRecord]:
        """Fetch and parse proxies from a single source."""
        proxies = []
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    self.logger.warning(f"Source {source_name} returned status {resp.status}")
                    return []

                content = await resp.text()
                lines = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('#')]

                for line in lines[:1000]:  # Limit per source
                    try:
                        # Parse: ip:port or protocol://ip:port
                        if '://' in line:
                            parsed = urlparse(line)
                            protocol = parsed.scheme
                            ip = parsed.hostname
                            port = parsed.port
                        else:
                            parts = line.split(':')
                            if len(parts) != 2:
                                continue
                            ip, port_str = parts
                            port = int(port_str)
                            protocol = 'http'  # default

                        if not ip or not port:
                            continue

                        proxy = ProxyRecord(
                            proxy_url=f"{protocol}://{ip}:{port}",
                            source=source_name,
                            protocol=protocol,
                            ip=ip,
                            port=port,
                            country=None,
                            anonymity=None,
                            https=(protocol in ['https', 'socks5']),
                            last_check=datetime.utcnow()
                        )
                        proxies.append(proxy)
                    except Exception as e:
                        self.logger.debug(f"Failed to parse proxy line '{line}': {e}")
                        continue

        except Exception as e:
            self.logger.error(f"Error fetching from {source_name}: {e}")
            raise

        self.logger.debug(f"Fetched {len(proxies)} proxies from {source_name}")
        return proxies

    async def _validate_proxies(self, proxies: List[ProxyRecord], max_concurrent: int = 100) -> List[ProxyRecord]:
        """Validate a batch of proxies concurrently."""
        validated = []
        semaphore = asyncio.Semaphore(max_concurrent)

        # Test URL (httpbin.org/ip returns client IP)
        test_url = "http://httpbin.org/ip"
        timeout = aiohttp.ClientTimeout(total=10)

        async def test_proxy(proxy: ProxyRecord):
            async with semaphore:
                try:
                    proxy_url = proxy.proxy_url
                    start = time.time()

                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get(test_url, proxy=proxy_url) as resp:
                            elapsed = time.time() - start
                            if resp.status == 200:
                                proxy.successful_requests += 1
                                proxy.total_requests += 1
                                proxy.last_success = datetime.utcnow()
                                proxy.avg_response_time = elapsed if proxy.avg_response_time is None else \
                                    (proxy.avg_response_time * 0.7 + elapsed * 0.3)
                                proxy.is_healthy = True
                                validated.append(proxy)
                            else:
                                proxy.failed_requests += 1
                                proxy.total_requests += 1
                                proxy.last_error = datetime.utcnow()
                                proxy.last_error_msg = f"HTTP {resp.status}"
                except Exception as e:
                    proxy.failed_requests += 1
                    proxy.total_requests += 1
                    proxy.last_error = datetime.utcnow()
                    proxy.last_error_msg = str(e)
                    proxy.is_healthy = False

        # Run validation tasks
        await asyncio.gather(*[test_proxy(p) for p in proxies], return_exceptions=False)

        self.logger.info(f"Validated {len(validated)}/{len(proxies)} proxies")
        return validated

    def get_next_proxy(self, strategy: str = "weighted") -> Optional[ProxyRecord]:
        """
        Get next proxy according to strategy.

        Args:
            strategy: "weighted", "round_robin", "random", "best"
        """
        if not self.proxies:
            self.logger.error("Proxy pool is empty!")
            return None

        healthy = [p for p in self.proxies if p.is_healthy and p.score >= 30]
        if not healthy:
            self.logger.warning("No healthy proxies available, using any proxy")
            healthy = self.proxies

        if strategy == "weighted":
            # Weighted random by score
            weights = [max(1, p.score) for p in healthy]
            chosen = random.choices(healthy, weights=weights, k=1)[0]
        elif strategy == "round_robin":
            chosen = healthy[self._round_robin_index % len(healthy)]
            self._round_robin_index += 1
        elif strategy == "random":
            chosen = random.choice(healthy)
        elif strategy == "best":
            chosen = healthy[0]  # Already sorted by score
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

        # Update usage stats
        chosen.last_used = datetime.utcnow()
        return chosen

    def mark_result(self, proxy: ProxyRecord, success: bool, response_time: Optional[float] = None, error: Optional[str] = None):
        """
        Mark a proxy usage result.

        Args:
            proxy: The proxy used
            success: Whether the request succeeded
            response_time: Time in seconds (if success)
            error: Error message (if failure)
        """
        proxy.total_requests += 1
        if success:
            proxy.successful_requests += 1
            proxy.last_success = datetime.utcnow()
            if response_time:
                if proxy.avg_response_time is None:
                    proxy.avg_response_time = response_time
                else:
                    # Rolling average
                    proxy.avg_response_time = proxy.avg_response_time * 0.8 + response_time * 0.2
        else:
            proxy.failed_requests += 1
            proxy.last_error = datetime.utcnow()
            proxy.last_error_msg = error

        # Recalculate score
        proxy.update_score()

        # Auto-prune if score too low
        if proxy.score < 10:
            proxy.is_healthy = False
            if proxy in self.proxies:
                self.proxies.remove(proxy)
                self.logger.debug(f"Proxy {proxy.proxy_url} removed due to low score")

        # Periodic cache save
        if proxy.total_requests % 10 == 0:
            self._save_cache()

    def has_enough_proxies(self, min_count: int = 100, min_score: float = 30) -> bool:
        """Check if proxy pool has enough healthy proxies."""
        healthy = [p for p in self.proxies if p.is_healthy and p.score >= min_score]
        return len(healthy) >= min_count

    def get_stats(self) -> Dict:
        """Get statistics about proxy pool."""
        total = len(self.proxies)
        healthy = len([p for p in self.proxies if p.is_healthy])
        high_score = len([p for p in self.proxies if p.score >= 70])
        countries = defaultdict(int)
        for p in self.proxies:
            if p.country:
                countries[p.country] += 1

        return {
            "total_proxies": total,
            "healthy_proxies": healthy,
            "high_score_proxies": high_score,
            "countries": dict(countries),
            "last_refresh": self.stats.get("last_refresh"),
            "total_fetched": self.stats.get("total_fetched", 0),
        }
