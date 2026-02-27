# Spanish Cendoj Court Sentences Scraper

A comprehensive open-source scraper to systematically download all available PDF court sentences from the Spanish Centro de Documentación Judicial (Cendoj) website.

## Features

- Complete coverage of Cendoj sentence database
- Handles advanced protections (FingerprintJS)
- Reliable and resumable downloads
- Produces a redistributable SQLite database
- Modular architecture for maintainability

## Project Structure

```
cendoj/
├── scraper/              # Main scraping module
│   ├── __init__.py
│   ├── browser.py       # Browser automation with stealth
│   ├── navigator.py     # Site navigation logic
│   ├── downloader.py    # PDF download manager
│   ├── parser.py        # HTML/metadata parser
│   └── models.py        # Data models
├── storage/             # Data storage layer
│   ├── __init__.py
│   ├── database.py      # SQLite operations
│   ├── file_manager.py  # Hierarchical file storage
│   └── schemas.py       # Database schemas
├── utils/               # Utilities
│   ├── __init__.py
│   ├── proxies.py       # Proxy rotation
│   ├── fingerprint.py   # Fingerprint spoofing
│   ├── rate_limiter.py  # Rate limiting
│   └── logger.py        # Logging setup
├── config/              # Configuration
│   ├── __init__.py
│   ├── settings.py      # App settings
│   └── sites.yaml       # Site configurations
├── tests/               # Test suite
├── scripts/             # Utility scripts
├── data/                # Data directory (gitignored)
│   ├── pdfs/           # Downloaded PDFs
│   └── cendoj.db       # Metadata database
├── docs/                # Documentation
├── requirements.txt     # Python dependencies
├── .gitignore
├── README.md
├── LICENSE              # MIT License
├── setup.py
├── pyproject.toml
└── PLAN.md              # Project planning
```

## Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/cendoj-scraper.git
cd cendoj-scraper

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure settings
cp config/settings.example.yaml config/settings.yaml
# Edit config/settings.yaml with your preferences

# Run the scraper
python -m scraper.main

# Or with custom configuration
python -m scraper.main --config config/myconfig.yaml
```

## Configuration

Key configuration options in `config/settings.yaml`:

```yaml
storage:
  base_dir: ./data
  pdf_dir: ./data/pdfs
  database_path: ./data/cendoj.db

browser:
  headless: true
  stealth_mode: true
  timeout: 30000

downloader:
  max_concurrent: 4
  rate_limit: 1.0  # seconds between requests
  retry_attempts: 3
  timeout: 60

proxy:
  enabled: false
  pool_file: config/proxies.txt
  rotate_after: 10

logging:
  level: INFO
  file: logs/scraper.log
  max_size: 10MB
  backup_count: 5
```

## Database Schema

The scraper produces a comprehensive SQLite database with tables for:

- `sentences` - Main sentence metadata
- `collections` - Cendoj collection information
- `pdf_files` - Downloaded PDF file tracking
- `download_log` - Download history and errors
- `search_results` - Search query results

## Legal Considerations

This tool is intended for:
- Academic research
- Legal analysis
- Public interest work
- Open justice initiatives

Users must comply with:
- Spanish law regarding public documents
- Cendoj's terms of service
- Rate limiting to avoid server overload
- Copyright restrictions on commercial use

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a Pull Request

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for details.

## License

MIT License - see [LICENSE](LICENSE) file.

## Disclaimer

This project is not affiliated with the Spanish Judiciary or Cendoj. Use responsibly and in accordance with all applicable laws and regulations.