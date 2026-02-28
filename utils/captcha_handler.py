"""CAPTCHA detection and handling system."""

import re
import time
import asyncio
from pathlib import Path
from datetime import datetime
from playwright.async_api import Page
from typing import Optional, Tuple
from cendoj.utils.logger import get_logger

logger = get_logger(__name__)


class CAPTCHAHandler:
    """Detects CAPTCHA challenges and handles them (pause, screenshot, alert)."""

    # Patterns indicating CAPTCHA presence
    CAPTCHA_PATTERNS = [
        # Common CAPTCHA text
        r'captcha',
        r'recaptcha',
        r'hcaptcha',
        r'verify you are human',
        r'prove you are not a robot',
        r'please complete the security check',
        r'access denied',
        r'too many requests',
        r'rate limit exceeded',
        r'cloudflare',
        r'ddos protection',
        r'security check',
        r'are you human',
        # Spanish patterns (for Cendoj.es)
        r'comprueba que eres humano',
        r'verificación de seguridad',
        r'completa el desafío',
        r'acceso denegado',
        r'demasiadas solicitudes',
        r'límite de tasa excedido',
    ]

    # HTML selectors for CAPTCHA elements
    CAPTCHA_SELECTORS = [
        "iframe[src*='recaptcha']",
        "iframe[src*='hcaptcha']",
        ".captcha",
        ".g-recaptcha",
        ".h-captcha",
        "[data-captcha]",
        "div[class*='captcha']",
        "div[id*='captcha']",
        # reCAPTCHA v2 checkbox
        ".recaptcha-checkbox",
        ".recaptcha-checkbox-border",
    ]

    def __init__(
        self,
        screenshots_dir: str = "data/sessions/captchas",
        pause_on_captcha: bool = True,
        auto_screenshot: bool = True
    ):
        """
        Initialize CAPTCHA handler.

        Args:
            screenshots_dir: Directory to save CAPTCHA screenshots
            pause_on_captcha: Whether to pause execution when CAPTCHA detected
            auto_screenshot: Take screenshot automatically on detection
        """
        self.screenshots_dir = Path(screenshots_dir)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.pause_on_captcha = pause_on_captcha
        self.auto_screenshot = auto_screenshot
        self.logger = get_logger(__name__)

        # Stats
        self.captcha_count = 0
        self.last_captcha_time: Optional[datetime] = None

    async def check_page(self, page: Page) -> Tuple[bool, Optional[str]]:
        """
        Check if current page contains CAPTCHA.

        Args:
            page: Playwright page object

        Returns:
            Tuple of (is_captcha, reason)
        """
        # Method 1: Check page content for patterns
        try:
            content = await page.content()
            content_lower = content.lower()

            for pattern in self.CAPTCHA_PATTERNS:
                if re.search(pattern, content_lower, re.IGNORECASE):
                    reason = f"Pattern match: {pattern}"
                    self.logger.warning(f"CAPTCHA detected: {reason}")
                    return True, reason
        except Exception as e:
            self.logger.debug(f"Error checking page content: {e}")

        # Method 2: Check for CAPTCHA elements
        try:
            for selector in self.CAPTCHA_SELECTORS:
                elements = await page.query_selector_all(selector)
                if elements:
                    reason = f"Element found: {selector}"
                    self.logger.warning(f"CAPTCHA detected: {reason}")
                    return True, reason
        except Exception as e:
            self.logger.debug(f"Error checking CAPTCHA elements: {e}")

        # Method 3: Check page title
        try:
            title = await page.title()
            title_lower = title.lower()
            for pattern in ['captcha', 'security check', 'verification']:
                if pattern in title_lower:
                    reason = f"Title contains: {pattern}"
                    self.logger.warning(f"CAPTCHA detected: {reason}")
                    return True, reason
        except:
            pass

        # Method 4: Check for HTTP status headers (Cloudflare)
        try:
            # Cloudflare challenge pages often have specific headers
            response = await page.evaluate("""
                () => {
                    const perfEntries = performance.getEntries();
                    return perfEntries.length > 0 ? perfEntries[0].name : null;
                }
            """)
            if response and ('challenge' in response.lower() or 'captcha' in response.lower()):
                reason = f"Performance entry: {response}"
                self.logger.warning(f"CAPTCHA detected: {reason}")
                return True, reason
        except:
            pass

        return False, None

    async def handle_captcha(
        self,
        page: Page,
        session_id: str,
        screenshot: bool = True,
        pause_seconds: int = 0
    ) -> bool:
        """
        Handle detected CAPTCHA.

        Args:
            page: Playwright page object
            session_id: Current discovery session ID
            screenshot: Whether to take screenshot
            pause_seconds: Seconds to pause (0 = wait for manual input)

        Returns:
            True if should retry, False to skip/abort
        """
        self.captcha_count += 1
        self.last_captcha_time = datetime.utcnow()

        url = page.url
        self.logger.error(f"[{session_id}] CAPTCHA detected at: {url}")

        # Take screenshot
        screenshot_path = None
        if screenshot:
            screenshot_path = self.screenshots_dir / f"captcha_{session_id}_{int(time.time())}.png"
            try:
                await page.screenshot(path=str(screenshot_path), full_page=True)
                self.logger.info(f"[{session_id}] CAPTCHA screenshot saved: {screenshot_path}")
            except Exception as e:
                self.logger.error(f"Failed to take CAPTCHA screenshot: {e}")

        # Log details
        self.logger.warning("=" * 80)
        self.logger.warning(f"⚠️  CAPTCHA DETECTED!")
        self.logger.warning(f"   URL: {url}")
        self.logger.warning(f"   Session: {session_id}")
        self.logger.warning(f"   Screenshot: {screenshot_path or 'not taken'}")
        self.logger.warning("=" * 80)

        # Notify via file (for external alerting scripts)
        alert_file = self.screenshots_dir / f"alert_{session_id}.txt"
        with open(alert_file, 'w') as f:
            f.write(f"CAPTCHA detected at {datetime.utcnow().isoformat()}\n")
            f.write(f"URL: {url}\n")
            f.write(f"Screenshot: {screenshot_path}\n")
            f.write(f"Session: {session_id}\n")

        # Pause for manual resolution if configured
        if self.pause_on_captcha:
            if pause_seconds > 0:
                self.logger.info(f"[{session_id}] Pausing for {pause_seconds} seconds...")
                await asyncio.sleep(pause_seconds)
                self.logger.info(f"[{session_id}] Resuming after pause")
                return True
            else:
                # Wait for manual input
                print("\n" + "="*80)
                print("⚠️  CAPTCHA DETECTED!")
                print(f"   URL: {url}")
                print(f"   Check screenshot: {screenshot_path}")
                print("\n   Action required:")
                print("   1. Open the browser (if visible)")
                print("   2. Solve the CAPTCHA manually")
                print("   3. Press ENTER to continue scraping")
                print("   4. Type 'skip' + ENTER to skip this URL")
                print("   5. Type 'abort' + ENTER to abort session")
                print("="*80 + "\n")

                try:
                    user_input = asyncio.get_event_loop().run_in_executor(
                        None, input, "What to do? [continue/skip/abort]: "
                    )
                    choice = await user_input
                    choice = choice.strip().lower()

                    if choice == 'skip':
                        self.logger.info(f"[{session_id}] Skipping URL due to CAPTCHA")
                        return False  # Skip this URL
                    elif choice == 'abort':
                        self.logger.warning(f"[{session_id}] Aborting session due to CAPTCHA")
                        raise KeyboardInterrupt("User aborted due to CAPTCHA")
                    else:
                        self.logger.info(f"[{session_id}] Continuing after manual CAPTCHA resolution")
                        return True
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    self.logger.error(f"Error getting user input: {e}, continuing...")
                    return True
        else:
            # Auto-continue (not recommended)
            self.logger.warning(f"[{session_id}] Auto-continuing without solving CAPTCHA (likely to fail)")
            await asyncio.sleep(5)  # Brief pause
            return True

    async def should_skip_url(self, page: Page, session_id: str) -> bool:
        """
        Check if current page has CAPTCHA and handle it.

        Args:
            page: Playwright page object
            session_id: Current session ID

        Returns:
            True if URL should be skipped, False to continue
        """
        is_captcha, reason = await self.check_page(page)
        if is_captcha:
            self.logger.warning(f"[{session_id}] CAPTCHA blocking access: {reason}")
            should_continue = await self.handle_captcha(page, session_id)
            return not should_continue  # Skip if handle_captcha returns False
        return False
