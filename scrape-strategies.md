# Comprehensive Scraping Strategies

This document aggregates every strategy we have identified for safely and thoroughly scraping the Cendoj website and related portals. Each section describes the goal, the core technique, and the required implementation components.

## 1. Sitemap Discovery & Parsing
- **Purpose:** Enumerate every indexable URL exposed through `sitemap.xml` and sitemap indexes.
- **Approach:** Use the `SitemapStrategy` to fetch configured sitemap endpoints, follow nested indexes, and filter URLs by regex patterns (`include_patterns` / `exclude_patterns`).
- **Implementation Notes:**
  - Configuration lives under `sitemap.*` in `config/sites.yaml`.
  - Results feed into the deep crawler seed queue for validation/downloading.

```python
# scraper/strategies/sitemap.py
strategy = SitemapStrategy(config=settings.Config())
await strategy.initialize()
result = await strategy.discover()
print(f'Seed URLs: {len(result.seed_urls)}')
```

## 2. Pattern-Based URL Generation
- **Purpose:** Detect systematic URL structures (year/month directories, sequential Cendoj IDs) and generate exhaustive URL sequences even when links are missing.
- **Approach:**
  - Analyze discovered URLs to infer templates (e.g., `/2024/01/28079-2024-00001.pdf`).
  - Enumerate date ranges and numeric sequences; enqueue generated URLs for validation.
- **Status:** ✅ Implemented. See `scraper/strategies/pattern_generator.py`. The implementation loads existing PDF URLs from the database, identifies numeric sequences in filenames using skeleton templates (replacing the numeric token with `{SEQ}`), then fills gaps between the minimum and maximum sequence values while preserving zero-padding. Includes `include_patterns`/`exclude_patterns` filtering and respects a `max_urls` limit.

```python
# scraper/strategies/pattern_generator.py (implemented)
class PatternGenerator(DiscoveryStrategy):
    name = "pattern_generator"

    async def discover(self) -> StrategyResult:
        urls = await self._load_urls()           # from DB
        filtered = self._filter_urls(urls)
        generated = await self._generate_missing(filtered)
        return StrategyResult(seed_urls=generated, metadata={
            'sample_count': len(filtered),
            'generated_count': len(generated)
        })
```

## 3. Exhaustive Search API Exploration
- **Purpose:** Pull complete historical data beyond the "latest sentences" feed by iterating search parameters.
- **Approach:**
  - Automate POST requests to `search/search.action`, covering jurisdiction × date grids, keyword combinations, and court filters.
  - Respect per-request limits, rotate proxies, and capture CAPTCHA events.
- **Status:** ✅ Implemented. See `scraper/strategies/search_explorer.py`. The implementation iterates over jurisdictions and quarterly date ranges (last 20 years by default), POSTs to the configured search endpoint, and parses PDF URLs from the returned HTML. Results are deduplicated and filtered. Configurable `max_results`, `max_per_request`, and optional include/exclude patterns are respected.

```python
# scraper/strategies/search_explorer.py (implemented)
class SearchExplorer(DiscoveryStrategy):
    name = "search_explorer"

    async def discover(self) -> StrategyResult:
        seeds = []
        for site in self.config.sites:
            api_url = site.get('api', {}).get('search_url')
            jurisdictions = site.get('api', {}).get('jurisdictions', [])
            for jurisdiction in jurisdictions:
                for start, end in self._quarter_ranges():
                    payload = self._build_payload(jurisdiction, start, end)
                    html = await self._post(api_url, payload)
                    seeds.extend(self._parse_html_for_pdfs(html, site['base_url']))
        return StrategyResult(seed_urls=self._filter_urls(seeds))
```

## 4. Taxonomy & Collection Enumeration
- **Purpose:** Reconstruct the website's navigation hierarchy to ensure every collection/year/section is visited.
- **Approach:**
  - Parse navigation menus, tables, and sidebar lists to build a graph of collections.
  - Traverse each node to gather seed URLs for the crawler.
