# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Huawei LATAM SMB Solutions portal — a React SPA showcasing cloud migration, AI, and infrastructure solutions for Latin American SMBs, with an integrated cloud pricing estimator and conversational chat portal backed by a Python FastAPI agent.

## Commands

### Frontend (React + Vite + TypeScript)
- `npm run dev` — dev server on 0.0.0.0 (proxies `/quote-api` to `localhost:8011`)
- `npm run build` — type-check (`tsc --noEmit`) then Vite build
- `npm run lint` — type-check only (`tsc --noEmit`)
- `npm run preview` — preview production build

### Quote Agent (Python + FastAPI + LangGraph)
- `cd quote-agent && uvicorn app.main:app --reload --port 8011` — run the API server
- `cd quote-agent && python -m pytest tests/ -v` — run all tests
- `cd quote-agent && python -m pytest tests/test_workflow.py::test_function_name -v` — run a single test

### Data pipeline
- `npm run export:pricebook` — transpile `src/data/pricingCatalog.ts` into `quote-agent/data/flexible-pricing-catalog.json` (the Python agent reads this JSON at runtime). Run this whenever the TS catalog changes.

### Asset pipeline
- `node scripts/cache-huawei-images.mjs` — pre-cache Huawei CDN images used in the site

### Deployment
- `scripts/publish-static-site.sh` — builds the frontend and rsyncs `dist/` to `/var/www/huawei-latam-smb-site`

## Code Reading Rules

- Do not read the whole repository or recursively open many files at once.
- Start with narrow discovery: prefer `rg`, `rg --files`, `fd`, `ls`, and `tree -L 2` to locate relevant files before opening them.
- Read only the files directly related to the task. Default to at most 3 files per exploration round.
- Do not read full large files unless strictly necessary. If a file is longer than 300 lines, read only the relevant chunk first.
- Prefer targeted reads around matching symbols, functions, classes, routes, or error sites instead of full-file reads.
- When using `sed`, `awk`, or similar tools, read small ranges first, typically 80-150 lines at a time.
- After each exploration round, summarize findings in 5-10 lines before reading more files.
- Avoid re-reading the same file from the top if only one later section is needed.
- If the task scope is unclear, ask which module or feature to inspect instead of scanning unrelated directories.
- For repo entrypoint discovery, prefer this order: `package.json`, `src/App.tsx`, relevant `src/components/*`, `quote-agent/app/main.py`, then the specific module implicated by the task.
- Treat `quote-agent/vendor/` and generated artifacts as low-priority unless the task explicitly involves them.
- If context usage starts growing quickly, stop reading new files and switch to a short working summary plus a focused next lookup.

### Extra rules for HLD tasks

- For HLD-only tasks, do not inspect unrelated frontend, chat, pricing, CDN, or deployment modules.
- For HLD-only tasks, start with this exact order unless blocked:
  1. `quote-agent/app/hld_workflow.py`
  2. `quote-agent/app/hwc_drawio_library.py`
  3. `quote-agent/app/hwc_icon_mapping.py`
  4. the most focused HLD test file only
- Do not open the entire `quote-agent/tests/` tree for HLD work.
- Do not read image files as base64, OCR, or binary dumps. If reference images are relevant, treat their intended rules as user-provided constraints unless visual inspection is absolutely necessary.
- For layout/debugging tasks, inspect at most one fresh generated `.drawio` and one fresh generated `.png` before editing code.
- For HLD rendering fixes, prefer changing deterministic renderer/layout code over prompt wording whenever the issue is overlap, spacing, routing, icon placement, or container sizing.
- If an HLD task mentions icons, first verify whether the issue is:
  - icon resolution/mapping
  - draw.io export compatibility
  - layout overlap
  before broadening scope.

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `VITE_GA_MEASUREMENT_ID` | — | Google Analytics measurement ID |
| `VITE_QUOTE_API_BASE_URL` | `/quote-api` | Base URL for the quote/chat API (Vite dev proxy strips this prefix and forwards to `localhost:8011`) |

### Backend (Python agent)

