import yaml
from typing import Dict, List, Optional, Any

class Config:
    def __init__(self, config_path: str = "config/sites.yaml"):
        self.config_path = config_path
        self._config = self._load_config()
        self._validate_config()

    def _load_config(self) -> dict:
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
        self._apply_env_overrides(config)
        return config

    def _apply_env_overrides(self, config: dict):
        """Apply environment variable overrides to config.
        
        Env vars format: CENDOJ__SECTION__KEY=value
        For nested dicts, use double underscore: CENDOJ__browser__stealth=true
        For list sections like sites, use array index: CENDOJ__sites__0__name=site1
        """
        import os
        from typing import Any
        
        def _set_nested_value(d: dict, keys: list, value: str):
            """Set a nested value in dict using list of keys."""
            for key in keys[:-1]:
                if key not in d:
                    d[key] = {}
                d = d[key]
            final_key = keys[-1]
            d[final_key] = self._convert_value(value)

        # Prefix for all Cendoj env vars
        prefix = "CENDOJ__"
        
        for env_key, env_value in os.environ.items():
            if not env_key.startswith(prefix):
                continue
            
            # Remove prefix and split by __
            parts = env_key[len(prefix):].lower().split('__')
            if len(parts) < 2:
                continue  # Need at least section and key
            
            _set_nested_value(config, parts, env_value)

    def _convert_value(self, value: str) -> Any:
        """Convert string value to appropriate type."""
        # Boolean
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        
        # Integer
        try:
            if value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
                return int(value)
        except (ValueError, AttributeError):
            pass
        
        # Float
        try:
            if '.' in value:
                return float(value)
        except (ValueError, AttributeError):
            pass
        
        # List (comma-separated)
        if ',' in value:
            items = [item.strip() for item in value.split(',')]
            # Try to convert items to appropriate types
            converted = []
            for item in items:
                converted.append(self._convert_value(item))
            return converted
        
        # Default: string
        return value

    def _validate_config(self):
        """Validate required configuration sections exist."""
        required_sections = ['sites', 'browser', 'download', 'storage', 'logging']
        for section in required_sections:
            if section not in self._config:
                raise ValueError(f"Missing required configuration section: {section}")

    @property
    def sites(self) -> List[Dict]:
        """Return list of site configurations."""
        return self._config.get('sites', [])

    @property
    def browser_config(self) -> Dict:
        """Return browser configuration."""
        return self._config.get('browser', {})

    @property
    def download_config(self) -> Dict:
        """Return download configuration."""
        return self._config.get('download', {})

    @property
    def storage_config(self) -> Dict:
        """Return storage configuration."""
        return self._config.get('storage', {})

    @property
    def logging_config(self) -> Dict:
        """Return logging configuration."""
        return self._config.get('logging', {})

    @property
    def request_config(self) -> Dict:
        """Return request configuration (optional)."""
        return self._config.get('request', {})

    @property
    def proxy_config(self) -> Dict:
        """Return proxy configuration (optional)."""
        return self._config.get('proxy', {
            'enabled': False,
            'url': None,
            'rotation_interval': 900
        })

    @property
    def stealth_mode(self) -> bool:
        """Return browser stealth mode setting."""
        return self.browser_config.get('stealth', False)

    @property
    def headless(self) -> bool:
        """Return headless mode setting."""
        return self.browser_config.get('headless', True)

    @property
    def user_agent(self) -> str:
        """Return user agent string."""
        return self.browser_config.get('user_agent', '')

    @property
    def max_concurrent(self) -> int:
        """Return max concurrent downloads."""
        return self.download_config.get('max_concurrent', 5)

    @property
    def chunk_size(self) -> int:
        """Return download chunk size."""
        return self.download_config.get('chunk_size', 65536)

    @property
    def download_timeout(self) -> int:
        """Return download timeout in seconds."""
        return self.download_config.get('timeout', 300)

    @property
    def database_path(self) -> str:
        """Return database path."""
        return self.storage_config.get('database', 'data/documents.db')

    @property
    def backup_dir(self) -> str:
        """Return backup directory."""
        return self.storage_config.get('backup_dir', 'data/backups')

    @property
    def export_dir(self) -> str:
        """Return export directory."""
        return self.storage_config.get('export_dir', 'data/exports')

    @property
    def log_level(self) -> str:
        """Return log level."""
        return self.logging_config.get('level', 'INFO')

    @property
    def log_file(self) -> str:
        """Return log file path."""
        return self.logging_config.get('file', 'logs/scraper.log')

    @property
    def log_max_size_mb(self) -> int:
        """Return max log file size in MB."""
        return self.logging_config.get('max_size_mb', 10)

    @property
    def log_backup_count(self) -> int:
        """Return number of log backups to keep."""
        return self.logging_config.get('backup_count', 3)

    @property
    def rate_limit(self) -> float:
        """Return rate limit in seconds."""
        return self._config.get('rate_limit', 1.0)

    @property
    def request_retries(self) -> int:
        """Return number of retries for requests."""
        return self.request_config.get('retries', 3)

    @property
    def backoff_factor(self) -> float:
        """Return backoff factor for retries."""
        return self.request_config.get('backoff_factor', 1.0)

    @property
    def request_timeout(self) -> int:
        """Return request timeout in seconds."""
        return self.request_config.get('timeout', 30)

    @property
    def scrape_only(self) -> bool:
        """Return whether to only scrape URLs without downloading."""
        return self.download_config.get('scrape_only', False)

    @property
    def validate_url_timeout(self) -> int:
        """Return timeout for URL validation requests in seconds."""
        return self.download_config.get('validate_url_timeout', 10)

    # ========== DISCOVERY CONFIG ==========
    @property
    def discovery_config(self) -> Dict:
        """Return discovery configuration."""
        return self._config.get('discovery', {
            'mode': 'full',
            'max_depth': 0,
            'follow_internal_links': True,
            'follow_external_links': False,
            'extract_from_scripts': True,
            'max_pages_per_collection': 0,
            'respect_robots_txt': False,
            'validate_on_discovery': True,
            'deduplicate': True,
            'dedup_normalize_urls': True,
        })

    @property
    def discovery_mode(self) -> str:
        """Return discovery mode."""
        return self.discovery_config.get('mode', 'full')

    @property
    def discovery_max_depth(self) -> int:
        """Return max depth for deep crawl (0 = unlimited)."""
        return self.discovery_config.get('max_depth', 0)

    @property
    def discovery_validate_on_discovery(self) -> bool:
        """Whether to validate URLs (HEAD request) after discovery."""
        return self.discovery_config.get('validate_on_discovery', True)

    @property
    def discovery_deduplicate(self) -> bool:
        """Whether to deduplicate discovered URLs."""
        return self.discovery_config.get('deduplicate', True)

    @property
    def discovery_follow_internal_links(self) -> bool:
        """Whether to enqueue internal links during discovery."""
        return self.discovery_config.get('follow_internal_links', True)

    @property
    def sitemap_config(self) -> Dict:
        """Return sitemap discovery configuration."""
        return self._config.get('sitemap', {
            'enabled': False,
            'urls': [],
            'follow_sitemap_links': True,
            'max_depth': 3,
            'max_urls': 5000,
            'include_patterns': [],
            'exclude_patterns': [],
        })

    # ========== ANTI-BLOCKING CONFIG ==========
    @property
    def anti_blocking_config(self) -> Dict:
        """Return anti-blocking configuration."""
        return self._config.get('anti_blocking', {})

    @property
    def proxy_enabled(self) -> bool:
        """Whether proxy rotation is enabled."""
        return self.anti_blocking_config.get('proxy', {}).get('enabled', True)

    @property
    def proxy_sources(self) -> List[str]:
        """List of proxy source names to use."""
        return self.anti_blocking_config.get('proxy', {}).get('sources', ['proxifly', 'proxyscraper'])

    @property
    def proxy_refresh_hours(self) -> int:
        """How often to refresh proxy pool in hours."""
        return self.anti_blocking_config.get('proxy', {}).get('refresh_hours', 6)

    @property
    def proxy_min_anonymity(self) -> str:
        """Minimum anonymity level required."""
        return self.anti_blocking_config.get('proxy', {}).get('min_anonymity', 'elite')

    @property
    def proxy_require_https(self) -> bool:
        """Whether to require HTTPS support."""
        return self.anti_blocking_config.get('proxy', {}).get('require_https', False)

    @property
    def proxy_test_before_use(self) -> bool:
        """Whether to test proxies before using them."""
        return self.anti_blocking_config.get('proxy', {}).get('test_before_use', True)

    @property
    def proxy_rotate_per_request(self) -> bool:
        """Whether to rotate proxy for each request."""
        return self.anti_blocking_config.get('proxy', {}).get('rotate_per_request', True)

    @property
    def proxy_rotate_on_error(self) -> bool:
        """Whether to rotate proxy on error (429, 403, etc)."""
        return self.anti_blocking_config.get('proxy', {}).get('rotate_on_error', True)

    @property
    def ua_pool_file(self) -> str:
        """Path to user agents file."""
        return self.anti_blocking_config.get('user_agent', {}).get('pool_file', 'config/user_agents.txt')

    @property
    def ua_rotate_per_session(self) -> bool:
        """Whether to rotate user agent per session."""
        return self.anti_blocking_config.get('user_agent', {}).get('rotate_per_session', True)

    @property
    def ua_rotate_per_request(self) -> bool:
        """Whether to rotate user agent per request."""
        return self.anti_blocking_config.get('user_agent', {}).get('rotate_per_request', False)

    @property
    def behavior_simulate_human(self) -> bool:
        """Whether to simulate human behavior."""
        return self.anti_blocking_config.get('behavior', {}).get('simulate_human', True)

    @property
    def behavior_random_delays_enabled(self) -> bool:
        """Whether to use random delays."""
        return self.anti_blocking_config.get('behavior', {}).get('random_delays', {}).get('enabled', True)

    @property
    def behavior_min_delay(self) -> float:
        """Minimum delay in seconds."""
        return self.anti_blocking_config.get('behavior', {}).get('random_delays', {}).get('min', 1.0)

    @property
    def behavior_max_delay(self) -> float:
        """Maximum delay in seconds."""
        return self.anti_blocking_config.get('behavior', {}).get('random_delays', {}).get('max', 5.0)

    @property
    def behavior_delay_distribution(self) -> str:
        """Delay distribution: uniform, normal, exponential."""
        return self.anti_blocking_config.get('behavior', {}).get('random_delays', {}).get('distribution', 'normal')

    @property
    def behavior_mouse_movements(self) -> bool:
        """Whether to simulate mouse movements."""
        return self.anti_blocking_config.get('behavior', {}).get('mouse_movements', False)

    @property
    def behavior_scrolling(self) -> bool:
        """Whether to simulate scrolling."""
        return self.anti_blocking_config.get('behavior', {}).get('scrolling', False)

    @property
    def rate_limiting_strategy(self) -> str:
        """Rate limiting strategy: fixed, adaptive, stealth."""
        return self.anti_blocking_config.get('rate_limiting', {}).get('strategy', 'adaptive')

    @property
    def rate_limiting_requests_per_minute(self) -> int:
        """Base requests per minute."""
        return self.anti_blocking_config.get('rate_limiting', {}).get('requests_per_minute', 20)

    @property
    def rate_limiting_burst_size(self) -> int:
        """Burst size for rate limiting."""
        return self.anti_blocking_config.get('rate_limiting', {}).get('burst_size', 5)

    @property
    def rate_limiting_backoff_on_429(self) -> bool:
        """Whether to back off on 429 responses."""
        return self.anti_blocking_config.get('rate_limiting', {}).get('backoff_on_429', True)

    @property
    def rate_limiting_max_backoff_seconds(self) -> int:
        """Maximum backoff time in seconds."""
        return self.anti_blocking_config.get('rate_limiting', {}).get('max_backoff_seconds', 300)

    @property
    def rate_limiting_decrease_on_4xx(self) -> bool:
        """Whether to decrease rate on 4xx errors."""
        return self.anti_blocking_config.get('rate_limiting', {}).get('decrease_on_4xx', True)

    @property
    def fingerprint_randomized(self) -> bool:
        """Whether to randomize browser fingerprint."""
        return self.anti_blocking_config.get('fingerprint', {}).get('randomized', True)

    @property
    def fingerprint_rotate_after(self) -> int:
        """Rotate fingerprint after N requests."""
        return self.anti_blocking_config.get('fingerprint', {}).get('rotate_after', 50)

    @property
    def fingerprint_webgl_spoof(self) -> bool:
        """Whether to spoof WebGL."""
        return self.anti_blocking_config.get('fingerprint', {}).get('webgl_spoof', True)

    @property
    def fingerprint_canvas_spoof(self) -> bool:
        """Whether to spoof Canvas."""
        return self.anti_blocking_config.get('fingerprint', {}).get('canvas_spoof', True)

    @property
    def fingerprint_webrtc_leak_protection(self) -> bool:
        """Whether to enable WebRTC leak protection."""
        return self.anti_blocking_config.get('fingerprint', {}).get('webrtc_leak_protection', True)

    @property
    def captcha_auto_detect(self) -> bool:
        """Whether to automatically detect CAPTCHAs."""
        return self.anti_blocking_config.get('captcha', {}).get('auto_detect', True)

    @property
    def captcha_pause_on_captcha(self) -> bool:
        """Whether to pause when CAPTCHA detected."""
        return self.anti_blocking_config.get('captcha', {}).get('pause_on_captcha', True)

    @property
    def captcha_screenshot_on_captcha(self) -> bool:
        """Whether to take screenshot on CAPTCHA."""
        return self.anti_blocking_config.get('captcha', {}).get('screenshot_on_captcha', True)

    @property
    def captcha_manual_solve_timeout(self) -> int:
        """Timeout for manual CAPTCHA solving in seconds."""
        return self.anti_blocking_config.get('captcha', {}).get('manual_solve_timeout', 300)

    # ========== BROWSER CONFIG EXPANDED ==========
    @property
    def random_viewport(self) -> bool:
        """Whether to use random viewport."""
        return self.browser_config.get('random_viewport', True)

    @property
    def viewport_variations(self) -> List[Dict]:
        """List of viewport variations to use."""
        return self.browser_config.get('viewport_variations', [
            {'width': 1920, 'height': 1080},
            {'width': 1366, 'height': 768},
            {'width': 1536, 'height': 864},
            {'width': 1440, 'height': 900},
            {'width': 1600, 'height': 900},
        ])

    # ========== STORAGE CONFIG EXPANDED ==========
    @property
    def session_dir(self) -> str:
        """Directory for session files."""
        return self.storage_config.get('session_dir', 'data/sessions')

    # ========== LOGGING CONFIG EXPANDED ==========
    @property
    def discovery_verbosity(self) -> str:
        """Discovery logging verbosity: QUIET, NORMAL, VERBOSE, DEBUG."""
        return self.logging_config.get('discovery_verbosity', 'NORMAL')

    @property
    def separate_discovery_log(self) -> bool:
        """Whether to use separate log file for discovery."""
        return self.logging_config.get('separate_discovery_log', True)
