import yaml
from typing import Dict, List, Optional

class Config:
    def __init__(self, config_path: str = "config/sites.yaml"):
        self.config_path = config_path
        self._config = self._load_config()
        self._validate_config()

    def _load_config(self) -> dict:
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
        return config

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
