# Internet Radar V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working Internet Radar v2 app from `/Users/deepakkudi23/Downloads/INTERNET_RADAR_V2_ARCHITECTURE.md` with local-first intelligence, real no-key collectors, a Streamlit dashboard, tests, and GitHub-pushed commits.

**Architecture:** Implement a Python package with collectors, signal validation, scoring, storage, LLM routing, alerts, scheduler, and dashboard modules. Keep keyed or brittle sources registered but disabled by default, while live no-key sources power an end-to-end dashboard and test suite without secrets.

**Tech Stack:** Python 3.12, Streamlit, requests, pydantic, PyYAML, pandas, SQLite, pytest, local Ollama if available.

---

### Task 1: Project Skeleton And Tests

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `README.md`
- Create: `.env.example`
- Create: `tests/test_core_pipeline.py`
- Create: `tests/test_dashboard_smoke.py`

- [ ] **Step 1: Write failing tests**

Create tests that import `internet_radar.pipeline.run_radar_once`, `internet_radar.sources.registry.SOURCE_REGISTRY`, dashboard helpers, scorers, and the Ollama router. The expected initial failure is `ModuleNotFoundError: No module named 'internet_radar'`.

- [ ] **Step 2: Verify red**

Run: `uv run --python 3.12 pytest -q`
Expected: collection fails because the package does not exist yet.

- [ ] **Step 3: Add packaging metadata**

Define dependencies and scripts:
- `internet-radar-run = internet_radar.cli:main`
- `streamlit run dashboard/app.py` documented in README
- Python requirement `>=3.11,<3.14`

- [ ] **Step 4: Run tests**

Run: `uv run --python 3.12 pytest -q`
Expected: failures move from missing package to missing implementation.

### Task 2: Core Models, Source Registry, And Storage

**Files:**
- Create: `internet_radar/storage/models.py`
- Create: `internet_radar/storage/db.py`
- Create: `internet_radar/storage/cache.py`
- Create: `internet_radar/sources/registry.py`
- Create: `config/sources.yaml`
- Create: `config/interests.yaml`

- [ ] **Step 1: Write failing behavior tests**

Tests verify:
- at least 64 source definitions exist
- source records have category, cost, auth requirement, default status, and reliability level
- `SignalRecord` normalizes topic/source/category/score/timestamp
- SQLite storage can upsert and list signals without duplicate IDs

- [ ] **Step 2: Verify red**

Run: `uv run --python 3.12 pytest tests/test_core_pipeline.py -q`
Expected: model and registry imports fail.

- [ ] **Step 3: Implement minimal models and storage**

Use pydantic models for source definitions, signal records, user profile, and briefing payloads. Use SQLite with an idempotent schema and no mandatory external service.

- [ ] **Step 4: Verify green for storage and registry tests**

Run: `uv run --python 3.12 pytest tests/test_core_pipeline.py -q`
Expected: storage and registry tests pass.

### Task 3: Collectors And Radar Pipeline

**Files:**
- Create: `internet_radar/collectors/base.py`
- Create: `internet_radar/collectors/live.py`
- Create: `internet_radar/pipeline.py`
- Create package folders matching the architecture: `collectors/`, `signals/`, `brain/`, `scoring/`, `alerts/`, `scheduler/`

- [ ] **Step 1: Write failing collector tests**

Tests use fake HTTP payloads for GitHub trending/search, Reddit JSON, Hacker News, Dev.to, RemoteOK, arXiv, PyPI, npm, and RSS so no network is required.

- [ ] **Step 2: Verify red**

Run: `uv run --python 3.12 pytest tests/test_core_pipeline.py -q`
Expected: collectors or pipeline functions missing.

- [ ] **Step 3: Implement live no-key collectors**

Implement resilient collectors for:
- GitHub search/trending via public API or HTML fallback
- Reddit JSON
- Hacker News top stories and Algolia search
- Dev.to
- RemoteOK
- arXiv
- PyPI package metadata
- npm package metadata
- RSS feeds

