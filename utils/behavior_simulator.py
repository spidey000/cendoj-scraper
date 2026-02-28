"""Human behavior simulation for browser automation."""

import asyncio
import random
from typing import Optional
from playwright.async_api import Page
from ..utils.logger import get_logger

logger = get_logger(__name__)


class BehaviorSimulator:
    """Simulates human-like behavior in browser pages."""

    def __init__(
        self,
        min_delay: float = 1.0,
        max_delay: float = 5.0,
        delay_distribution: str = "normal"  # "uniform", "normal", "exponential"
    ):
        """
        Initialize behavior simulator.

        Args:
            min_delay: Minimum delay in seconds
            max_delay: Maximum delay in seconds
            delay_distribution: Type of distribution for delays
        """
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.delay_distribution = delay_distribution

    async def random_delay(self, custom_min: Optional[float] = None, custom_max: Optional[float] = None):
        """
        Wait a random amount of time to simulate human reading/thinking.

        Args:
            custom_min: Override min delay
            custom_max: Override max delay
        """
        min_d = custom_min if custom_min is not None else self.min_delay
        max_d = custom_max if custom_max is not None else self.max_delay

        if self.delay_distribution == "uniform":
            delay = random.uniform(min_d, max_d)
        elif self.delay_distribution == "normal":
            # Normal distribution centered between min and max
            mean = (min_d + max_d) / 2
            std = (max_d - min_d) / 4
            delay = random.gauss(mean, std)
            delay = max(min_d, min(max_d, delay))
        elif self.delay_distribution == "exponential":
            # Exponential with mean at (min+max)/2
            scale = (min_d + max_d) / 2
            delay = random.expovariate(1/scale)
            delay = max(min_d, min(max_d, delay))
        else:
            raise ValueError(f"Unknown delay distribution: {self.delay_distribution}")

        await asyncio.sleep(delay)

    async def move_mouse_randomly(self, page: Page, num_moves: Optional[int] = None):
        """
        Move mouse to random positions on the page.

        Args:
            page: Playwright page object
            num_moves: Number of random movements (random if None)
        """
        if num_moves is None:
            num_moves = random.randint(3, 10)

        try:
            viewport = page.viewport_size
            if not viewport:
                return

            width = viewport.get('width', 1920)
            height = viewport.get('height', 1080)

            for _ in range(num_moves):
                # Random position within viewport
                x = random.randint(0, width)
                y = random.randint(0, height)

                try:
                    await page.mouse.move(x, y)
                    # Short pause between movements
                    await asyncio.sleep(random.uniform(0.05, 0.2))
                except Exception:
                    # Page might be closed or mouse not available
                    break

        except Exception as e:
            logger.debug(f"Mouse movement failed: {e}")

    async def scroll_human(self, page: Page, scrolls: Optional[int] = None):
        """
        Scroll down the page in a human-like manner with pauses.

        Args:
            page: Playwright page object
            scrolls: Number of scroll actions (random if None)
        """
        if scrolls is None:
            scrolls = random.randint(3, 8)

        try:
            # Get page height
            page_height = await page.evaluate("() => document.body.scrollHeight")
            viewport_height = page.viewport_size.get('height', 1080) if page.viewport_size else 1080

            current_scroll = 0
            for i in range(scrolls):
                # Random scroll amount (like a mouse wheel)
                scroll_amount = random.randint(300, 800)
                current_scroll += scroll_amount

                # Don't overscroll
                if current_scroll > page_height - viewport_height:
                    break

                await page.evaluate(f"window.scrollTo(0, {current_scroll})")

                # Pause as if reading content
                read_time = random.uniform(0.3, 1.5)
                await asyncio.sleep(read_time)

                # Small chance to scroll back up a bit
                if random.random() < 0.2 and i > 1:
                    back_scroll = random.randint(100, 300)
                    current_scroll = max(0, current_scroll - back_scroll)
                    await page.evaluate(f"window.scrollTo(0, {current_scroll})")
                    await asyncio.sleep(random.uniform(0.2, 0.5))

        except Exception as e:
            logger.debug(f"Scroll failed: {e}")

    async def click_random_element(self, page: Page, selector: str = "a, button, input"):
        """
        Click a random element on the page (use with caution).

        Args:
            page: Playwright page object
            selector: CSS selector for elements to click
        """
        try:
            elements = await page.query_selector_all(selector)
            visible_elements = []

            for el in elements:
                try:
                    if await el.is_visible():
                        visible_elements.append(el)
                except:
                    continue

            if not visible_elements:
                return

            # Pick random visible element
            target = random.choice(visible_elements)

            # Move to element then click
            await target.hover()
            await asyncio.sleep(random.uniform(0.1, 0.3))
            await target.click()

            # Pause after click
            await asyncio.sleep(random.uniform(0.5, 1.5))

        except Exception as e:
            logger.debug(f"Random click failed: {e}")

    async def simulate_page_interaction(self, page: Page):
        """
        Perform a series of random interactions to look more human.

        Args:
            page: Playwright page object
        """
        # Random delay before starting
        await self.random_delay(0.5, 2)

        # Mouse movements
        if random.random() < 0.7:  # 70% chance
            await self.move_mouse_randomly(page, random.randint(3, 8))

        # Scrolling
        if random.random() < 0.6:  # 60% chance
            await self.scroll_human(page, random.randint(2, 6))

        # Hover over some links (without clicking)
        try:
            links = await page.query_selector_all("a")
            if links:
                random_link = random.choice(links[:10])  # Limit to first few
                try:
                    await random_link.hover()
                    await asyncio.sleep(random.uniform(0.2, 0.8))
                except:
                    pass
        except:
            pass

        # Random click on non-critical element (rare)
        if random.random() < 0.1:  # 10% chance
            await self.click_random_element(page, "a:not([href*='logout']):not([href*='signout'])")

        # Random delay before finishing
        await self.random_delay(0.5, 2)

    async def type_human(self, page: Page, selector: str, text: str, delay_range: tuple = (50, 150)):
        """
        Type text with random delays between keystrokes.

        Args:
            page: Playwright page object
            selector: Element selector
            text: Text to type
            delay_range: Min/max delay between keystrokes in ms
        """
        element = await page.query_selector(selector)
        if not element:
            raise ValueError(f"Element not found: {selector}")

        await element.click()
        await asyncio.sleep(random.uniform(0.1, 0.3))

        for char in text:
            await page.keyboard.type(char, delay=random.randint(*delay_range))
            # Occasionally pause like a human thinking
            if random.random() < 0.05:  # 5% chance
                await asyncio.sleep(random.uniform(0.1, 0.3))
