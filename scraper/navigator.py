"""Navigator module for discovering court sentences across configured sites."""

import asyncio
import logging
from typing import Optional, List, AsyncIterator
from datetime import datetime

from .models import Sentence, Collection
from .browser import BrowserManager
from config.settings import Config
from utils.logger import get_logger
from utils.rate_limiter import RateLimiter
from utils.proxy_manager import ProxyManager
from utils.ua_pool import UserAgentPool
from utils.captcha_handler import CAPTCHAHandler


class Navigator:
    """Navigates configured sites to discover and extract sentence information."""

    def __init__(
        self,
        config: Config,
        browser_manager: Optional[BrowserManager] = None,
        proxy_manager: Optional[ProxyManager] = None,
        ua_pool: Optional[UserAgentPool] = None,
        captcha_handler: Optional[CAPTCHAHandler] = None
    ):
        """
        Initialize Navigator.

        Args:
            config: Configuration object containing site definitions
            browser_manager: Optional pre-configured BrowserManager instance
            proxy_manager: Optional ProxyManager for rotation
            ua_pool: Optional UserAgentPool for rotation
            captcha_handler: Optional CAPTCHAHandler
        """
        self.config = config
        self.browser_manager = browser_manager or BrowserManager(config.browser)
        self.proxy_manager = proxy_manager
        self.ua_pool = ua_pool
        self.captcha_handler = captcha_handler
        self.logger = get_logger(__name__, config.logging.file)
        self.rate_limiter = RateLimiter(
            requests_per_minute=config.rate_limit.requests_per_minute,
            burst=config.rate_limit.burst
        )

    async def discover_sentences(self, site_override: Optional[str] = None) -> AsyncIterator[Sentence]:
        """
        Discover sentences across all configured sites or a specific site.

        Args:
            site_override: Optional site key to limit discovery to one site

        Yields:
            Sentence objects as they are discovered
        """
        sites = [s for s in self.config.sites if site_override is None or s.key == site_override]

        for site in sites:
            try:
                self.logger.info(f"Starting discovery for site: {site.key}")
                async for sentence in self._discover_site(site):
                    yield sentence
                self.logger.info(f"Completed discovery for site: {site.key}")
            except Exception as e:
                self.logger.error(f"Error during discovery for site {site.key}: {e}", exc_info=True)
                continue

    async def _discover_site(self, site) -> AsyncIterator[Sentence]:
        """
        Discover sentences from a single site configuration.

        Args:
            site: SiteConfig object

        Yields:
            Sentence objects
        """
        await self.rate_limiter.wait()

        if not site.enabled:
            self.logger.debug(f"Site {site.key} is disabled, skipping")
            return

        # Navigate to each collection path
        for path in site.paths:
            collection_url = site.base_url.rstrip('/') + '/' + path.lstrip('/')
            self.logger.info(f"Navigating to collection: {collection_url}")

            try:
                page = await self.browser_manager.new_page()
            except Exception as e:
                self.logger.error(f"Failed to create page for {site.key}: {e}")
                continue

            try:
                # Set user agent if rotating
                if self.ua_pool:
                    ua = self.ua_pool.get_random()
                    await page.set_extra_http_headers({"User-Agent": ua})

                # Determine proxy for this request
                proxy = None
                if self.proxy_manager:
                    proxy_rec = self.proxy_manager.get_next_proxy()
                    if proxy_rec:
                        proxy = proxy_rec.proxy_url
                        self.logger.debug(f"Using proxy: {proxy}")

                # Navigate with proxy
                response = await page.goto(collection_url, timeout=60000)
                if response and response.status >= 400:
                    self.logger.warning(f"HTTP {response.status} for {collection_url}")
                    if proxy and self.proxy_manager:
                        self.proxy_manager.mark_result(proxy_rec, False, error=f"HTTP {response.status}")
                    await page.close()
                    continue

                # Check for CAPTCHA
                if self.captcha_handler:
                    should_skip = await self.captcha_handler.should_skip_url(page, "navigator")
                    if should_skip:
                        await page.close()
                        continue

                await page.wait_for_load_state('networkidle')

                # Process collection pages with pagination
                page_num = 1
                while True:
                    # Check if we have navigation selectors
                    if not site.selectors:
                        self.logger.warning(f"No selectors configured for site {site.key}")
                        break

                    if site.selectors.content_table:
                        # Parse current page's content table
                        sentences = await self._parse_content_table(page, site)
                        for sentence in sentences:
                            yield sentence

                    # Check for next page
                    if site.selectors.pagination:
                        next_button = await page.query_selector(site.selectors.pagination.next_page)
                        if next_button and await next_button.is_visible():
                            self.logger.debug(f"Moving to page {page_num + 1} for {site.key}")
                            await next_button.click()
                            await page.wait_for_load_state('networkidle')
                            page_num += 1
                        else:
                            self.logger.debug(f"No more pages for {site.key}")
                            break
                    else:
                        # No pagination configured, single page only
                        break

                # Mark successful proxy use
                if proxy and self.proxy_manager:
                    self.proxy_manager.mark_result(proxy_rec, True)

            except Exception as e:
                self.logger.error(f"Error processing collection {collection_url}: {e}", exc_info=True)
            finally:
                await page.close()

    async def _parse_content_table(self, page, site) -> List[Sentence]:
        """
        Parse a content table page to extract sentence information.

        Args:
            page: Browser page object
            site: SiteConfig object

        Returns:
            List of Sentence objects
        """
        sentences = []

        try:
            selectors = site.selectors.content_table

            # Get all rows (excluding header)
            rows = await page.query_selector_all(selectors.row)
            self.logger.debug(f"Found {len(rows)} rows in content table")

            for row in rows:
                try:
                    # Extract PDF link
                    pdf_link_element = await row.query_selector(selectors.pdf_link)
                    if not pdf_link_element:
                        continue

                    pdf_href = await pdf_link_element.get_attribute('href')
                    if not pdf_href:
                        continue

                    # Resolve relative URLs
                    if pdf_href.startswith('/'):
                        pdf_url = site.base_url.rstrip('/') + pdf_href
                    elif not pdf_href.startswith(('http://', 'https://')):
                        pdf_url = site.base_url.rstrip('/') + '/' + pdf_href.lstrip('/')
                    else:
                        pdf_url = pdf_href

                    # Extract other metadata if available
                    cendoj_number = None
                    court = None
                    date = None

                    # Try to extract cendoj number from row or URL
                    if hasattr(selectors, 'cendoj_number'):
                        cendoj_elem = await row.query_selector(selectors.cendoj_number)
                        if cendoj_elem:
                            cendoj_number = (await cendoj_elem.text_content()).strip()
                    if not cendoj_number:
                        cendoj_number = self._extract_cendoj_from_url(pdf_url)

                    # Try to extract court
                    if hasattr(selectors, 'court'):
                        court_elem = await row.query_selector(selectors.court)
                        if court_elem:
                            court = (await court_elem.text_content()).strip()

                    # Try to extract date
                    if hasattr(selectors, 'date'):
                        date_elem = await row.query_selector(selectors.date)
                        if date_elem:
                            date_str = (await date_elem.text_content()).strip()
                            try:
                                # Attempt to parse date (format may vary)
                                date = datetime.strptime(date_str, '%Y-%m-%d').date()
                            except ValueError:
                                date = date_str

                    # Create Sentence object
                    sentence = Sentence(
                        id=None,  # Will be assigned by storage layer
                        cendoj_number=cendoj_number,
                        court=court,
                        date=date,
                        pdf_url=pdf_url,
                        metadata={
                            'site_key': site.key,
                            'source_url': page.url,
                        }
                    )

                    sentences.append(sentence)
                    self.logger.debug(f"Discovered sentence: {cendoj_number or pdf_url}")

                except Exception as e:
                    self.logger.warning(f"Error parsing row: {e}")
                    continue

        except Exception as e:
            self.logger.error(f"Error parsing content table: {e}", exc_info=True)

        return sentences

    def _extract_cendoj_from_url(self, url: str) -> Optional[str]:
        """
        Extract Cendoj number from URL pattern if possible.

        Args:
            url: PDF URL

        Returns:
            Extracted Cendoj number or None
        """
        import re
        # Common pattern: .../NOMBRE_NUMERO_PDF
        match = re.search(r'/([^/]+_[^/_]+_\d+)\.pdf', url, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    async def start(self):
        """Start the browser manager."""
        await self.browser_manager.start()

    async def stop(self):
        """Stop the browser manager."""
        await self.browser_manager.stop()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