Each collector returns `SignalRecord` objects and degrades to bundled sample data if the network fails.

- [ ] **Step 4: Verify pipeline tests**

Run: `uv run --python 3.12 pytest tests/test_core_pipeline.py -q`
Expected: fake collector and fallback tests pass.

### Task 4: Signals, Scoring, And Local LLM

**Files:**
- Create: `internet_radar/signals/cross_source_validator.py`
- Create: `internet_radar/signals/deduplicator.py`
- Create: `internet_radar/signals/velocity_engine.py`
- Create: `internet_radar/scoring/master_scorer.py`
- Create: `internet_radar/brain/local_llm.py`
- Create: `internet_radar/brain/llm_router.py`
- Create: `internet_radar/brain/prompts.py`

- [ ] **Step 1: Write failing tests**

Tests verify cross-source phases, duplicate removal, trend scoring, hackathon/internship/startup scoring bounds, Ollama model selection, and deterministic fallback when Ollama is unavailable.

- [ ] **Step 2: Verify red**

Run: `uv run --python 3.12 pytest tests/test_core_pipeline.py -q`
Expected: missing signal/scoring/brain modules.

- [ ] **Step 3: Implement formulas from the architecture**

Use the supplied scoring formulas where data exists. Keep optional fields defensive so partial external records do not crash the app.

- [ ] **Step 4: Verify LLM and scoring tests**

Run: `uv run --python 3.12 pytest tests/test_core_pipeline.py -q`
Expected: all core tests pass.

### Task 5: Dashboard, Alerts, Scheduler, And CLI

**Files:**
- Create: `dashboard/app.py`
- Create: `dashboard/pages/00_briefing.py` through `dashboard/pages/12_profile.py`
- Create: `internet_radar/dashboard_data.py`
- Create: `internet_radar/cli.py`
- Create: `internet_radar/alerts/alert_manager.py`
- Create: `internet_radar/alerts/ntfy_notifier.py`
- Create: `internet_radar/scheduler/jobs.py`
- Create: `internet_radar/scheduler/runner.py`

- [ ] **Step 1: Write failing dashboard smoke tests**

Tests verify dashboard data can render all 13 page keys and that the Streamlit app file imports without executing network-only code.

- [ ] **Step 2: Verify red**

Run: `uv run --python 3.12 pytest tests/test_dashboard_smoke.py -q`
Expected: dashboard modules missing.

- [ ] **Step 3: Implement dashboard and runtime commands**

Build Streamlit tabs/pages for all architecture pages. Show live pipeline output, active source counts, score cards, source health, search, profile config, and an LLM status panel.

- [ ] **Step 4: Verify dashboard smoke**

Run: `uv run --python 3.12 pytest tests/test_dashboard_smoke.py -q`
Expected: smoke tests pass.

### Task 6: End-To-End Verification And Cleanup

**Files:**
- Modify only generated app files, tests, lockfiles, and docs.

- [ ] **Step 1: Install and test in a space-conscious environment**

Run: `uv sync --python 3.12`
Then: `uv run pytest -q`

- [ ] **Step 2: Run app locally**

Run: `uv run streamlit run dashboard/app.py --server.headless true --server.port 8501`
Verify `http://localhost:8501` loads and browser console has no fatal errors.

- [ ] **Step 3: Exercise Ollama integration**

Run a CLI smoke call against local Ollama if the server is available and model `qwen2.5:0.5b` is installed. If Ollama is not usable, verify deterministic fallback and report it.

- [ ] **Step 4: Clean local artifacts**

Remove only disposable caches created by this task, such as `.pytest_cache`, Streamlit cache, and pip/uv cache entries when safe. Do not remove active Codex worktrees or unrelated running project data.

- [ ] **Step 5: Commit and push**

Run `git status -sb`, stage intended files, commit with a concise message, and push to `https://github.com/puneetdixit200/my-bloomburg.git`.
