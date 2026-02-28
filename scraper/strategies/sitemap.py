"""Sitemap-based discovery strategy."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import List, Optional, Set

import aiohttp

from cendoj.scraper.strategies.base import DiscoveryStrategy, StrategyResult


class SitemapStrategy(DiscoveryStrategy):
    """Fetch and parse sitemap XML files to produce seed URLs."""

    name = "sitemap"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sitemap_config = getattr(self.config, 'sitemap_config', lambda: {})()
        self._session: Optional[aiohttp.ClientSession] = None
        self._max_depth = int(self._sitemap_config.get('max_depth', 3))
        self._max_urls = int(self._sitemap_config.get('max_urls', 5000))
        self._follow_indexes = self._sitemap_config.get('follow_sitemap_links', True)
        self._include_patterns = [re.compile(p) for p in self._sitemap_config.get('include_patterns', [])]
        self._exclude_patterns = [re.compile(p) for p in self._sitemap_config.get('exclude_patterns', [])]

    @property
    def enabled(self) -> bool:
        urls = self._sitemap_config.get('urls', [])
        return bool(self._sitemap_config.get('enabled', False) and urls)

    async def initialize(self):
        if not self.enabled or self._session:
            return
        timeout = aiohttp.ClientTimeout(total=self._sitemap_config.get('timeout_seconds', 30))
        self._session = aiohttp.ClientSession(timeout=timeout)

    async def discover(self) -> StrategyResult:
        result = StrategyResult(metadata={'strategy': self.name})
        if not self.enabled:
            return result

        urls = self._sitemap_config.get('urls', [])
        discovered: Set[str] = set()

        for sitemap_url in urls:
            try:
                entries = await self._parse_sitemap(sitemap_url, depth=0)
                discovered.update(entries)
            except Exception as exc:
                self.logger.warning(f"Sitemap parsing failed for {sitemap_url}: {exc}")

            if len(discovered) >= self._max_urls:
                break

        filtered = self._filter_urls(list(discovered))[: self._max_urls]
        result.seed_urls.extend(filtered)
        result.metadata['total_urls'] = len(discovered)
        result.metadata['filtered_urls'] = len(filtered)
        return result

    async def cleanup(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def _fetch_text(self, url: str) -> Optional[str]:
        if not self._session:
            await self.initialize()
        if not self._session:
            return None

        if self.rate_limiter:
            await self.rate_limiter.wait()

        async with self._session.get(url) as resp:
            if resp.status != 200:
                self.logger.warning(f"HTTP {resp.status} fetching sitemap {url}")
                return None
            return await resp.text()

    async def _parse_sitemap(self, sitemap_url: str, depth: int) -> List[str]:
        if depth > self._max_depth:
            return []

        body = await self._fetch_text(sitemap_url)
        if not body:
            return []

        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            self.logger.warning(f"Invalid sitemap XML ({sitemap_url}): {exc}")
            return []

        namespace = { 'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9' }
        tag = root.tag.lower()

        urls: List[str] = []
        if tag.endswith('sitemapindex'):
            if not self._follow_indexes:
                return []
            for child in root.findall('sm:sitemap', namespace):
                loc = child.find('sm:loc', namespace)
                if loc is not None and loc.text:
                    urls.extend(await self._parse_sitemap(loc.text.strip(), depth + 1))
        else:
            for child in root.findall('sm:url', namespace):
                loc = child.find('sm:loc', namespace)
                if loc is not None and loc.text:
                    urls.append(loc.text.strip())
        return urls

    def _filter_urls(self, urls: List[str]) -> List[str]:
        if not urls:
            return []

        def matches(patterns, value: str) -> bool:
            return any(p.search(value) for p in patterns)

        filtered = []
        for url in sorted(set(urls)):
            if self._exclude_patterns and matches(self._exclude_patterns, url):
                continue
            if self._include_patterns and not matches(self._include_patterns, url):
                continue
            filtered.append(url)
        return filtered