- **Status:** ✅ Implemented. See `scraper/strategies/taxonomy.py`. Uses the shared `BrowserManager` to visit the base URL and extracts links from a wide set of CSS selectors (nav, menus, sidebars, breadcrumbs). Performs a limited BFS (depth 1) on discovered navigation pages to expand coverage. Filters and deduplication are applied, and limits prevent runaway resource use.

```python
# scraper/strategies/taxonomy.py (implemented)
class TaxonomyStrategy(DiscoveryStrategy):
    name = "taxonomy"

    async def discover(self) -> StrategyResult:
        seeds = set()
        for site in self.config.sites:
            base_url = site.get('base_url')
            page = await self.browser_manager.new_page()
            await page.goto(base_url)
            links = await self._extract_links(page, base_url)
            seeds.update(links)
            await page.close()
        return StrategyResult(seed_urls=list(seeds))
```

## 5. Breadcrumb Trail Analysis
- **Purpose:** Understand hierarchical relationships on detail pages to backfill missing parent collections and spot coverage gaps.
- **Approach:**
  - Extract breadcrumbs (`.breadcrumb`, `[aria-label="breadcrumb"]`) during crawling.
  - Map breadcrumb paths to the taxonomy graph for reporting.

```python
# deep crawler utility
def extract_breadcrumbs(html: str) -> list[str]:
    soup = BeautifulSoup(html, 'html.parser')
    return [a.get('href') for a in soup.select('.breadcrumb a, nav.breadcrumb a') if a.get('href')]
```

## 6. Form Discovery & Automated Submission
- **Purpose:** Discover hidden search endpoints and trigger them programmatically.
- **Approach:**
  - Scan pages for `<form>` elements referencing search backends.
  - Submit forms with systematic parameter combinations, handling CSRF tokens and pagination.
- **Status:** ✅ Implemented. See `scraper/strategies/form_discovery.py`. Parses forms, extracts inputs (text, select, checkbox, radio), enumerates parameter combinations (bounded by max_combinations), and extracts PDF URLs from responses.

```python
# scraper/strategies/form_discovery.py (implemented)
class FormDiscoveryStrategy(DiscoveryStrategy):
    name = "form_discovery"
    
    async def discover(self) -> StrategyResult:
        for page_url in self._seed_pages:
            forms = await self._fetch_and_parse_forms(page_url)
            for form in forms:
                pdf_urls = await self._submit_form_and_extract(page_url, form)
                result.seed_urls.extend(pdf_urls)
```

## 7. Network Traffic Interception
- **Purpose:** Detect dynamic JSON/XHR endpoints that serve document lists outside the visible DOM.
- **Approach:**
  - Extend `BrowserManager` session to log `page.on("requestfinished")` traffic.
  - Reverse engineer API shapes and add new strategies or navigator extensions for them.
- **Status:** ✅ Implemented. See `scraper/network_interceptor.py`. Provides `NetworkInterceptor` class that attaches to Playwright pages, captures all requests/responses, and categorizes endpoints (JSON, API, PDF, HTML). Also includes `NetworkInterceptorManager` for managing multiple interceptors.

```python
# scraper/network_interceptor.py (implemented)
interceptor = NetworkInterceptor(capture_json=True, max_requests=1000)
interceptor.attach(page)
# ... crawl pages ...
endpoints = interceptor.extract_endpoints()
# {'json': [...], 'api': [...], 'pdf': [...], 'html': [...]}
```

## 8. Structured Data Extraction
- **Purpose:** Capture machine-readable metadata embedded as JSON-LD/Microdata which may include direct PDF links.
- **Approach:**
  - While crawling, parse `<script type="application/ld+json">` and microdata attributes.
  - Normalize results into `pdf_links` records with high-confidence metadata.
- **Status:** ✅ Implemented. See `scraper/structured_data.py`. Provides `StructuredDataExtractor` for JSON-LD and Microdata extraction, plus `StructuredDataStrategy` wrapper. Extracts PDF links from structured data and relevant metadata (dates, court, case numbers).

```python
# scraper/structured_data.py (implemented)
extractor = StructuredDataExtractor()
structured = extractor.extract(html, source_url)
pdf_links = extractor.extract_pdf_links(structured)
relevant = extractor.extract_relevant_data(structured)
```

