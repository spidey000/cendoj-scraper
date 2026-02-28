"""Navigator module for discovering court sentences across configured sites."""

import asyncio
from typing import Optional, List, AsyncIterator, Dict, Any
from urllib.parse import urljoin
from datetime import datetime

import aiohttp
from bs4 import BeautifulSoup
from playwright.async_api import Error

from cendoj.scraper.models import Sentence
from cendoj.scraper.browser import BrowserManager
from cendoj.config.settings import Config
from cendoj.utils.logger import get_logger
from cendoj.utils.rate_limiter import RateLimiter
from cendoj.utils.proxy_manager import ProxyManager
from cendoj.utils.ua_pool import UserAgentPool
from cendoj.utils.captcha_handler import CAPTCHAHandler


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
        self._owns_browser = browser_manager is None
        self.browser_manager = browser_manager or BrowserManager(
            headless=config.headless,
            stealth=config.stealth_mode,
        )
        self._started = False
        self.proxy_manager = proxy_manager
        self.ua_pool = ua_pool
        self.captcha_handler = captcha_handler
        log_file = self.config.logging_config.get('file')
        self.logger = get_logger(__name__, log_file)
        self.rate_limiter = RateLimiter(
            requests_per_minute=self.config.rate_limiting_requests_per_minute
        )

    async def discover_sentences(self, site_override: Optional[str] = None) -> AsyncIterator[Sentence]:
        """
        Discover sentences across all configured sites or a specific site.

        Args:
            site_override: Optional site key to limit discovery to one site

        Yields:
            Sentence objects as they are discovered
        """
        sites: List[Dict[str, Any]] = []
        for site in self.config.sites:
            if site_override:
                if site_override not in (
                    site.get('name'),
                    site.get('base_url')
                ):
                    continue
            sites.append(site)

        if not sites:
            self.logger.warning("No matching sites found in configuration")
            return

        for site in sites:
            site_name = site.get('name') or site.get('base_url', 'unknown')
            try:
                self.logger.info(f"Starting discovery for site: {site_name}")
                async for sentence in self._discover_site(site):
                    yield sentence
                self.logger.info(f"Completed discovery for site: {site_name}")
            except Exception as e:
                self.logger.error(
                    f"Error during discovery for site {site_name}: {e}",
                    exc_info=True,
                )
                continue

    async def _discover_site(self, site: Dict[str, Any]) -> AsyncIterator[Sentence]:
        """Discover sentences from a single site configuration."""

        if not site.get('enabled', True):
            site_name = site.get('name') or site.get('base_url', 'unknown')
            self.logger.debug(f"Site {site_name} is disabled, skipping")
            return

        api_cfg = site.get('api') or {}
        if api_cfg.get('type') == 'query_last_sentences':
            async for sentence in self._discover_last_sentences_api(api_cfg):
                yield sentence
            return

        base_url = (site.get('base_url') or '').rstrip('/')
        paths = site.get('paths') or []
        selectors = site.get('selectors') or {}
        pagination_cfg = selectors.get('pagination') or {}
        next_selector = pagination_cfg.get('next_page')

        if not base_url or not paths:
            site_name = site.get('name') or site.get('base_url', 'unknown')
            self.logger.warning(f"Site {site_name} missing base_url or paths")
            return

        base_url_with_slash = base_url + ('/' if not base_url.endswith('/') else '')

        for path in paths:
            collection_url = urljoin(base_url_with_slash, path)
            self.logger.info(f"Navigating to collection: {collection_url}")

            proxy_rec = self.proxy_manager.get_next_proxy() if self.proxy_manager else None
            page = None

            try:
                await self.rate_limiter.wait()
                page = await self.browser_manager.new_page()

                if self.ua_pool:
                    ua = self.ua_pool.get_random()
                    if ua:
                        await page.set_extra_http_headers({"User-Agent": ua})

                response = await page.goto(collection_url, timeout=60000)
                if response and response.status >= 400:
                    self.logger.warning(f"HTTP {response.status} for {collection_url}")
                    if proxy_rec and self.proxy_manager:
                        self.proxy_manager.mark_result(proxy_rec, False, error=f"HTTP {response.status}")
                    continue

                if self.captcha_handler:
                    should_skip = await self.captcha_handler.should_skip_url(page, "navigator")
                    if should_skip:
                        continue

                await page.wait_for_load_state('networkidle')
                row_selector = selectors.get('row')
                await self._wait_for_rows(page, row_selector)

                page_num = 1
                while True:
                    if not selectors:
                        self.logger.warning("No selectors configured for current site")
                        break

                    sentences = await self._parse_content_table(page, site)
                    for sentence in sentences:
                        yield sentence

                    if pagination_cfg.get('enabled') and next_selector:
                        next_button = await page.query_selector(next_selector)
                        if next_button and await next_button.is_visible():
                            self.logger.debug(
                                f"Moving to page {page_num + 1} for {collection_url}"
                            )
                            await next_button.click()
                            await page.wait_for_load_state('networkidle')
                            page_num += 1
                            continue
                    break

                if proxy_rec and self.proxy_manager:
                    self.proxy_manager.mark_result(proxy_rec, True)

            except Exception as e:
                self.logger.error(
                    f"Error processing collection {collection_url}: {e}",
                    exc_info=True,
                )
            finally:
                if page:
                    await page.close()

    async def _wait_for_rows(self, page, row_selector: Optional[str]):
        if not row_selector:
            return
        try:
            await page.wait_for_selector(row_selector, timeout=15000)
        except Exception as exc:
            self.logger.warning(f"Timeout esperando selector {row_selector}: {exc}")

    async def _discover_last_sentences_api(self, api_cfg: Dict[str, Any]) -> AsyncIterator[Sentence]:
        """Fetch last sentences using the Poder Judicial search API."""

        search_url = api_cfg.get('search_url')
        if not search_url:
            self.logger.warning("API configuration missing search_url")
            return

        index_url = api_cfg.get('index_url')
        jurisdictions = api_cfg.get('jurisdictions') or ['CIVIL']
        resolution = api_cfg.get('resolution_type', 'SENTENCIA')
        databasematch = api_cfg.get('databasematch', 'TS')
        historical = str(api_cfg.get('historical', False)).lower()
        tab = api_cfg.get('tab', 'AN')
        limit_per_jur = api_cfg.get('limit_per_jurisdiction')
        total_limit = api_cfg.get('total_limit')

        headers = {
            "User-Agent": (self.ua_pool.get_session_ua() if self.ua_pool else None)
                            or (self.ua_pool.get_random() if self.ua_pool else None)
                            or "Mozilla/5.0",
        }
        if index_url:
            headers['Referer'] = index_url

        timeout = aiohttp.ClientTimeout(total=api_cfg.get('timeout', 60))

        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            if index_url:
                try:
                    await session.get(index_url, allow_redirects=True)
                except Exception as exc:
                    self.logger.warning(f"Failed to warm up API session: {exc}")

            yielded = 0
            for jurisdiccion in jurisdictions:
                payload = {
                    'action': api_cfg.get('action', 'queryLastSentences'),
                    'databasematch': databasematch,
                    'HISTORICO': str(historical).lower(),
                    'JURISDICCION': jurisdiccion,
                    'TIPORESOLUCION': resolution,
                    'tab': tab,
                }

                try:
                    response = await session.post(search_url, data=payload)
                except Exception as exc:
                    self.logger.error(f"API request failed for {jurisdiccion}: {exc}")
                    continue

                if response.status != 200:
                    self.logger.warning(
                        f"API request for {jurisdiccion} returned status {response.status}"
                    )
                    continue

                html = await response.text()
                sentences = self._parse_last_sentences_html(html, jurisdiccion)
                if not sentences:
                    self.logger.debug(f"No sentences parsed for {jurisdiccion}")

                count_for_jur = 0
                for sentence in sentences:
                    yield sentence
                    yielded += 1
                    count_for_jur += 1

                    if limit_per_jur and count_for_jur >= limit_per_jur:
                        break
                    if total_limit and yielded >= total_limit:
                        return

    def _parse_last_sentences_html(self, html: str, jurisdiccion: str) -> List[Sentence]:
        soup = BeautifulSoup(html, 'html.parser')
        results: List[Sentence] = []

        for li in soup.select('li.doc'):
            link = li.find('a', href=True)
            if not link:
                continue

            pdf_url = link['href']
            ref = link.get('data-reference') or link.get('data-ref') or link.get('id') or pdf_url
            roj = link.get('data-roj') or link.get_text(strip=True)
            court = link.get('data-jur') or jurisdiccion
            date_str = ''
            date_elem = li.select_one('.fecha')
            if date_elem:
                date_str = date_elem.get_text(strip=True).strip('()')

            summary_elem = li.select_one('.resumen')
            metadata = {
                'source_url': pdf_url,
                'jurisdiccion': jurisdiccion,
                'title': link.get('title') or link.get_text(strip=True),
            }
            if summary_elem:
                metadata['summary'] = summary_elem.get_text(strip=True)

            sentence = Sentence(
                id=ref,
                cendoj_number=roj,
                court=court,
                date=date_str,
                pdf_url=pdf_url,
                metadata=metadata,
            )
            results.append(sentence)

        return results

    async def _parse_content_table(self, page, site: Dict[str, Any]) -> List[Sentence]:
        """
        Parse a content table page to extract sentence information.

        Args:
            page: Browser page object
            site: Site configuration dict

        Returns:
            List of Sentence objects
        """
        sentences = []

        try:
            selectors = site.get('selectors') or {}
            row_selector = selectors.get('row')
            pdf_selector = selectors.get('pdf_link')
            base_url = (site.get('base_url') or '').rstrip('/')

            if not (row_selector and pdf_selector and base_url):
                self.logger.warning("Incomplete selectors configuration for content table")
                return []

            attempts = 3
            rows = []
            for attempt in range(attempts):
                try:
                    rows = await page.query_selector_all(row_selector)
                    break
                except Error as exc:
                    if "Execution context was destroyed" in str(exc) and attempt < attempts - 1:
                        await page.wait_for_load_state('networkidle')
                        await page.wait_for_timeout(500)
                        continue
                    raise
            if not rows:
                return []
            self.logger.debug(f"Found {len(rows)} rows in content table")

            for row in rows:
                try:
                    pdf_link_element = await row.query_selector(pdf_selector)
                    if not pdf_link_element:
                        continue

                    pdf_href = await pdf_link_element.get_attribute('href')
                    if not pdf_href:
                        continue

                    # Resolve relative URLs
                    pdf_url = pdf_href
                    if pdf_href.startswith('/') and base_url.startswith('http'):
                        pdf_url = base_url + pdf_href
                    elif not pdf_href.startswith(('http://', 'https://', 'file://')):
                        prefix = base_url + ('/' if not base_url.endswith('/') else '')
                        pdf_url = urljoin(prefix, pdf_href)

                    # Extract other metadata if available
                    cendoj_number = None
                    court = None
                    date = None

                    # Try to extract cendoj number from row or URL
                    cendoj_selector = selectors.get('cendoj_number')
                    if cendoj_selector:
                        cendoj_elem = await row.query_selector(cendoj_selector)
                        if cendoj_elem:
                            cendoj_number = (await cendoj_elem.text_content()).strip()
                    if not cendoj_number:
                        cendoj_number = self._extract_cendoj_from_url(pdf_url)

                    # Try to extract court
                    court_selector = selectors.get('court')
                    if court_selector:
                        court_elem = await row.query_selector(court_selector)
                        if court_elem:
                            court = (await court_elem.text_content()).strip()

                    # Try to extract date
                    date_selector = selectors.get('date')
                    if date_selector:
                        date_elem = await row.query_selector(date_selector)
                        if date_elem:
                            date_str = (await date_elem.text_content()).strip()
                            try:
                                # Attempt to parse date (format may vary)
                                date = datetime.strptime(date_str, '%Y-%m-%d').date()
                            except ValueError:
                                date = date_str

                    # Create Sentence object
                    sentence = Sentence(
                        id=cendoj_number or pdf_url,
                        cendoj_number=cendoj_number or pdf_url,
                        court=court,
                        date=date,
                        pdf_url=pdf_url,
                        metadata={
                            'site_key': site.get('name') or site.get('base_url'),
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
        """Ensure browser context exists."""
        if not self.browser_manager.context:
            await self.browser_manager.start()
        self._started = True

    async def stop(self):
        """Stop owned browser if necessary."""
        if self._owns_browser and self._started:
            await self.browser_manager.stop()
        self._started = False

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
