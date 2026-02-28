"""Taxonomy and collection enumeration strategy."""

from __future__ import annotations

import re
from typing import List, Dict, Any, Set
from urllib.parse import urljoin

from cendoj.scraper.strategies.base import DiscoveryStrategy, StrategyResult
from cendoj.utils.logger import get_logger


class TaxonomyStrategy(DiscoveryStrategy):
    """Traverse navigation structures to enumerate every collection/section."""

    name = "taxonomy"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tax_config = getattr(self.config, 'taxonomy_config', lambda: {})()
        self._max_pages_per_site = int(self._tax_config.get('max_pages_per_site', 100))
        self._selectors = self._tax_config.get('selectors', [
            'nav a', '.menu a', '.sidebar a', '.navigation a', '.nav-menu a',
            '[role="navigation"] a', '.breadcrumb a'
        ])
        self._include_patterns = [re.compile(p) for p in self._tax_config.get('include_patterns', [])]
        self._exclude_patterns = [re.compile(p) for p in self._tax_config.get('exclude_patterns', [])]

    @property
    def enabled(self) -> bool:
        # Requires browser manager
        if not self.browser_manager:
            return False
        return bool(self._tax_config.get('enabled', False))

    async def initialize(self):
        pass

    async def discover(self) -> StrategyResult:
        result = StrategyResult(metadata={'strategy': self.name})
        if not self.enabled:
            return result

        sites = self.config.sites
        all_seeds: Set[str] = set()

        for site in sites:
            if not site.get('enabled', True):
                continue
            base_url = (site.get('base_url') or '').rstrip('/')
            if not base_url:
                continue

            site_seeds = await self._crawl_site_navigation(base_url)
            all_seeds.update(site_seeds)
            if len(all_seeds) >= self._max_pages_per_site * len(sites):
                break

        filtered = self._filter_urls(list(all_seeds))
        result.seed_urls.extend(filtered)
        result.metadata['total_seeds'] = len(filtered)
        return result

    async def cleanup(self):
        pass

    async def _crawl_site_navigation(self, base_url: str) -> Set[str]:
        """Open base URL, extract navigation links, then optionally follow to next pages."""
        seeds: Set[str] = set()
        if not self.browser_manager:
            return seeds

        page = await self.browser_manager.new_page()
        try:
            await page.goto(base_url, timeout=60000)
            # Extract initial navigation links
            links = await self._extract_links(page, base_url)
            seeds.update(links)

            # Optionally follow a limited BFS on navigation pages only (depth=1)
            # We'll visit each navigation link and gather its links as well
            nav_pages = list(links)[:20]  # cap to avoid explosion
            for nav_url in nav_pages:
                try:
                    await page.goto(nav_url, timeout=60000)
                    nested = await self._extract_links(page, base_url)
                    seeds.update(nested)
                except Exception as exc:
                    self.logger.debug(f"Failed to navigate to {nav_url}: {exc}")
        finally:
            await page.close()

        return seeds

    async def _extract_links(self, page, base_url: str) -> Set[str]:
        """Use Playrino locator to grab all <a> elements matching selectors."""
        links: Set[str] = set()
        for selector in self._selectors:
            try:
                elements = await page.query_selector_all(selector)
                for el in elements:
                    href = await el.get_attribute('href')
                    if href:
                        full = urljoin(base_url, href.strip())
                        if self._passes_filters(full):
                            links.add(full)
            except Exception:
                continue
        return links

    def _passes_filters(self, url: str) -> bool:
        if self._exclude_patterns and any(p.search(url) for p in self._exclude_patterns):
            return False
        if self._include_patterns and not any(p.search(url) for p in self._include_patterns):
            return False
        return True

    def _filter_urls(self, urls: List[str]) -> List[str]:
        uniq = list(dict.fromkeys(urls))
        return uniq
