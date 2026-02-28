"""Browser automation with stealth capabilities."""

import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from cendoj.scraper.fingerprint import FingerprintSpoofer
from cendoj.utils.logger import get_logger

logger = get_logger(__name__)

class BrowserManager:
    """Manages browser instance with stealth capabilities."""

    def __init__(self, headless: bool = True, stealth: bool = True):
        self.headless = headless
        self.stealth = stealth
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.fingerprint_spoofer = FingerprintSpoofer() if stealth else None

    async def start(self):
        """Initialize browser with stealth settings."""
        logger.info("Starting browser...")
        self.playwright = await async_playwright().start()

        # Launch Chromium with stealth args
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-accelerated-2d-canvas",
            "--disable-gpu"
        ]

        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=launch_args
        )

        # Create context with viewport and user agent
        context_options = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "locale": "es-ES",
            "timezone_id": "Europe/Madrid"
        }

        self.context = await self.browser.new_context(**context_options)

        # Apply fingerprint spoofing if enabled
        if self.stealth and self.fingerprint_spoofer:
            await self.fingerprint_spoofer.apply_to_context(self.context)

        # Add script to mask automation
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        logger.info("Browser started successfully")

    async def new_page(self) -> Page:
        """Create a new page with stealth settings."""
        if not self.context:
            await self.start()

        page = await self.context.new_page()
        return page

    async def screenshot(self, page: Page, path: str):
        """Take screenshot for debugging."""
        await page.screenshot(path=path, full_page=True)

    async def stop(self):
        """Clean up browser resources."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser stopped")