| Variable | Default | Purpose |
|---|---|---|
| `HUAWEI_MAAS_API_KEY` | — | Huawei MaaS API key for chat/LLM calls |
| `HUAWEI_MAAS_BASE_URL` | — | Huawei MaaS base URL for chat completions |
| `HUAWEI_MAAS_MODEL` | — | Huawei MaaS model identifier |
| `SEARXNG_BASE_URL` | `http://127.0.0.1:8888` | SearXNG instance URL for web search |
| `ROW_QUOTE_MAAS_BATCH_SIZE` | `3` | Batch size for concurrent MaaS calls in row-quote |
| `ROW_QUOTE_MAAS_CONCURRENCY` | `6` | Per-task concurrency limit for MaaS calls |
| `ROW_QUOTE_MAAS_GLOBAL_CONCURRENCY` | `12` | Process-wide concurrency limit across all row-quote tasks |
| `ROW_QUOTE_MAAS_TIMEOUT_SECONDS` | `120` | Timeout for MaaS calls in row-quote |
| `ROW_QUOTE_MAAS_MAX_RETRIES` | `1` | Max retries for MaaS calls in row-quote |

**HLD design** requires `drawio` (or `draw.io`) on PATH for PNG export. Vendor resources are in `quote-agent/vendor/drawio-skill/`. PNG export runs as non-root user `hld-render` via `preexec_fn` with xvfb on Linux.

## Architecture

### Frontend — Hash-based SPA, no router library

- **Routing**: `App.tsx` reads `window.location.hash` to switch between `home`, `solutionsIndex`, `solution`, `estimator`, `migration`, and `hld` views. No React Router. Both `home` and `hld` render `ChatPortal` (no header/footer); other routes wrap content in `SiteHeader`/`SiteFooter`.
- **Chat portal**: `ChatPortal.tsx` is the default home view — a conversational UI that connects to `/api/chat/sessions` and `/api/chat/sessions/{id}/messages/stream` (SSE). Supports file uploads and card actions (route navigation, upload triggers, suggested prompts). Also hosts `HldDesignWizard` and `HldDesignResultCard` inline.
- **HLD Design Wizard**: `HldDesignWizard.tsx` — multi-step form collecting architecture requirements (project name, business goal, architecture boundary, deployment mode, user access, core components, external integrations, data stores, network/security, filename). Fetches rule-based+LLM recommendations from `/api/hld/designs/recommendations`, submits to `/api/hld/designs` (async task), polls status, then renders result via `HldDesignResultCard.tsx` (PNG preview + download for PNG/.drawio).
- **Migration Explorer**: `MigrationExplorer.tsx` — dedicated page filtering solution scenarios by migration-specific IDs (cloud-database-migration, bi-data-platform-migration, sap-erp-on-cloud, backup-dr-security, workspace-vmware-migration).
- **Healthcare Solution**: `HealthcareSolutionPage.tsx` — dedicated enterprise healthcare solution page.
- **i18n**: Three languages (es/en/zh). `src/data/i18n.ts` holds UI chrome copy; `src/data/solutions.ts` uses `LocalizedPair = { en, es }` for solution content (zh falls back to en). Language persisted in localStorage under `huawei-latam-smb-lang`.
- **Analytics**: `src/analytics.ts` wraps Google Analytics via `VITE_GA_MEASUREMENT_ID` env var. Tracks page views and clicks with route context.
- **Solution data model**: Four `SolutionEntry` objects (ai-maas, cloud-to-cloud, on-prem-to-cloud, enterprise) each containing `scenarioIds` that reference `SolutionScenario` objects with full sales content (pain points, approach, services, demo skills, integration steps, talk tracks, outcomes).
- **Quote estimator**: `QuoteEstimatorHub` switches between `PricingEstimator` (RVTools .xlsx upload → `/api/quotes/preview`) and `FlexibleQuoteEstimator` (multi-file upload → `/api/quotes/flexible/preview/tasks` async task). Both call the backend at `VITE_QUOTE_API_BASE_URL`.

### Quote Agent — LangGraph state machines

