"""User-Agent pool management with rotation."""

import random
from pathlib import Path
from typing import List, Optional
from cendoj.utils.logger import get_logger

logger = get_logger(__name__)


class UserAgentPool:
    """Manages a pool of user agents for rotation."""

    def __init__(self, ua_file: str = "config/user_agents.txt"):
        """
        Initialize UA pool from file.

        Args:
            ua_file: Path to text file with one UA per line
        """
        self.ua_file = Path(ua_file)
        self.user_agents: List[str] = []
        self._index = 0
        self.session_ua: Optional[str] = None
        self.logger = logger
        self.load()

    def load(self):
        """Load user agents from file."""
        if not self.ua_file.exists():
            # Default minimal set
            self.user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ]
            self.logger.warning(f"UA file {self.ua_file} not found, using default UAs")
            return

        with open(self.ua_file, 'r') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        self.user_agents = lines
        self.logger.info(f"Loaded {len(self.user_agents)} user agents from {self.ua_file}")

    def get_random(self) -> str:
        """Get a random user agent."""
        return random.choice(self.user_agents)

    def get_next(self) -> str:
        """Get next user agent in round-robin fashion."""
        if not self.user_agents:
            raise RuntimeError("No user agents available")
        ua = self.user_agents[self._index % len(self.user_agents)]
        self._index += 1
        return ua

    def set_session_ua(self, ua: Optional[str] = None):
        """
        Set a user agent for the entire session (if None, pick random).

        Args:
            ua: Specific user agent string, or None for random
        """
        self.session_ua = ua or self.get_random()
        self.logger.info(f"Session UA set to: {self.session_ua[:50]}...")
        return self.session_ua

    def get_session_ua(self) -> Optional[str]:
        """Get the session user agent (if set)."""
        return self.session_ua

    def reset_session_ua(self):
        """Reset session user agent."""
        self.session_ua = None

    def refresh(self):
        """Reload user agents from file."""
        self.load()
