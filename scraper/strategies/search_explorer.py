"""Search API explorer strategy."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

import aiohttp

from cendoj.scraper.strategies.base import DiscoveryStrategy, StrategyResult


class SearchExplorer(DiscoveryStrategy):
    """Exhaustively query the search API to collect PDF links beyond UI pagination."""

    name = "search_explorer"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._search_config = getattr(self.config, 'search_explorer_config', lambda: {})()
        self._session: Optional[aiohttp.ClientSession] = None
        self._max_results = int(self._search_config.get('max_results', 50000))
        self._max_per_request = int(self._search_config.get('max_per_request', 1000))
        self._include_patterns = [re.compile(p) for p in self._search_config.get('include_patterns', [])]
        self._exclude_patterns = [re.compile(p) for p in self._search_config.get('exclude_patterns', [])]

    @property
    def enabled(self) -> bool:
        return bool(self._search_config.get('enabled', False))

    async def initialize(self):
        if not self.enabled or self._session:
            return
        timeout = aiohttp.ClientTimeout(total=self._search_config.get('timeout_seconds', 60))
        self._session = aiohttp.ClientSession(timeout=timeout)

    async def discover(self) -> StrategyResult:
        result = StrategyResult(metadata={'strategy': self.name})
        if not self.enabled:
            return result

        sites = self.config.sites
        for site in sites:
            if not site.get('enabled', True):
                continue
            base_url = site.get('base_url', '').rstrip('/')
            api_url = site.get('api', {}).get('search_url')
            jurisdictions = site.get('api', {}).get('jurisdictions', [])
            if not api_url or not jurisdictions:
                continue

            site_seeds = await self._explore_site(base_url, api_url, jurisdictions)
            result.seed_urls.extend(site_seeds)
            if len(result.seed_urls) >= self._max_results:
                break

        result.seed_urls = self._filter_urls(result.seed_urls)[:self._max_results]
        result.metadata['total_seeds'] = len(result.seed_urls)
        return result

    async def cleanup(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def _explore_site(self, base_url: str, api_url: str, jurisdictions: List[str]) -> List[str]:
        seeds = []
        # Generate quarterly date ranges for the last 20 years (adjustable)
        start_year = datetime.now().year - 20
        quarters = []
        for year in range(start_year, datetime.now().year + 1):
            for month in (1, 4, 7, 10):
                start = datetime(year, month, 1)
                end = start + timedelta(days=89)
                quarters.append((start, end))

        for jurisdiction in jurisdictions:
            for start_dt, end_dt in quarters:
                payload = self._build_payload(jurisdiction, start_dt, end_dt)
                try:
                    html = await self._post(api_url, payload)
                    pdfs = self._parse_html_for_pdfs(html, base_url)
                    seeds.extend(pdfs)
                except Exception as exc:
                    self.logger.warning(f"SearchExplorer failed for {jurisdiction} {start_dt.date()}-{end_dt.date()}: {exc}")
                if len(seeds) >= self._max_results:
                    return seeds
        return seeds

    async def _post(self, url: str, payload: Dict[str, Any]) -> str:
        if self.rate_limiter:
            await self.rate_limiter.wait()
        if not self._session:
            await self.initialize()
        async with self._session.post(url, data=payload) as resp:
            resp.raise_for_status()
            return await resp.text()

    def _build_payload(self, jurisdiction: str, start: datetime, end: datetime) -> Dict[str, Any]:
        """Build form payload for search request."""
        # These field names are guesses; adapt to actual form
        return {
            'jurisdiction': jurisdiction,
            'startDate': start.strftime('%d/%m/%Y'),
            'endDate': end.strftime('%d/%m/%Y'),
            'max': self._max_per_request,
            'page': 1,
        }

    def _parse_html_for_pdfs(self, html: str, base_url: str) -> List[str]:
        """Extract PDF URLs from search results page."""
        # Primary: CSS-like anchor href ending .pdf
        pdf_urls = re.findall(r'https?://[^\s"\'<>]+\.pdf', html, re.IGNORECASE)
        # Then relative links: resolve against base_url
        relative = re.findall(r'href="([^"]+\.pdf)"', html, re.IGNORECASE)
        pdf_urls.extend(urljoin(base_url, rel) for rel in relative)
        # Deduplicate and filter
        unique = list(dict.fromkeys(pdf_urls))
        return self._filter_urls(unique)
