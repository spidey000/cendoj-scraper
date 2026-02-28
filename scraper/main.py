"""Cendoj scraper main entry point."""

import asyncio
import sys
from pathlib import Path
from typing import Optional
import yaml
import click
from playwright.async_api import async_playwright

from .browser import BrowserManager
from .navigator import CendojNavigator
from .downloader import DownloadManager
from .storage.database import Database
from .config.settings import Settings
from cendoj.utils.logger import get_logger

logger = get_logger(__name__)

class CendojScraper:
    """Main scraper orchestrator."""

    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config = Settings.from_yaml(config_path)
        self.db: Optional[Database] = None
        self.browser: Optional[BrowserManager] = None
        self.navigator: Optional[CendojNavigator] = None
        self.downloader: Optional[DownloadManager] = None

    async def initialize(self):
        """Initialize all components."""
        logger.info("Initializing scraper...")

        # Initialize database
        self.db = Database(self.config.storage.database_path)
        await self.db.initialize()

        # Initialize browser
        self.browser = BrowserManager(
            headless=self.config.browser.headless,
            stealth=self.config.browser.stealth_mode
        )
        await self.browser.start()

        # Initialize navigator
        page = await self.browser.new_page()
        self.navigator = CendojNavigator(
            page=page,
            base_url=self.config.sites.cendoj.base_url
        )

        # Initialize downloader
        self.downloader = DownloadManager(
            db=self.db,
            storage_path=Path(self.config.storage.pdf_dir),
            max_concurrent=self.config.downloader.max_concurrent,
            rate_limit=self.config.downloader.rate_limit
        )

        logger.info("Scraper initialized successfully")

    async def run(self):
        """Run the scraping process."""
        try:
            logger.info("Starting scraping process...")

            # Discover collections
            collections = await self.navigator.discover_collections()
            logger.info(f"Found {len(collections)} collections")

            # Process each collection
            for collection in collections:
                logger.info(f"Processing collection: {collection.name}")
                await self.process_collection(collection)

            logger.info("Scraping completed successfully")

        except Exception as e:
            logger.error(f"Scraping failed: {e}", exc_info=True)
            raise
        finally:
            await self.cleanup()

    async def process_collection(self, collection):
        """Process a single collection."""
        # Get all sentences for the collection
        sentences = await self.navigator.get_sentences(collection)

        # Check if we're in scrape-only mode
        if self.config.scrape_only:
            logger.info(f"Scrape-only mode: Validating URLs for collection {collection.name}")
            await self.downloader.validate_all(sentences)
        else:
            # Queue downloads
            logger.info(f"Download mode: Starting downloads for collection {collection.name}")
            await self.downloader.download_all(sentences)

    async def cleanup(self):
        """Clean up resources."""
        if self.browser:
            await self.browser.stop()
        if self.db:
            await self.db.close()

@click.command()
@click.option('--config', default='config/settings.yaml', help='Path to config file')
@click.option('--collection', help='Specific collection to scrape')
@click.option('--resume', is_flag=True, help='Resume from last successful download')
@click.option('--scrape-only', is_flag=True, help='Only scrape URLs without downloading files')
def main(config: str, collection: Optional[str], resume: bool, scrape_only: bool):
    """CLI entry point for Cendoj scraper."""
    scraper = CendojScraper(config)
    
    # Override scrape-only setting from CLI
    if scrape_only:
        scraper.config.scrape_only = True
        logger.info("Running in scrape-only mode - URLs will be validated but not downloaded")

    try:
        asyncio.run(scraper.initialize())
        asyncio.run(scraper.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
