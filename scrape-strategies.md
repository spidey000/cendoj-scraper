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
- **Status:** Planned. Implement as `scraper/strategies/pattern_generator.py` using regex grouping and heuristics for parameter detection.

```python
# scraper/strategies/pattern_generator.py (planned)
class PatternGenerator(DiscoveryStrategy):
    name = "pattern_generator"

    async def discover(self) -> StrategyResult:
        urls = self._load_samples()
        patterns = self._infer_patterns(urls)
        generated = self._enumerate_sequences(patterns)
        return StrategyResult(seed_urls=generated, metadata={"patterns": patterns})
```

## 3. Exhaustive Search API Exploration
- **Purpose:** Pull complete historical data beyond the “latest sentences” feed by iterating search parameters.
- **Approach:**
  - Automate POST requests to `search/search.action`, covering jurisdiction × date grids, keyword combinations, and court filters.
  - Respect per-request limits, rotate proxies, and capture CAPTCHA events.
- **Status:** Planned. Will become a strategy that emits both seed URLs and direct PDF records when HTML responses already contain download links.

```python
# scraper/strategies/search_explorer.py (planned)
class SearchExplorer(DiscoveryStrategy):
    async def discover(self) -> StrategyResult:
        seeds = []
        api = self.config.sites[0]['api']
        for jurisdiction in api['jurisdictions']:
            for start, end in self._quarter_ranges():
                payload = self._build_payload(jurisdiction, start, end)
                html = await self._post(api['search_url'], payload)
                seeds.extend(self._parse_results(html))
        return StrategyResult(seed_urls=seeds)
```

## 4. Taxonomy & Collection Enumeration
- **Purpose:** Reconstruct the website’s navigation hierarchy to ensure every collection/year/section is visited.
- **Approach:**
  - Parse navigation menus, tables, and sidebar lists to build a graph of collections.
  - Traverse each node to gather seed URLs for the crawler.
- **Status:** Planned; will leverage Playwright/BrowserManager to fetch and parse DOM trees.

```python
# scraper/strategies/taxonomy.py (planned)
class TaxonomyStrategy(DiscoveryStrategy):
    async def discover(self) -> StrategyResult:
        seeds = []
        for site in self.config.sites:
            page = await self.browser_manager.new_page()
            await page.goto(site['base_url'])
            links = await page.locator('nav a, .menu a').all()
            for link in links:
                href = await link.get_attribute('href')
                if href:
                    seeds.append(urljoin(site['base_url'], href))
            await page.close()
        return StrategyResult(seed_urls=list(dict.fromkeys(seeds)))
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

```python
# scraper/strategies/form_discovery.py (planned)
for form in soup.find_all('form'):
    action = urljoin(base_url, form.get('action', ''))
    base_payload = {inp.get('name'): inp.get('value', '') for inp in form.find_all('input') if inp.get('name')}
    for overrides in self._enumerate_parameter_sets(form):
        response = session.post(action, data={**base_payload, **overrides})
        self._process_html(response.text)
```

## 7. Network Traffic Interception
- **Purpose:** Detect dynamic JSON/XHR endpoints that serve document lists outside the visible DOM.
- **Approach:**
  - Extend `BrowserManager` session to log `page.on("requestfinished")` traffic.
  - Reverse engineer API shapes and add new strategies or navigator extensions for them.

```python
# scraper/browser.py (planned hook)
page.on('requestfinished', lambda request: self.logger.debug("XHR {request.url}"))
page.on('response', lambda response: asyncio.create_task(self._capture_json(response)))

async def _capture_json(self, response):
    if 'application/json' in (response.headers.get('content-type') or ''):
        data = await response.json()
        self.discovery_bus.publish('json_endpoint', {'url': response.url, 'payload': data})
```

## 8. Structured Data Extraction
- **Purpose:** Capture machine-readable metadata embedded as JSON-LD/Microdata which may include direct PDF links.
- **Approach:**
  - While crawling, parse `<script type="application/ld+json">` and microdata attributes.
  - Normalize results into `pdf_links` records with high-confidence metadata.

```python
# structured data helper
def extract_structured_data(html: str) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    payloads = []
    for node in soup.select('script[type="application/ld+json"]'):
        payloads.append(json.loads(node.string))
    return payloads
```

## 9. Archive/Legacy Section Detection
- **Purpose:** Identify alternate archive paths (e.g., `/archivos/`, `/historico/`, old domain mirrors) that store unlinked PDFs.
- **Approach:**
  - Use heuristics and HEAD requests against known archive patterns.
  - Monitor DNS/host records for legacy `cendoj.es` mirrors and incorporate them into the config.

```python
# archive probing snippet
for pattern in ['/archivos/{year}', '/historico/{year}']:
    for year in range(2000, datetime.now().year + 1):
        url = urljoin(site['base_url'], pattern.format(year=year))
        if await self._head_ok(url):
            seeds.append(url)
```

## 10. Coverage Graph & Gap Analysis
- **Purpose:** Quantify which parts of the site graph have been crawled and highlight missing segments.
- **Approach:**
  - Build a directed graph of visited pages (node attributes include depth, extraction method).
  - Analyze for disconnected subgraphs, missing year ranges, or low branching factors to guide follow-up crawls.

```python
# scraper/coverage_analyzer.py (planned)
class CoverageAnalyzer:
    def __init__(self):
        self.graph: dict[str, set[str]] = {}

    def add_edge(self, source: str, target: str):
        self.graph.setdefault(source, set()).add(target)

    def frontier(self):
        return [node for node, edges in self.graph.items() if not edges]
```

## 11. Downloader Validation Strategy
- **Purpose:** Ensure discovered PDFs are accessible and deduplicated before download.
- **Approach:**
  - Use HEAD validation (`Downloader.validate_url`) with rate limiting and retries.
  - Track SHA256 checksums, file sizes, and HTTP status for audit trails.

```python
# scraper/downloader.py
async def validate_url(self, sentence: Sentence) -> ValidationResult:
    await self.rate_limiter.wait()
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.config.validate_url_timeout)) as session:
        async with session.head(sentence.pdf_url, headers=self._headers()) as response:
            return ValidationResult(
                sentence_id=sentence.id,
                accessible=response.status == 200,
                status_code=response.status,
                content_type=response.headers.get('Content-Type'),
            )
```

## 12. Anti-Blocking & Resilience Stack
- **Purpose:** Keep long-running crawls sustainable and respectful.
- **Approach:**
  - Rotate proxies via `ProxyManager`, randomize user agents (`UserAgentPool`), simulate human timing with `BehaviorSimulator`, and detect CAPTCHAs via `CAPTCHAHandler`.
  - Combine adaptive rate limiting with session snapshots for safe pause/resume.

```python
# utils/proxy_manager.py usage
proxy = proxy_manager.get_next_proxy('weighted')
headers = {'User-Agent': ua_pool.get()}
response = session.get(url, proxy=proxy.proxy_url, headers=headers, timeout=30)
proxy_manager.mark_result(proxy, success=response.ok, error=None if response.ok else response.status)
```

---

All strategies funnel their discoveries into the `DiscoveryScanner`, which merges seed URLs, hands them to the `DeepCrawler`, and persists findings in `storage/database.py`. Enable or tune each strategy through configuration before running `python cli.py discover`.
