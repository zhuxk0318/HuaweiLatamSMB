# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Huawei LATAM SMB Solutions portal — a React SPA showcasing cloud migration, AI, and infrastructure solutions for Latin American SMBs, with an integrated cloud pricing estimator backed by a Python FastAPI agent.

## Commands

### Frontend (React + Vite + TypeScript)
- `npm run dev` — dev server on 0.0.0.0 (proxies `/quote-api` to `localhost:8011`)
- `npm run build` — type-check (`tsc --noEmit`) then Vite build
- `npm run lint` — type-check only (`tsc --noEmit`)
- `npm run preview` — preview production build

### Quote Agent (Python + FastAPI + LangGraph)
- `cd quote-agent && uvicorn app.main:app --reload --port 8011` — run the API server
- `cd quote-agent && python -m pytest tests/ -v` — run all tests
- `cd quote-agent && python -m pytest tests/test_workflow.py::test_parse_rvtools_supports_variants_and_aggregates_disk -v` — run a single test

### Data pipeline
- `npm run export:pricebook` — transpile `src/data/pricingCatalog.ts` into `quote-agent/data/pricing-pricebook.json` (the Python agent reads this JSON at runtime)

## Architecture

### Frontend — Hash-based SPA, no router library

- **Routing**: `App.tsx` reads `window.location.hash` to switch between `home`, `solutionsIndex`, `solution`, and `estimator` views. No React Router.
- **i18n**: Three languages (es/en/zh). `src/data/i18n.ts` holds UI chrome copy; `src/data/solutions.ts` uses `LocalizedPair = { en, es }` for solution content (zh falls back to en). Language persisted in localStorage under `huawei-latam-smb-lang`.
- **Analytics**: `src/analytics.ts` wraps Google Analytics via `VITE_GA_MEASUREMENT_ID` env var. Tracks page views and clicks with route context.
- **Solution data model**: Three `SolutionEntry` objects (ai-maas, cloud-to-cloud, on-prem-to-cloud) each containing `scenarioIds` that reference `SolutionScenario` objects with full sales content (pain points, approach, services, demo skills, integration steps, talk tracks, outcomes).
- **Quote estimator**: `QuoteEstimatorHub` switches between `PricingEstimator` (RVTools .xlsx upload → `/api/quotes/preview`) and `FlexibleQuoteEstimator` (multi-file upload → `/api/quotes/flexible/preview/tasks` async task). Both call the backend at `VITE_QUOTE_API_BASE_URL` (default `/quote-api`, proxied to `localhost:8011` in dev).

### Quote Agent — LangGraph state machines

- **RVTools workflow** (`workflow.py`): Linear LangGraph pipeline: `parse_rvtools → normalize_inventory → load_pricebook → quote_inventory → summarize_quote`. Reads RVTools .xlsx, matches VMs to ECS specs, calculates monthly costs. Optional MaaS enrichment for summary text.
- **Flexible workflow** (`flexible_workflow.py`): More complex pipeline for arbitrary requirement spreadsheets. Stages: `ingest_files → parse_documents → understand_input → extract_requirement_items → normalize_requirements → deduplicate_items → map_to_huawei_product → validate_quote_readiness → return_blockers → resolve_price_components → quote_items → summarize_quote`. Uses LLM (Huawei MaaS) for schema understanding when column mapping isn't obvious.
- **Row quote workflow** (`row_quote_workflow.py`): Annotates an existing customer workbook in-place with Huawei product mapping and pricing columns appended to each sheet.
- **Models** (`models.py`): Pydantic v2 models for all request/response types. Key types: `QuoteRequest`, `QuotePreviewResponse`, `FlexibleQuotePreviewResponse`, `RequirementItem`, `FlexibleQuoteLine`, `PriceComponent`.
- **Pricing** (`pricebook.py`, `flexible_pricing.py`): Both load from JSON catalogs under `quote-agent/data/`. The RVTools pricebook comes from `pricing-pricebook.json` (exported from the TS catalog). The flexible catalog comes from `flexible-pricing-catalog.json`.
- **Async tasks** (`flexible_preview_tasks.py`, `row_quote_tasks.py`): In-memory task queues for long-running flexible/annotate operations. Poll via GET endpoints.

### Data flow: TS pricing catalog → Python pricebook

`src/data/pricingCatalog.ts` is the source of truth for ECS/EVS pricing. The script `scripts/export-pricing-catalog.mjs` transpiles and evaluates it (using Node `vm` module), writing the result to `quote-agent/data/pricing-pricebook.json`. Run this script whenever the TS catalog changes.

## Key conventions

- The site language defaults to Spanish (`es`). All UI copy must include es and en at minimum.
- `LocalizedPair` in solutions data is `{ en, es }` only — zh users see the `en` version via `textFor()`.
- The Python agent has no database; all pricing is read from static JSON files loaded at startup with `lru_cache`.
- Tests use `monkeypatch` to replace `_maas_understanding` with deterministic fakes, avoiding real LLM calls.
- The flexible pricing catalog (`quote-agent/data/flexible-pricing-catalog.json`) is maintained separately from the TS catalog — it covers a broader product set (ECS, EVS, CBR, EIP, CCE, SFS Turbo, NAT Gateway, VPN, Direct Connect, RDS).
