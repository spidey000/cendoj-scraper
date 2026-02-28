"""Discovery Scanner: Main orchestrator for PDF discovery."""

import asyncio
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

from cendoj.scraper.browser import BrowserManager
from cendoj.scraper.deep_crawler import DeepCrawler
from cendoj.scraper.navigator import Navigator
from cendoj.scraper.strategies.base import DiscoveryStrategy, StrategyResult
from cendoj.scraper.strategies.sitemap import SitemapStrategy
from cendoj.utils.logger import get_logger
from cendoj.utils.proxy_manager import ProxyManager
from cendoj.utils.ua_pool import UserAgentPool
from cendoj.utils.adaptive_limiter import AdaptiveRateLimiter
from cendoj.utils.behavior_simulator import BehaviorSimulator
from cendoj.utils.captcha_handler import CAPTCHAHandler
from cendoj.storage.database import init_db, get_session, Base
from cendoj.storage.schemas import DiscoverySession
from cendoj.config.settings import Config

logger = get_logger(__name__)


class DiscoveryScanner:
    """
    Main orchestrator for PDF discovery.

    Supports multiple modes:
    - shallow: Use Navigator only (original table-based extraction)
    - deep: Deep crawl with BFS from seed URLs
    - full: Deep crawl without depth limits
    """

    def __init__(self, config: Config):
        """
        Initialize DiscoveryScanner.

        Args:
            config: Configuration object
        """
        self.config = config
        self.session_id = str(uuid.uuid4())
        self.logger = get_logger(__name__)

        # Components (initialized later)
        self.browser_manager: Optional[BrowserManager] = None
        self.proxy_manager: Optional[ProxyManager] = None
        self.ua_pool: Optional[UserAgentPool] = None
        self.rate_limiter: Optional[AdaptiveRateLimiter] = None
        self.behavior_sim: Optional[BehaviorSimulator] = None
        self.captcha_handler: Optional[CAPTCHAHandler] = None
        self.navigator: Optional[Navigator] = None
        self.deep_crawler: Optional[DeepCrawler] = None

        # Strategy plugins
        self.strategies: List[DiscoveryStrategy] = []

        # DB session
        self.db_session = None

        # Stats
        self.stats = {
            'total_pdfs': 0,
            'accessible': 0,
            'broken': 0,
            'blocked': 0,
            'pages_visited': 0,
            'errors': 0,
        }

    async def initialize(self, resume_session_id: Optional[str] = None):
        """
        Initialize all components.

        Args:
            resume_session_id: Session ID to resume from
        """
        self.logger.info(f"Initializing DiscoveryScanner (session: {self.session_id})")

        # Initialize database
        init_db(self.config.database_path)
        self.db_session = get_session()

        # Create discovery session record
        session = DiscoverySession(
            id=self.session_id,
            mode=self.config.discovery_mode,
            max_depth=self.config.discovery_max_depth,
            config_snapshot=self.config._config,
            status='running'
        )
        self.db_session.add(session)
        self.db_session.commit()
        self.logger.info(f"Created discovery session: {self.session_id}")

        # Initialize components
        self.browser_manager = BrowserManager(
            headless=self.config.headless,
            stealth=self.config.stealth_mode
        )
        await self.browser_manager.start()

        # Proxy manager
        if self.config.proxy_enabled:
            self.proxy_manager = ProxyManager({
                'min_proxies_required': 100,
                'min_score': 30,
            }, cache_file='data/proxies_cache.json')
            await self.proxy_manager.initialize()
            self.logger.info(f"Proxy manager initialized with {len(self.proxy_manager.proxies)} proxies")

        # User agent pool
        self.ua_pool = UserAgentPool(self.config.ua_pool_file)
        if self.config.ua_rotate_per_session:
            self.ua_pool.set_session_ua()

        # Rate limiter
        self.rate_limiter = AdaptiveRateLimiter(
            requests_per_minute=self.config.rate_limiting_requests_per_minute,
            burst_size=self.config.rate_limiting_burst_size,
            backoff_on_429=self.config.rate_limiting_backoff_on_429,
            max_backoff_seconds=self.config.rate_limiting_max_backoff_seconds,
        )

        # Behavior simulator
        if self.config.behavior_simulate_human:
            self.behavior_sim = BehaviorSimulator(
                min_delay=self.config.behavior_min_delay,
                max_delay=self.config.behavior_max_delay,
                delay_distribution=self.config.behavior_delay_distribution
            )

        # CAPTCHA handler
        if self.config.captcha_auto_detect:
            self.captcha_handler = CAPTCHAHandler(
                screenshots_dir='data/sessions/captchas',
                pause_on_captcha=self.config.captcha_pause_on_captcha,
                auto_screenshot=self.config.captcha_screenshot_on_captcha
            )

        # Navigator (for shallow mode or as fallback)
        self.navigator = Navigator(
            config=self.config,
            browser_manager=self.browser_manager
        )

        # Deep crawler
        self.deep_crawler = DeepCrawler(
            browser_manager=self.browser_manager,
            config=self.config,
            proxy_manager=self.proxy_manager,
            ua_pool=self.ua_pool,
            rate_limiter=self.rate_limiter,
            captcha_handler=self.captcha_handler,
            behavior_sim=self.behavior_sim
        )

        self._load_strategies()
        if self.strategies:
            await asyncio.gather(*(strategy.initialize() for strategy in self.strategies))

        self.logger.info("All components initialized successfully")

    async def run(self, collections: Optional[list] = None, resume: bool = False):
        """
        Main discovery loop.

        Args:
            collections: Optional list of collections to scrape (from sites.yaml)
            resume: Whether to resume from previous session
        """
        try:
            # Get seed URLs
            if self.config.discovery_mode == 'shallow':
                # Use original Navigator approach
                self.logger.info("Running in SHALLOW mode (table extraction only)")
                async for sentence in self._run_shallow(collections):
                    yield sentence
            else:
                # Deep crawl mode
                self.logger.info(f"Running in {self.config.discovery_mode.upper()} mode (deep crawl)")
                strategy_results = await self._run_strategies()
                seed_urls = await self._get_seed_urls(collections, strategy_results)

                await self.deep_crawler.initialize(
                    session_id=self.session_id,
                    seed_urls=seed_urls
                )

                async for pdf in self.deep_crawler.crawl():
                    self.stats['total_pdfs'] += 1
                    if pdf.get('validation', {}).get('accessible'):
                        self.stats['accessible'] += 1
                    else:
                        self.stats['broken'] += 1

                    # Update session stats periodically
                    if self.stats['total_pdfs'] % 100 == 0:
                        await self._update_session_stats()

                    yield pdf

                self.stats['pages_visited'] = self.deep_crawler.stats['pages_visited']

        except KeyboardInterrupt:
            self.logger.warning("Interrupted by user")
            await self._update_session_status('interrupted')
            raise
        except Exception as e:
            self.logger.error(f"Discovery failed: {e}", exc_info=True)
            await self._update_session_status('failed')
            raise
        finally:
            await self.cleanup()

    async def _run_shallow(self, collections: Optional[list]):
        """
        Shallow discovery using Navigator (original table extraction).

        Args:
            collections: Optional collection filters
        """
        # Use original Navigator's discover_sentences
        async with self.navigator as nav:
            async for sentence in nav.discover_sentences():
                # Convert Sentence to dict
                yield {
                    'url': sentence.pdf_url,
                    'source_url': sentence.metadata.get('source_url', ''),
                    'depth': 0,
                    'method': 'table_css',
                    'validation': {},
                    'sentence': sentence,
                }

    async def _get_seed_urls(self, collections: Optional[list], strategy_results: Optional[List[StrategyResult]] = None) -> list:
        """
        Get seed URLs for deep crawl, combining strategy outputs and config paths.

        Args:
            collections: Optional specific collections
            strategy_results: Optional list of strategy discovery payloads

        Returns:
            List of deduplicated seed URLs
        """
        urls = []

        if strategy_results:
            for result in strategy_results:
                urls.extend(result.seed_urls)

        if collections:
            sites = self.config.sites
            for site in sites:
                async with self.navigator as nav:
                    # Placeholder for collection-specific logic
                    pass
        else:
            for site in self.config.sites:
                if not site.get('enabled', True):
                    continue
                base_url = (site.get('base_url') or '').rstrip('/')
                if not base_url:
                    continue
                for path in site.get('paths', []):
                    if not path:
                        continue
                    url = f"{base_url}/{path.lstrip('/')}"
                    urls.append(url)

        deduped = list(dict.fromkeys(urls))
        self.logger.info(f"Generated {len(deduped)} seed URLs ({len(urls)} before dedup)")
        return deduped

    def _load_strategies(self):
        """Instantiate enabled discovery strategies."""
        from cendoj.scraper.strategies.pattern_generator import PatternGenerator
        from cendoj.scraper.strategies.search_explorer import SearchExplorer
        from cendoj.scraper.strategies.taxonomy import TaxonomyStrategy
        from cendoj.scraper.strategies.form_discovery import FormDiscoveryStrategy
        from cendoj.scraper.strategies.archive_probe import ArchiveProbeStrategy
        available = [
            SitemapStrategy,
            PatternGenerator,
            SearchExplorer,
            TaxonomyStrategy,
            FormDiscoveryStrategy,
            ArchiveProbeStrategy,
        ]
        self.strategies = []
        for strategy_cls in available:
            strategy = strategy_cls(
                config=self.config,
                browser_manager=self.browser_manager,
                rate_limiter=self.rate_limiter,
                proxy_manager=self.proxy_manager,
                ua_pool=self.ua_pool,
            )
            if strategy.enabled:
                self.logger.info(f"Strategy enabled: {strategy.name}")
                self.strategies.append(strategy)
            else:
                self.logger.debug(f"Strategy disabled: {strategy.name}")

    async def _run_strategies(self) -> List[StrategyResult]:
        """Execute all configured strategies sequentially."""
        results: List[StrategyResult] = []
        for strategy in self.strategies:
            try:
                self.logger.info(f"Running strategy: {strategy.name}")
                result = await strategy.discover()
                if result:
                    results.append(result)
                    self.logger.info(
                        f"Strategy {strategy.name} produced {len(result.seed_urls)} seed URLs"
                    )
            except Exception as exc:
                self.logger.error(f"Strategy {strategy.name} failed: {exc}", exc_info=True)
        return results

    async def _update_session_stats(self):
        """Update discovery session record in DB."""
        try:
            session = self.db_session.query(DiscoverySession).filter_by(id=self.session_id).first()
            if session:
                session.total_pages_visited = self.deep_crawler.stats['pages_visited']
                session.total_links_found = self.deep_crawler.stats['pdfs_found']
                session.new_links = self.stats['total_pdfs']
                session.errors = self.deep_crawler.stats['errors']
                self.db_session.commit()
        except Exception as e:
            self.logger.error(f"Failed to update session stats: {e}")

    async def _update_session_status(self, status: str):
        """Update discovery session status."""
        try:
            session = self.db_session.query(DiscoverySession).filter_by(id=self.session_id).first()
            if session:
                session.status = status
                session.end_time = datetime.utcnow()
                if status == 'interrupted':
                    # Save current state
                    session.interrupted_at = {
                        'queue_size': len(self.deep_crawler.queue),
                        'visited_count': len(self.deep_crawler.visited_urls),
                        'current_depth': 0,  # TODO: capture actual depth
                    }
                self.db_session.commit()
        except Exception as e:
            self.logger.error(f"Failed to update session status: {e}")

    async def cleanup(self):
        """Clean up resources."""
        self.logger.info("Cleaning up DiscoveryScanner...")

        if self.strategies:
            await asyncio.gather(*(strategy.cleanup() for strategy in self.strategies))

        if self.browser_manager:
            await self.browser_manager.stop()

        if self.db_session:
            self.db_session.close()

        self.logger.info("Cleanup complete")

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
