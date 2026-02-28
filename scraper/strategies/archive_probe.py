"""Archive and legacy section detection strategy."""

from __future__ import annotations

import asyncio
from typing import List, Dict, Any, Set
from datetime import datetime
from urllib.parse import urljoin

import aiohttp

from cendoj.scraper.strategies.base import DiscoveryStrategy, StrategyResult
from cendoj.utils.logger import get_logger


class ArchiveProbeStrategy(DiscoveryStrategy):
    """Detect and probe archive/legacy sections of the site."""

    name = "archive_probe"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._archive_config = getattr(self.config, 'archive_discovery_config', lambda: {})()
        self._session: aiohttp.ClientSession = None
        self._path_templates = self._archive_config.get('path_templates', [
            '/archivos/{year}',
            '/historico/{year}',
            '/legacy/{year}',
            '/old/{year}',
            '/archive/{year}',
        ])
        self._start_year = int(self._archive_config.get('start_year', 2000))
        self._max_probes = int(self._archive_config.get('max_probes', 500))
        self._include_patterns = [__import__('re').compile(p) for p in self._archive_config.get('include_patterns', [])]
        self._exclude_patterns = [__import__('re').compile(p) for p in self._archive_config.get('exclude_patterns', [])]

    @property
    def enabled(self) -> bool:
        return bool(self._archive_config.get('enabled', False))

    async def initialize(self):
        if not self.enabled or self._session:
            return
        timeout = aiohttp.ClientTimeout(total=self._archive_config.get('timeout_seconds', 30))
        self._session = aiohttp.ClientSession(timeout=timeout)

    async def discover(self) -> StrategyResult:
        result = StrategyResult(metadata={'strategy': self.name})
        if not self.enabled:
            return result

        sites = self.config.sites
        current_year = datetime.now().year
        
        for site in sites:
            if not site.get('enabled', True):
                continue
            base_url = (site.get('base_url') or '').rstrip('/')
            if not base_url:
                continue

            # Generate probe URLs from templates
            probe_urls = []
            for template in self._path_templates:
                for year in range(self._start_year, current_year + 1):
                    path = template.format(year=year)
                    url = urljoin(base_url + '/', path.lstrip('/'))
                    probe_urls.append(url)
                    if len(probe_urls) >= self._max_probes:
                        break
                if len(probe_urls) >= self._max_probes:
                    break

            # Probe each URL
            for url in probe_urls:
                try:
                    if self.rate_limiter:
                        await self.rate_limiter.wait()
                    
                    async with self._session.head(url, allow_redirects=True) as resp:
                        if resp.status == 200:
                            result.seed_urls.append(url)
                            self.logger.debug(f"Archive found: {url}")
                        elif resp.status == 301 or resp.status == 302:
                            # Redirect might indicate archive
                            result.seed_urls.append(url)
                            self.logger.debug(f"Archive redirect: {url} -> {resp.headers.get('Location')}")
                except Exception as exc:
                    self.logger.debug(f"Archive probe failed for {url}: {exc}")

        result.seed_urls = self._filter_urls(result.seed_urls)
        result.metadata['probes_total'] = len(result.seed_urls)
        return result

    async def cleanup(self):
        if self._session:
            await self._session.close()
            self._session = None

    def _filter_urls(self, urls: List[str]) -> List[str]:
        if not urls:
            return []
        filtered = []
        for url in sorted(set(urls)):
            if self._exclude_patterns and any(p.search(url) for p in self._exclude_patterns):
                continue
            if self._include_patterns and not any(p.search(url) for p in self._include_patterns):
                continue
            filtered.append(url)
        return filtered
