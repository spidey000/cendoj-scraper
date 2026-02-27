"""Fingerprint spoofing to evade detection."""

import json
import random
from typing import Dict, Any
from ..utils.logger import get_logger

logger = get_logger(__name__)

class FingerprintSpoofer:
    """Spoofs browser fingerprints to evade detection."""

    def __init__(self):
        self.fingerprints = self._load_fingerprints()

    def _load_fingerprints(self) -> list:
        """Load realistic browser fingerprints."""
        # Sample fingerprint data (in production, use real fingerprints database)
        return [
            {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "screen_resolution": "1920x1080",
                "available_screen_resolution": "1920x1040",
                "timezone": "Europe/Madrid",
                "language": "es-ES",
                "platform": "Win32",
                "hardware_concurrency": 8,
                "device_memory": 8
            },
            {
                "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "screen_resolution": "1366x768",
                "available_screen_resolution": "1366x728",
                "timezone": "Europe/Madrid",
                "language": "es-ES",
                "platform": "Linux x86_64",
                "hardware_concurrency": 4,
                "device_memory": 4
            }
        ]

    def get_random_fingerprint(self) -> Dict[str, Any]:
        """Return a random fingerprint from the pool."""
        return random.choice(self.fingerprints).copy()

    async def apply_to_context(self, context):
        """Apply fingerprint spoofing to browser context."""
        fingerprint = self.get_random_fingerprint()
        logger.debug(f"Applying fingerprint: {fingerprint['user_agent']}")

        # Inject JavaScript to override navigator properties
        script = f"""
        // Override navigator properties
        Object.defineProperty(navigator, 'userAgent', {{
            get: () => '{fingerprint["user_agent"]}'
        }});

        Object.defineProperty(navigator, 'platform', {{
            get: () => '{fingerprint["platform"]}'
        }});

        Object.defineProperty(navigator, 'hardwareConcurrency', {{
            get: () => {fingerprint["hardware_concurrency"]}
        }});

        Object.defineProperty(navigator, 'deviceMemory', {{
            get: () => {fingerprint["device_memory"]}
        }});

        // Spoof screen resolution
        Object.defineProperty(screen, 'width', {{ get: () => {fingerprint["screen_resolution"].split('x')[0]} }});
        Object.defineProperty(screen, 'height', {{ get: () => {fingerprint["screen_resolution"].split('x')[1]} }});
        Object.defineProperty(screen, 'availWidth', {{ get: () => {fingerprint["available_screen_resolution"].split('x')[0]} }});
        Object.defineProperty(screen, 'availHeight', {{ get: () => {fingerprint["available_screen_resolution"].split('x')[1]} }});

        // Override timezone
        Object.defineProperty(Intl.DateTimeFormat.prototype, 'resolvedOptions', {{
            get: function() {{
                const original = this._originalResolvedOptions || originalResolvedOptions;
                return function() {{
                    const options = original.apply(this, arguments);
                    options.timeZone = '{fingerprint["timezone"]}';
                    options.locale = '{fingerprint["language"]}';
                    return options;
                }};
            }}
        }});
        """

        await context.add_init_script(script)
        logger.info("Fingerprint spoofing applied")