- **Chat service** (`chat_service.py`): Manages conversational sessions with file context. Parses uploaded files (PDF, DOCX, XLSX, CSV) into text, builds a prompt with up to `CHAT_INPUT_TOKEN_BUDGET` (160k) tokens, and streams responses from Huawei MaaS via SSE.
- **Web search** (`web_search.py`): SearXNG client for RAG-style web search context. Queries a local SearXNG instance (default `http://127.0.0.1:8888`), preferring Huawei official domains (`huaweicloud.com`, `support.huaweicloud.com`, `developer.huaweicloud.com`).
- **Chat mock** (`chat_mock.py`): Standalone mock session data for testing chat without a live MaaS connection.
- **RVTools workflow** (`workflow.py`): Linear LangGraph pipeline: `parse_rvtools → normalize_inventory → load_pricebook → quote_inventory → summarize_quote`. Reads RVTools .xlsx, matches VMs to ECS specs, calculates monthly costs. Optional MaaS enrichment for summary text.
- **Flexible workflow** (`flexible_workflow.py`): More complex pipeline for arbitrary requirement spreadsheets. Stages: `ingest_files → parse_documents → understand_input → extract_requirement_items → normalize_requirements → deduplicate_items → map_to_huawei_product → validate_quote_readiness → return_blockers → resolve_price_components → quote_items → summarize_quote`. Uses LLM (Huawei MaaS) for schema understanding when column mapping isn't obvious.
- **Row quote workflow** (`row_quote_workflow.py`): Annotates an existing customer workbook in-place with Huawei product mapping and pricing columns appended to each sheet.
- **Models** (`models.py`): Pydantic v2 models for all request/response types. Key types: `QuoteRequest`, `QuotePreviewResponse`, `FlexibleQuotePreviewResponse`, `RequirementItem`, `FlexibleQuoteLine`, `PriceComponent`, `ChatMessage`, `ChatSessionResponse`.
- **Pricing** (`pricebook.py`, `flexible_pricing.py`): Both load from the single catalog file `quote-agent/data/flexible-pricing-catalog.json`. `pricebook.py` rebuilds an RVTools-compatible pricebook structure from the unified catalog; `flexible_pricing.py` loads `PriceComponent` items directly with query filters.
- **Async tasks** (`flexible_preview_tasks.py`, `row_quote_tasks.py`, `hld_tasks.py`): In-memory task queues for long-running flexible/annotate/HLD operations. Thread-safe with TTL expiry (1800s). Poll via GET endpoints; cancel via POST `/cancel`.
- **HLD workflow** (`hld_workflow.py`): Generates architecture diagrams. Pipeline: structured requirements → LLM generates architecture spec JSON (constrained: max 15 nodes, 20 edges, 30-char labels) → deterministic render to `.drawio` XML → draw.io CLI exports PNG (via xvfb, `EXPORT_SEMAPHORE` limits concurrency to 2) → PNG repair. One retry on spec parse failure. Vendor resources (styles, references, scripts) loaded from `quote-agent/vendor/drawio-skill/`.
- **HLD recommendations** (`hld_recommend.py`): Rule-based wizard step recommendations (architecture boundary, user access, core components, data stores, network/security, external integrations, filename) with LLM fallback. All recommendations are trilingual (en/es/zh).

### HLD rendering status and current working assumptions

- Huawei Cloud icon vendor path is:
  - `quote-agent/vendor/hwc-drawio-libraries/color/`
- The icon pipeline is already integrated into the backend. Current HLD work should assume:
  - icon mapping exists
  - icon rendering exists
  - the main remaining class of problems is often layout/spacing/routing, not missing icon assets
- Current HLD layout goals:
  - no node overlap inside a container
  - icon + label treated as one layout unit
  - container size expands from content
  - logical groups (`AZ`, `AS Group`, `AS Policy`) keep visible inner padding
  - orthogonal edges should avoid crossing node centers when practical
- For layout changes, keep scope in the backend renderer. Do not redesign the HLD wizard unless the task explicitly asks for it.

### Current HLD fix target: DR site did not become 2AZ

- Current confirmed issue:
  - a user mentioned `disaster recovery site`, but the generated HLD did not produce `AZ1/AZ2` or equivalent two-AZ DR topology
  - instead, the latest generated `.drawio` showed `DR Replication` self-loop edges on individual nodes
- Treat this as a backend HLD generation/spec-validation problem first, not a frontend problem and not primarily a renderer/layout problem.
- Start with the smallest relevant context only:
  1. `quote-agent/app/hld_workflow.py`
  2. one fresh generated `.drawio` under `/tmp/hld-designs/`
  3. the most focused HLD test file you need
- Working hypothesis:
  - prompt/schema currently allows `replication` edges for DR but does not require `az` containers or two-site structure when requirements mention DR/HA/standby/secondary site
  - parse/validation may also collapse container-level DR edges into node-level self-loops