## 9. Archive/Legacy Section Detection
- **Purpose:** Identify alternate archive paths (e.g., `/archivos/`, `/historico/`, old domain mirrors) that store unlinked PDFs.
- **Approach:**
  - Use heuristics and HEAD requests against known archive patterns.
  - Monitor DNS/host records for legacy `cendoj.es` mirrors and incorporate them into the config.
- **Status:** ✅ Implemented. See `scraper/strategies/archive_probe.py`. Configurable path templates (`/archivos/{year}`, etc.), iterates over years, probes with HEAD requests, and collects accessible archive URLs.

```python
# scraper/strategies/archive_probe.py (implemented)
class ArchiveProbeStrategy(DiscoveryStrategy):
    name = "archive_probe"
    
    async def discover(self) -> StrategyResult:
        for template in self._path_templates:
            for year in range(self._start_year, current_year + 1):
                url = urljoin(base_url, template.format(year=year))
                if await self._head_ok(url):
                    result.seed_urls.append(url)
```

## 10. Coverage Graph & Gap Analysis
- **Purpose:** Quantify which parts of the site graph have been crawled and highlight missing segments.
- **Approach:**
  - Build a directed graph of visited pages (node attributes include depth, extraction method).
  - Analyze for disconnected subgraphs, missing year ranges, or low branching factors to guide follow-up crawls.
- **Status:** ✅ Implemented. See `scraper/coverage_analyzer.py`. Provides `CoverageGraph` for directed graph management, `CoverageAnalyzer` for gap analysis (disconnected components, orphan nodes, missing years), and snapshot saving.

```python
# scraper/coverage_analyzer.py (implemented)
analyzer = CoverageAnalyzer()
analyzer.build_from_db(session_id)
gaps = analyzer.analyze_gaps()
# {'total_nodes': ..., 'disconnected_components': ..., 'recommendations': [...]}
report = analyzer.generate_report()
```

## 11. Downloader Validation Strategy
- **Purpose:** Ensure discovered PDFs are accessible and deduplicated before download.
- **Approach:**
  - Use HEAD validation (`Downloader.validate_url`) with rate limiting and retries.
  - Track SHA256 checksums, file sizes, and HTTP status for audit trails.
- **Status:** ✅ Already exists in `scraper/downloader.py`. Integrated into `DeepCrawler` via `discovery_validate_on_discovery` config flag. Performs HEAD requests, tracks HTTP status, content-type, content-length.

```python
# scraper/downloader.py (existing)
async def validate_url(self, sentence: Sentence) -> ValidationResult:
    await self.rate_limiter.wait()
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.config.validate_url_timeout)) as session:
        async with session.head(sentence.pdf_url, headers=self._headers()) as response:
            return ValidationResult(...)
```

## 12. Anti-Blocking & Resilience Stack
- **Purpose:** Keep long-running crawls sustainable and respectful.
- **Approach:**
  - Rotate proxies via `ProxyManager`, randomize user agents (`UserAgentPool`), simulate human timing with `BehaviorSimulator`, and detect CAPTCHAs via `CAPTCHAHandler`.
  - Combine adaptive rate limiting with session snapshots for safe pause/resume.
- **Status:** ✅ Fully implemented. Components exist in `utils/` directory: `proxy_manager.py`, `ua_pool.py`, `adaptive_limiter.py`, `behavior_simulator.py`, `captcha_handler.py`, `fingerprint.py`.

```python
# utils/proxy_manager.py usage
proxy = proxy_manager.get_next_proxy('weighted')
headers = {'User-Agent': ua_pool.get()}
response = session.get(url, proxy=proxy.proxy_url, headers=headers, timeout=30)
proxy_manager.mark_result(proxy, success=response.ok, error=None if response.ok else response.status)
```

---

All strategies funnel their discoveries into the `DiscoveryScanner`, which merges seed URLs, hands them to the `DeepCrawler`, and persists findings in `storage/database.py`. Enable or tune each strategy through configuration before running `python cli.py discover`.
