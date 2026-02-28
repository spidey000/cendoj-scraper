# CENDOJ Scraping Strategy

> **Objective:** obtain comprehensive, lawfully sourced access to CENDOJ judicial PDFs (STS and related chambers) while behaving like a responsible white‑hat operator.

---

## 1. Surface Reconnaissance

- **Entry Points**
  - `https://www.poderjudicial.es/search/indexAN.jsp` (browser portal)
  - `https://www.poderjudicial.es/search/search.action` (Ajax backend)
  - Legacy `cendoj.es` mirrors (currently parked; monitor for DNS changes)
  - Open‑data mirrors/Bulk datasets (BOE, datos.gob.es, tribunal websites)
- **Controls & Policies**
  - Record `robots.txt` guidance for each host
  - Document CAPTCHAs (“Control de grandes paginaciones”), authentication rules, and published reuse statements
  - Track anti‑automation layers (rate caps, fingerprint checks)

## 2. Latest Sentences API Harvest

- **Observation**: the JS bundle issues POST `queryLastSentences` calls with parameters `(databasematch=TS, JURISDICCION=<tab>, TIPORESOLUCION=SENTENCIA)`, returning ready‑to‑parse HTML (`li.doc`).
- **Plan**
  1. Warm up session via `indexAN.jsp` (sets cookies/context)
  2. Iterate jurisdictions `[CIVIL, PENAL, contencioso, SOCIAL, MILITAR, ESPECIAL]`
  3. Parse `li.doc > a` for ROJ, PDF link (`openDocument/...`), date, summary
  4. Resolve PDFs via GET (200 response is actual binary) with HEAD retry fallback
  5. Respect `limit_per_jurisdiction` to avoid hitting CAPTCHA thresholds

## 3. Exhaustive Search Crawling

- **Goal**: go beyond the “latest” feed by paginating the full search index.
- **Tactics**
  - Reproduce form submissions (hidden inputs `action=query`, `databasematch`, date/keyword filters)
  - Build a **keyword grid** (e.g., iterate `TEXT` tokens such as year ranges, alphabetical ROJ prefixes, or wildcard patterns) combined with time windows (quarterly, monthly) to keep result sets manageable
  - Paginate using `start`, `recordsPerPage`, `maxresults`, rotating proxies & UA
  - Detect `captcha` responses; back off and queue for manual review

## 4. Deep Archives & Alternate Sources

- **Bulk Releases**: check for official ZIP dumps of historical judgments (2011+). Prefer downloads when available to reduce live traffic.
- **Sitemaps/RSS**: look for `sitemap.xml`, `feed` endpoints, tribunal newsletters that cross‑reference CENDOJ numbers.
- **Cross‑References**: parse BOE or regional gazettes where CENDOJ/ECLI IDs appear, then fetch the canonical PDF.

## 5. PDF Acquisition & Validation

- **Downloader**
  - Async HTTP with resumable writes, SHA256 verification, and content‑length checks
  - HEAD validation before download when running in “validate only” mode
- **Metadata Verification**
  - Extract ECLI/CENDOJ number from PDF text to confirm match with metadata
  - Store jurisdiction, date, ROJ, summary, and source page for auditing

## 6. Storage & Audit Trail

- **Database Schema**
  - `sessions`: crawl metadata, timings, mode (shallow/deep/api)
  - `pdf_links`: URL, normalized URL, source, extraction method/confidence, validation status
  - `errors`: HTTP failures, CAPTCHA triggers, proxy issues
- **State Persistence**
  - Save BFS queues / API offsets for resumable crawls
  - Snapshot config + UA/proxy pools per session

## 7. Risk Mitigation (White‑Hat Discipline)

- Respect published terms of use; if data is restricted, obtain explicit permission.
- Throttle requests (AdaptiveRateLimiter), randomize delays, rotate proxies, and monitor `429/403` to auto‑pause.
- Log every request (timestamp, proxy, UA, endpoint, status) and maintain contact info for reporting issues.

## 8. Execution Roadmap

1. **Finalize Config**: ensure API definitions (as in `config/sites.yaml`) cover all needed jurisdictions.
2. **Implement Search Module**: extend navigator to support full query crawling with CAPTCHA awareness.
3. **Downloader Hardening**: integrate validation+storage pipeline.
4. **Automation Scripts**: cron or workflow to fetch latest feed daily + backlog crawl weekly.
5. **Monitoring**: alerts on parsing failures, HTTP spikes, or schema deltas (e.g., JS bundle hash changes).

This living document should evolve as we discover new endpoints or policy changes. Add notes whenever controls change (new CAPTCHA behavior, rate shifts, etc.) so future crawls stay compliant and effective.

## 9. Strategy Architecture (New)

- Discovery strategies are now pluggable modules loaded by `DiscoveryScanner`.
- Each strategy can emit `seed_urls` (to be crawled) and, in the future, direct `pdf_links`.
- The first concrete strategy is **SitemapStrategy**, which parses XML sitemap trees and feeds discovered URLs into the deep crawler seed queue.
- Enable it via `sitemap.enabled: true` in `config/sites.yaml` and list sitemap endpoints under `sitemap.urls`.
- Strategy lifecycle: initialized during scanner setup, executed once before BFS crawl, cleaned up at shutdown.

> Roadmap: additional strategies (pattern generator, exhaustive search) can plug into the same interface without modifying the orchestrator again.
