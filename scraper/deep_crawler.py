"""Deep crawler for exhaustive PDF link discovery using BFS."""

import asyncio
import re
from collections import deque
from typing import List, Dict, Any, Optional, Set
from urllib.parse import urljoin, urlparse
from datetime import datetime
from pathlib import Path
import pickle

from playwright.async_api import Page

from cendoj.scraper.models import Sentence
from cendoj.scraper.browser import BrowserManager
from cendoj.utils.logger import get_logger
from cendoj.storage.database import get_session
from cendoj.storage.schemas import PDFLink

logger = get_logger(__name__)


class DeepCrawler:
    """Breadth-first deep crawler for discovering PDF links."""

    def __init__(
        self,
        browser_manager: BrowserManager,
        config,
        proxy_manager=None,
        ua_pool=None,
        rate_limiter=None,
        captcha_handler=None,
        behavior_sim=None
    ):
        """
        Initialize DeepCrawler.

        Args:
            browser_manager: BrowserManager instance
            config: Config object
            proxy_manager: Optional ProxyManager
            ua_pool: Optional UserAgentPool
            rate_limiter: Optional AdaptiveRateLimiter
            captcha_handler: Optional CAPTCHAHandler
            behavior_sim: Optional BehaviorSimulator
        """
        self.browser_manager = browser_manager
        self.config = config
        self.proxy_manager = proxy_manager
        self.ua_pool = ua_pool
        self.rate_limiter = rate_limiter
        self.captcha_handler = captcha_handler
        self.behavior_sim = behavior_sim

        # State
        self.visited_urls: Set[str] = set()
        self.queue = deque()  # (url, depth, source_url, extraction_method)
        self.max_depth = config.discovery_max_depth
        self.session_id = None

        # Stats
        self.stats = {
            'pages_visited': 0,
            'pdfs_found': 0,
            'internal_links_found': 0,
            'errors': 0,
            'captchas': 0,
        }

        # Persistence
        self.state_file = None
        self.save_interval = 100  # pages

    async def initialize(self, session_id: str, seed_urls: List[str]):
        """Initialize crawler state."""
        self.session_id = session_id

        # Load state if resuming
        self.state_file = Path(self.config.session_dir) / f"crawler_state_{session_id}.pkl"
        if self.state_file.exists():
            await self._load_state()
            logger.info(f"Resumed from saved state: {len(self.visited_urls)} visited, {len(self.queue)} queued")
        else:
            # Seed initial URLs
            for url in seed_urls:
                self.queue.append((url, 0, None, "seed"))
            logger.info(f"Initialized crawler with {len(seed_urls)} seed URLs")

    async def crawl(self) -> List[Dict[str, Any]]:
        """
        Main crawl loop.

        Yields:
            Dict with PDF metadata: {
                'url': str,
                'source_url': str,
                'depth': int,
                'method': str,
                'validation': Optional[Dict]
            }
        """
        db_session = get_session()

        try:
            while self.queue:
                url, depth, source_url, method = self.queue.popleft()

                # Skip if already visited
                if self._normalize_url(url) in self.visited_urls:
                    continue

                # Check depth limit (0 = unlimited)
                if self.max_depth > 0 and depth >= self.max_depth:
                    logger.debug(f"Skipping {url}: depth {depth} >= max {self.max_depth}")
                    continue

                # Respect rate limiting
                if self.rate_limiter:
                    await self.rate_limiter.wait()

                # Get proxy and UA
                proxy = self.proxy_manager.get_next_proxy() if self.proxy_manager else None
                user_agent = self.ua_pool.get_random() if self.ua_pool else None

                # Visit page
                try:
                    page = await self.browser_manager.new_page()

                    # Set user agent if provided
                    if user_agent:
                        await page.set_extra_http_headers({"User-Agent": user_agent})

                    # Navigate with proxy
                    logger.debug(f"Visiting: {url} (depth={depth}, proxy={proxy.proxy_url if proxy else 'none'})")

                    # Navigate
                    response = await page.goto(url, timeout=self.config.browser_config.get('timeout', 60000))
                    if response and response.status >= 400:
                        logger.warning(f"HTTP {response.status} for {url}")
                        await page.close()
                        continue

                    # Check for CAPTCHA
                    if self.captcha_handler:
                        should_skip = await self.captcha_handler.should_skip_url(page, self.session_id)
                        if should_skip:
                            self.stats['captchas'] += 1
                            await page.close()
                            continue

                    # Simulate human behavior
                    if self.behavior_sim and depth == 0:  # Only on seed pages
                        await self.behavior_sim.simulate_page_interaction(page)

                    # Extract PDFs from this page
                    pdf_links = await self._extract_pdfs_from_page(page, url, depth)
                    for pdf_data in pdf_links:
                        self.stats['pdfs_found'] += 1

                        # Save to database
                        pdf_link = await self._store_pdf_link(pdf_data, db_session)
                        pdf_data['db_id'] = pdf_link.id if pdf_link else None

                        # Validate if configured
                        if self.config.discovery_validate_on_discovery:
                            validation = await self._validate_url(pdf_data['url'])
                            pdf_data['validation'] = validation
                            if pdf_link:
                                pdf_link.status = 'accessible' if validation.get('accessible') else 'broken'
                                pdf_link.validated_at = datetime.utcnow()
                                pdf_link.http_status = validation.get('status')
                                pdf_link.content_length = validation.get('content_length')
                                db_session.commit()

                        yield pdf_data

                    # Extract internal links for BFS (if not at max depth)
                    if (self.max_depth == 0 or depth < self.max_depth) and self.config.discovery_follow_internal_links:
                        internal_links = await self._extract_internal_links(page, url)
                        for link in internal_links:
                            normalized = self._normalize_url(link)
                            if normalized not in self.visited_urls:
                                self.queue.append((link, depth + 1, url, "internal_link"))
                                self.stats['internal_links_found'] += 1

                    await page.close()

                    # Mark as visited
                    self.visited_urls.add(self._normalize_url(url))
                    self.stats['pages_visited'] += 1

                    # Periodic state save
                    if self.stats['pages_visited'] % self.save_interval == 0:
                        await self._save_state()
                        logger.info(f"Progress: {self.stats['pages_visited']} pages, {self.stats['pdfs_found']} PDFs found")

                except Exception as e:
                    logger.error(f"Error visiting {url}: {e}")
                    self.stats['errors'] += 1
                    continue

        finally:
            db_session.close()
            await self._save_state()
            logger.info(f"Crawl finished: {self.stats}")

    async def _extract_pdfs_from_page(self, page: Page, source_url: str, depth: int) -> List[Dict[str, Any]]:
        """
        Extract ALL PDF links from a page using multiple methods.

        Args:
            page: Playwright page
            source_url: URL of the page
            depth: Crawl depth

        Returns:
            List of dicts with PDF metadata
        """
        pdfs = []

        # Method 1: CSS selector (configured)
        try:
            pdf_links = await page.query_selector_all("a[href$='.pdf']")
            for el in pdf_links:
                href = await el.get_attribute('href')
                if href:
                    full_url = urljoin(source_url, href)
                    pdfs.append({
                        'url': full_url,
                        'source_url': source_url,
                        'depth': depth,
                        'method': 'css_pdf_selector',
                        'confidence': 0.9,
                    })
        except Exception as e:
            logger.debug(f"CSS selector extraction failed: {e}")

        # Method 2: Regex scan of entire HTML (fallback)
        try:
            content = await page.content()
            pdf_matches = re.findall(r'https?://[^\s"\'<>]+\.pdf', content, re.IGNORECASE)
            for match in pdf_matches:
                pdfs.append({
                    'url': match,
                    'source_url': source_url,
                    'depth': depth,
                    'method': 'regex_fallback',
                    'confidence': 0.7,
                })
        except Exception as e:
            logger.debug(f"Regex extraction failed: {e}")

        # Method 3: Scan script tags for PDF URLs
        try:
            scripts = await page.query_selector_all("script")
            for script in scripts:
                script_content = await script.text_content()
                if script_content:
                    pdf_matches = re.findall(r'https?://[^\s"\'<>]+\.pdf', script_content, re.IGNORECASE)
                    for match in pdf_matches:
                        pdfs.append({
                            'url': match,
                            'source_url': source_url,
                            'depth': depth,
                            'method': 'script_scan',
                            'confidence': 0.6,
                        })
        except Exception as e:
            logger.debug(f"Script scan extraction failed: {e}")

        # Deduplicate by URL
        seen = set()
        unique_pdfs = []
        for pdf in pdfs:
            normalized = self._normalize_url(pdf['url'])
            if normalized not in seen:
                seen.add(normalized)
                unique_pdfs.append(pdf)

        return unique_pdfs

    async def _extract_internal_links(self, page: Page, base_url: str) -> List[str]:
        """
        Extract internal links for BFS crawling.

        Args:
            page: Playwright page
            base_url: Base URL for resolution

        Returns:
            List of absolute URLs to internal pages
        """
        links = []

        try:
            # Get all <a> elements
            anchor_elements = await page.query_selector_all("a[href]")

            for el in anchor_elements[:200]:  # Limit to avoid explosion
                try:
                    href = await el.get_attribute('href')
                    if not href:
                        continue

                    # Resolve to absolute URL
                    absolute_url = urljoin(base_url, href)

                    # Parse and check if it's internal (same domain)
                    parsed_base = urlparse(base_url)
                    parsed_link = urlparse(absolute_url)

                    # Skip if different domain (external)
                    if parsed_link.netloc and parsed_link.netloc != parsed_base.netloc:
                        continue

                    # Skip common non-html extensions
                    if any(ext in parsed_link.path.lower() for ext in ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.zip', '.doc', '.docx']):
                        continue

                    # Skip fragments, javascript, mailto
                    if parsed_link.fragment or absolute_url.startswith(('javascript:', 'mailto:', 'tel:')):
                        continue

                    links.append(absolute_url)

                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"Error extracting internal links: {e}")

        logger.debug(f"Found {len(links)} internal links on {base_url}")
        return links[:100]  # Limit per page to avoid explosion

    async def _validate_url(self, url: str) -> Dict[str, Any]:
        """Validate a PDF URL with HEAD request."""
        result = {
            'accessible': False,
            'status': None,
            'content_type': None,
            'content_length': None,
            'error': None,
        }

        try:
            import aiohttp
            proxy = None
            if self.proxy_manager:
                proxy_rec = self.proxy_manager.get_next_proxy()
                if proxy_rec:
                    proxy = proxy_rec.proxy_url

            timeout = aiohttp.ClientTimeout(total=self.config.validate_url_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                headers = {"User-Agent": self.ua_pool.get_random()} if self.ua_pool else {}
                async with session.head(url, proxy=proxy, headers=headers, allow_redirects=True) as resp:
                    result['accessible'] = resp.status == 200
                    result['status'] = resp.status
                    result['content_type'] = resp.headers.get('Content-Type')
                    result['content_length'] = int(resp.headers.get('Content-Length', 0)) if resp.headers.get('Content-Length') else None

                    if proxy and self.proxy_manager:
                        proxy_rec = self.proxy_manager.get_next_proxy()  # Get the same proxy? FIXME
                        self.proxy_manager.mark_result(proxy_rec, resp.status == 200)

        except Exception as e:
            result['error'] = str(e)

        return result

    async def _store_pdf_link(self, pdf_data: Dict[str, Any], db_session) -> Optional[PDFLink]:
        """Store discovered PDF link in database."""
        try:
            normalized = self._normalize_url(pdf_data['url'])

            # Check if already exists
            existing = db_session.query(PDFLink).filter_by(normalized_url=normalized).first()
            if existing and self.config.discovery_deduplicate:
                logger.debug(f"Duplicate PDF URL: {normalized}")
                return None

            pdf_link = PDFLink(
                url=pdf_data['url'],
                normalized_url=normalized,
                source_url=pdf_data['source_url'],
                discovery_session_id=self.session_id,
                discovered_at=datetime.utcnow(),
                status='discovered',
                extraction_method=pdf_data.get('method', 'unknown'),
                extraction_confidence=pdf_data.get('confidence', 1.0),
                metadata_json={
                    'depth': pdf_data.get('depth', 0),
                    'source': pdf_data.get('source_url'),
                }
            )

            db_session.add(pdf_link)
            db_session.commit()

            logger.info(f"Stored PDF link: {pdf_data['url'][:100]}...")
            return pdf_link

        except Exception as e:
            logger.error(f"Failed to store PDF link: {e}")
            db_session.rollback()
            return None

    def _normalize_url(self, url: str) -> str:
        """
        Normalize URL for deduplication.

        Args:
            url: Raw URL

        Returns:
            Normalized URL (lowercase, strip query params that don't matter)
        """
        parsed = urlparse(url.lower())
        # For PDFs, typically only the path matters (query params often are tracking)
        # But keep them if they seem to point to different files
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    async def _save_state(self):
        """Save crawler state to disk for resuming."""
        if not self.state_file:
            return

        state = {
            'session_id': self.session_id,
            'visited_urls': list(self.visited_urls),
            'queue': list(self.queue),
            'stats': self.stats,
            'saved_at': datetime.utcnow().isoformat(),
        }

        try:
            with open(self.state_file, 'wb') as f:
                pickle.dump(state, f)
            logger.debug(f"State saved: {len(self.visited_urls)} visited, {len(self.queue)} queued")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    async def _load_state(self):
        """Load crawler state from disk."""
        try:
            with open(self.state_file, 'rb') as f:
                state = pickle.load(f)

            self.visited_urls = set(state['visited_urls'])
            self.queue = deque(state['queue'])
            self.stats.update(state['stats'])

            logger.info(f"State loaded from {state['saved_at']}")
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            raise
