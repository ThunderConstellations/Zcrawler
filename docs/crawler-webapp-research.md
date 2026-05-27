# Crawler Webapp Research (Repo Examples + Build Direction)

Goal: evolve Zcrawler into a webapp where users can:

- view business lists and findings
- review previous crawler runs and inquiries
- create custom crawlers from UI inputs
- auto-generate crawler configs/code
- execute crawlers from the webapp
- visualize results in a graphically pleasing way

---

## 1) Strong open-source repo examples

### A) Full crawler management platforms

1. **Crawlab**  
   - Repo: [crawlab-team/crawlab](https://github.com/crawlab-team/crawlab)  
   - What it gives: distributed crawler orchestration, scheduling, worker nodes, logs/results UI, analytics, notifications, code editor.  
   - Stack: Go backend + Vue frontend + MongoDB + worker architecture.  
   - Why it matters: closest existing OSS product to your target “crawler control center” webapp.

2. **Gerapy**  
   - Repo: [Gerapy/Gerapy](https://github.com/Gerapy/Gerapy)  
   - What it gives: Scrapy/Scrapyd management UI with deploy/schedule/control flows.  
   - Stack: Django + Vue + Scrapy + Scrapyd.  
   - Why it matters: proven Python-first dashboard pattern for spider lifecycle.

3. **ScrapydWeb**  
   - Repo: [my8100/scrapydweb](https://github.com/my8100/scrapydweb/)  
   - What it gives: Scrapyd cluster management, log parsing/visualization, alerts, timer tasks.  
   - Why it matters: mature reference for run history + operational UX.

### B) Crawler runtime/tooling frameworks

4. **Crawlee (TypeScript)**  
   - Repo: [apify/crawlee](https://github.com/apify/crawlee)  
   - What it gives: robust crawler runtime for HTTP and browser crawling (Playwright/Puppeteer/Cheerio), queue/retry/proxy patterns.

5. **Crawlee (Python)**  
   - Repo: [apify/crawlee-python](https://github.com/apify/crawlee-python)  
   - What it gives: Python equivalent with Playwright/BeautifulSoup-style handlers.

6. **Crawl4AI**  
   - Repo: [unclecode/crawl4ai](https://github.com/unclecode/crawl4ai)  
   - What it gives: extraction-focused crawler runtime with monitoring/dashboard concepts.

### C) Visual workflow builders (for “custom crawler from UI”)

7. **Open Agent Builder**  
   - Repo: [firecrawl/open-agent-builder](https://github.com/firecrawl/open-agent-builder)  
   - What it gives: node-based visual workflow UX, real-time execution panel, templates.  
   - Why it matters: excellent UX reference for “build crawler without code.”

8. **n8n**  
   - Repo: [n8n-io/n8n](https://github.com/n8n-io/n8n/)  
   - What it gives: visual automation engine with execution history, logs, templates, approvals, integrations.  
   - Caveat: fair-code licensing (not pure OSS like MIT/Apache/GPL).

---

## 2) What to borrow from each (practical)

- **From Crawlab**: multi-run orchestration, scheduler, worker heartbeat, job queue model, run detail pages.
- **From ScrapydWeb/Gerapy**: crawler-focused operational pages (deploy/run/stop/log/export) and concise spider management UX.
- **From Open Agent Builder/n8n**: visual “builder canvas,” templates, form-driven node config, execution timeline.
- **From Crawlee/Crawl4AI**: resilient crawl engine internals (retry, queueing, headless fallback, anti-blocking controls).

---

## 3) Recommended architecture for Zcrawler webapp

### Suggested stack (free/open-source tools)

- **Frontend**: Next.js + TypeScript + Tailwind + component library (shadcn/ui) + charts (ECharts/Recharts) + map (Leaflet).
- **Backend API**: FastAPI (Python) for crawler APIs and orchestration.
- **Crawler runtime**:
  - current OSM/Overpass business crawler as first “template crawler”
  - pluggable adapter interface to support future crawler types (HTTP parser / browser / API crawler).
- **Queue/execution**: Celery + Redis (or RQ) for async jobs and scheduled runs.
- **Database**: Postgres (crawler defs, run metadata, findings index) + object/file storage for raw artifacts.
- **Observability**: structured logs + job metrics + run status stream (WebSocket/SSE).

### Core domain model

- `crawler_templates` (built-in recipes: business list, directory scrape, category crawler)
- `crawler_definitions` (user-created crawlers from forms/canvas)
- `crawl_runs` (status, start/end, logs, failures, trigger source)
- `crawl_findings` (normalized records from each run)
- `saved_inquiries` (user query/search presets and report filters)

---

## 4) Feature blueprint mapped to your request

### A) “look at lists / previously created crawlers / crawl inquiries / findings”

- Dashboard with:
  - latest runs
  - success/failure and duration trends
  - saved crawler definitions
  - saved inquiry filters
- Findings explorer:
  - table + map + chart tabs
  - filtering by distance, category, data quality, has phone/website
  - export CSV/JSON/Markdown

### B) “easily create new custom crawlers”

Two creation modes:

1. **Form Builder (MVP)**
   - source type (OSM, site list, API)
   - seed/query input
   - extraction fields
   - schedule/retry/politeness settings
   - output schema

2. **Visual Builder (Phase 2)**
   - canvas nodes (Source -> Extract -> Enrich -> Filter -> Rank -> Output)
   - branch/if nodes and reusable templates

### C) “automate creation of crawler and run in webapp”

- On save, generate:
  - crawler config JSON (single source of truth)
  - optional Python module from template renderer (Jinja2)
- “Run now” dispatches async job
- run details page streams logs and progress
- artifacts/results attached to run record

### D) “graphically pleasing manner”

- UI views:
  - KPI cards (runs, success rate, avg runtime, record count)
  - trend charts (records/day, failures by reason)
  - map with distance rings from anchor address
  - result quality heatmap (phone/site/hours completeness)

---

## 5) Build strategy (lowest-risk path)

### Phase 1 (1-2 weeks): Management webapp around current crawler

- Add FastAPI service around `scripts/valpo_business_crawler.py`
- Persist runs/results to Postgres
- Build web UI for:
  - create run
  - run history
  - findings table + map
  - export

### Phase 2: Config-driven custom crawler definitions

- Introduce `crawler_definitions` schema
- Form-based custom crawler creation
- Generate config + execute generic runner

### Phase 3: Visual builder + templates

- Add canvas editor for workflows
- add template gallery (“Local business from OSM”, “Directory extraction”, etc.)
- human approval step before first deployment

### Phase 4: Scale + governance

- worker pools
- role-based access control
- policy guardrails (robots/rate limits/source attribution)
- alerts and SLO dashboard

---

## 6) Recommendation: fastest way to get there

Best practical path:

1. Use **your current Python crawler** as the first template.
2. Build a **FastAPI + Next.js** management webapp around it.
3. Copy UX patterns from **Crawlab + ScrapydWeb** for operations.
4. Add a visual builder inspired by **Open Agent Builder** once form-builder is stable.

This gives you immediate value (run tracking + findings UI) without overcommitting to a full orchestration rewrite on day one.

---

## 7) Notes on data/source policy

- Keep Nominatim/OSM usage within policy limits.
- Cache geocoding/reverse-geocoding aggressively.
- Store source IDs and timestamps for auditability.
- Keep an adapter layer so you can add premium providers later without rewriting UI.

