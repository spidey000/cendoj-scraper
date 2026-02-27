# Cendoj Scraper Implementation Plan

## Project Overview
Build a comprehensive open-source scraper to systematically download all available PDF court sentences from the Spanish Centro de Documentación Judicial (Cendoj) website. Complete coverage, reliable/resumable, redistributable database.

## Architecture Design
- **Language**: Python 3.9+ with asyncio
- **Storage**: SQLite metadata + hierarchical PDF storage (year/collections)
- **Anti-blocking**: Residential/datacenter proxies, IP rotation, realistic browser fingerprinting
- **Modular components**: Browser manager, Navigator, Downloader, Parser, Storage

## Implementation Phases

### Phase 1: Foundation (Current)
- [x] Project scaffolding (README, requirements, pyproject.toml)
- [x] Core models (Sentence, Collection, DownloadResult)
- [x] Browser automation with stealth (playwright-stealth)
- [x] Fingerprint spoofing (FingerprintJS evasion)
- [x] Rate limiting and retry logic
- [x] Logging infrastructure
- [x] CLI entry point with argument parsing
- [ ] **Create PLAN.md documentation** (this file)

### Phase 2: Configuration & Storage (Next)
- [ ] Config module: sites.yaml with site structure, selectors, endpoints
- [ ] Settings loader with environment variable support
- [ ] SQLite database module (schema initialization, CRUD operations)
- [ ] File manager for hierarchical PDF storage
- [ ] Database schemas and migrations

### Phase 3: Core Scraping Logic
- [ ] Navigator: Explore site structure, discover collections and sentences
- [ ] Downloader: Download PDF files with resume support and validation
- [ ] Parser: Extract metadata from HTML pages and PDFs
- [ ] Session state management for resumability

### Phase 4: Orchestration & CLI
- [ ] Main orchestrator class coordinating all components
- [ ] Progress tracking and statistics
- [ ] Error handling and recovery
- [ ] CLI commands: scrape, resume, export, status

### Phase 5: Testing & Documentation
- [ ] Unit tests for each module
- [ ] Integration tests with mocked responses
- [ ] Usage documentation and examples
- [ ] Docker setup (optional)

### Phase 6: Deployment
- [ ] GitHub repository creation
- [ ] Initial commit and push
- [ ] Issues and project board setup

## Technical Decisions

### Browser Automation
- Use Playwright with stealth plugin
- Spoof navigator properties to match real browsers
- Handle Cloudflare/FingerprintJS challenges
- Support headless and headed modes

### Proxy Management
- Support both residential and datacenter proxies
- Automatic IP rotation on failures/rate limits
- Proxy health checking
- Configurable proxy pools from environment or file

### Storage Design
```
database.sqlite
  - sentences (id, collection_id, pdf_number, title, metadata, file_path, downloaded_at, filesize, checksum)
  - collections (id, name, url, parent_id, sentence_count, last_updated)
  - download_sessions (id, started_at, completed_at, total_sentences, success_count, failure_count)

pdf_storage/
  └── {year}/
      └── {collection_code}/
          └── {pdf_number}.pdf
```

### Rate Limiting
- Token bucket algorithm per domain
- Exponential backoff on failures
- Respect robots.txt (if present)
- Configurable delays and bursts

### Error Handling
- Retry with jitter on network errors
- Circuit breaker for persistent failures
- Detailed error logging with context
- Graceful degradation on proxy exhaustion

## Configuration Strategy

### sites.yaml
```yaml
sites:
  - name: "Cendoj"
    base_url: "https://www.cendoj.es"
    endpoints:
      browse: "/contenidos/index.htm"
      sentence: "/contenidos/{year}/{collection}/{pdf_number}.pdf"
    selectors:
      years: "select#formPublicacion option"
      collections: "table.contenidos tr"
      sentences: "table.contenidos tr"
    pagination:
      type: " none"  # or "page_param", "offset", "load_more"
      param: "pagina"
    rate_limits:
      requests_per_second: 2
      burst_size: 5
    proxy_required: true

proxies:
  providers:
    - "datacenter"
    - "residential"
  rotation_policy: "on_failure"  # round_robin, random, on_failure
  max_retries_per_proxy: 3
  cooldown_seconds: 300
```

### Environment Variables
```
PROXY_POOL_FILE=~/.proxy_pool.txt
MAX_CONCURRENT_DOWNLOADS=5
DOWNLOAD_DELAY=1.0
DATABASE_URL=sqlite:///cendoj.db
PDF_STORAGE_PATH=./pdf_storage
LOG_LEVEL=INFO
USER_AGENT_* (for fingerprint customization)
```

## Milestones & Timeline

1. **Week 1**: Configuration, storage, and Navigator module
2. **Week 2**: Downloader and Parser implementation
3. **Week 3**: Orchestrator and CLI, basic testing
4. **Week 4**: Polish, error handling, documentation
5. **Week 5**: Testing, GitHub repo, initial release

## Development Workflow

- [ ] Commit locally after completing each feature or significant change
- [ ] Push to remote repository after each commit
- [ ] Use descriptive commit messages following conventional commits
- [ ] Ensure tests pass before committing

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| IP blocking by Cendoj | High | High | Rotating proxies, realistic delays, fingerprint spoofing |
| Site structure changes | Medium | High | Configurable selectors, easy update process |
| Proxy quality issues | Medium | Medium | Proxy health checks, fallback to datacenter |
| Large storage requirements | High | Medium | Hierarchical storage, checksum validation |
| Rate limiting | High | Medium | Adaptive throttling, exponential backoff |

## Success Criteria

- [ ] 100% coverage of all available PDF sentences from Cendoj
- [ ] Resumable: can restart after interruption without duplicates
- [ ] Reliable: automatic retry, error recovery
- [ ] Redistributable: database format documented and exportable
- [ ] Anti-blocking: uses residential proxies and fingerprint evasion
- [ ] Open source: MIT license, public GitHub repository

## Contact & Questions
Project maintainer: spidey00@gmail.com