- For this issue, prefer fixes in this order:
  1. strengthen backend spec-generation constraints in `hld_workflow.py`
  2. add/adjust backend validation or normalization so DR requirements map to explicit multi-AZ structure
  3. add focused tests proving DR keywords yield 2AZ-style containers and no self-loop replication edges
- Do not broaden into chat portal, pricing, deployment, or unrelated frontend cleanup.
- If online verification is needed after backend changes, remember the backend service must be restarted.

### API endpoints

**Chat**
- `POST /api/chat/sessions` — create session
- `GET /api/chat/sessions/{id}` — get session
- `POST /api/chat/uploads` — upload files (PDF, DOCX, XLSX, CSV)
- `POST /api/chat/sessions/{id}/messages/stream` — stream chat response (SSE)

**RVTools quote**
- `POST /api/quotes/preview` — sync preview from RVTools .xlsx
- `POST /api/quotes/export` — export quoted workbook

**Flexible quote**
- `POST /api/quotes/flexible/preview` — sync flexible preview
- `POST /api/quotes/flexible/preview/tasks` — async flexible preview task
- `GET /api/quotes/flexible/preview/tasks/{id}` — poll flexible preview task
- `POST /api/quotes/flexible/review` — review/edit quoted items
- `POST /api/quotes/flexible/export` — export flexible workbook

**Row quote (annotate)**
- `POST /api/quotes/flexible/annotate/tasks` — async annotate task
- `GET /api/quotes/flexible/annotate/tasks/{id}` — poll annotate task
- `GET /api/quotes/flexible/annotate/tasks/{id}/export` — download annotated workbook
- `POST /api/quotes/flexible/annotate/tasks/{id}/cancel` — cancel running annotate task

**HLD design**
- `POST /api/hld/designs/recommendations` — get wizard step recommendation (rule-based + optional LLM)
- `POST /api/hld/designs` — create HLD design task (async)
- `GET /api/hld/designs/{design_id}` — poll task status (stages: queued → validate_cli → generate_spec → parse_spec → render_drawio → export_png → repair_png → completed)
- `GET /api/hld/designs/{design_id}/artifacts/png` — download PNG
- `GET /api/hld/designs/{design_id}/artifacts/drawio` — download .drawio XML

**Catalog**
- `GET /api/flexible-pricing/catalog` — query pricing catalog (optional `product`, `region` filters)

### Data flow: TS pricing catalog → Python pricebook

`src/data/pricingCatalog.ts` is the source of truth for ECS/EVS pricing. The script `scripts/export-pricing-catalog.mjs` transpiles and evaluates it (using Node `vm` module), converts ECS/EVS items to the unified JSON schema, preserves existing non-ECS/EVS items (CBR, EIP, CCE, etc.), and writes the merged result to `quote-agent/data/flexible-pricing-catalog.json`. Both `pricebook.py` and `flexible_pricing.py` read from this same file.

## Key conventions

- The site language defaults to Spanish (`es`). All UI copy must include es and en at minimum.
- `LocalizedPair` in solutions data is `{ en, es }` only — zh users see the `en` version via `textFor()`.
- The Python agent has no database; all pricing is read from static JSON files loaded at startup with `lru_cache`. Chat sessions and uploads are stored in-memory (thread-safe with `_lock`).
- Tests use `monkeypatch` to replace `_maas_understanding` with deterministic fakes, avoiding real LLM calls.
- The flexible pricing catalog (`quote-agent/data/flexible-pricing-catalog.json`) is the single pricing data file. It contains ECS/EVS items (exported from the TS catalog) plus a broader product set (CBR, EIP, CCE, SFS Turbo, NAT Gateway, VPN, Direct Connect, RDS, DDS, DWS, OBS, ELB, WAF, and more) maintained directly in JSON.
- `CLAUDE_HANDOFF.md` at repo root is used for cross-session continuity — stores in-progress goals, completed steps, and next actions in Chinese. Read it at session start when resuming work.

## Vendor resources

- `quote-agent/vendor/drawio-skill/` — draw.io style templates, reference architectures, and helper scripts used by the HLD workflow. These are vendored (not npm/pip packages) and loaded at runtime by `hld_workflow.py`.
