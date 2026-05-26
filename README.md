# Internet Radar v2

Local-first signal intelligence dashboard based on `INTERNET_RADAR_V2_ARCHITECTURE.md`.

## What Works

- 80-source registry covering code, social, news, jobs, hackathons, research, finance, search, and app stores.
- Live no-key collector layer for every enabled public registry source, including GitHub Search/Trending, GitLab, MCP Servers Directory, PyPI, npm, crates.io, HN Algolia, Reddit JSON, Bluesky, Mastodon, Stack Overflow, Dev.to, Tech RSS, Hashnode, TLDR, Lobsters, Indie Hackers, RemoteOK, The Muse, Arbeitnow, YC Jobs, Devpost, MLH, LeetCode Contests, arXiv, OpenAlex, Hugging Face, Wikipedia Pageviews, DuckDuckGo, Wayback Machine, Google Trends, YC Companies, SEC EDGAR, Papers With Code, OpenCollective, CoinGecko, Yahoo Finance, iTunes, Google Play, and Steam.
- Credential-aware optional collectors for Reddit API, Libraries.io, Product Hunt, Adzuna, HackerEarth, Semantic Scholar, Crunchbase, Brave Search, and Tavily.
- Parallel collector runner with per-source health reporting so one failing source does not stop the pipeline.
- Collector utilities for per-source rate limiting, TTL request caching, optional proxy rotation, and HTML cleanup for scraper-style sources.
- Deterministic sample fallback so the app runs without API keys or network.
- SQLite persistence in `data/radar.sqlite`, including `signal_snapshots` history for per-run metric tracking.
- Cross-source validation, deduplication, scoring, and local-first LLM routing.
- Cross-source agreement matrix with architecture multipliers for weak, strong, and act-now signals.
- Dedicated research and funding scorers for academic momentum and market-validation signals.
- Space-conscious local embeddings, optional ChromaDB vector persistence, Ollama/Cohere embedding routing, vector search, and semantic clusters for related signals.
- Deterministic sentiment/frustration scoring and startup gap clustering for pain-heavy social and app-store signals.
- Profile-aware relevance scoring from `config/interests.yaml`, including skills, interests, goals, blocked topics, alert threshold, and suggested Radar Search queries.
- Local-first LLM routing with Groq, Gemini, and OpenRouter online free-tier choices for heavy, huge-context, and overflow analysis, plus pipeline-stored briefing, gap, trend, idea, and Radar Search deep-dive summaries.
- Architecture-style alert templates for hackathons, startup gaps, research signals, funding signals, and skill radar items, filtered by profile threshold and notification channels.
- Multi-channel alert dispatch adapters for ntfy, Telegram, Discord, and Mailgun email, with alert-readiness reporting and credential-free dry-run coverage in tests.
- Architecture-style daily briefing and skill learning recommendations derived from job, code, and research momentum.
- APScheduler-backed job catalog for the architecture cadence map, with a persistent SQLite job store, named jobs wired to source-specific collectors/actions, and smart triggers for high scores, 3-source topic spikes, and hackathon crowd jumps.
- Scheduler priority queue so immediate alerts, deep analysis, and crowd warnings run before routine cadence jobs.
- Special intelligence modules for abandoned-tool opportunities, conference topic radar, salary velocity, and early wave prediction.
- Ollama integration with installed local models such as `qwen2.5:0.5b`; rule fallback when Ollama is unavailable.
- Streamlit dashboard with all 13 architecture pages, interactive filters, charts, CSV export, and signal drilldowns.
- Dashboard reliability layer with source health, visible data previews, latest-payload cache, manual refresh, free-only mode, and Markdown daily report export.
- Pytest coverage for pipeline, storage, scoring, collectors, LLM routing, dashboard smoke paths, and Streamlit rendering.

## Setup

```bash
uv sync --python 3.12 --extra test
cp .env.example .env
```

The same commands work on macOS, Linux, and Windows PowerShell. On Windows, use `.venv\Scripts\Activate.ps1` if you create a manual virtualenv instead of using `uv`.

The app defaults to sample data to keep it reliable and fast. To call public no-key APIs, set:

```bash
export INTERNET_RADAR_USE_LIVE=1
export INTERNET_RADAR_FREE_ONLY=1
```

`config/rss_feeds.yaml` ships with 20+ feeds. Keep adding feeds there; the RSS collectors read the file directly.

## Storage And Vectors

SQLite is the default storage backend:

```bash
export INTERNET_RADAR_STORAGE_BACKEND=sqlite
export INTERNET_RADAR_DB=data/radar.sqlite
export INTERNET_RADAR_SCHEDULER_DB=data/scheduler_jobs.sqlite
export INTERNET_RADAR_PAYLOAD_CACHE=data/latest_payload.json
export INTERNET_RADAR_BACKGROUND_REFRESH_SECONDS=3600
```

The app deliberately keeps analytics in SQLite instead of DuckDB to stay lightweight on disk. `signals` stores the latest known state; `signal_snapshots` stores per-run metric history such as score, velocity, stars, downloads, citations, amount, and participants.

Supabase is ready through REST keys:

```bash
export INTERNET_RADAR_STORAGE_BACKEND=supabase
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=your-key
export SUPABASE_TABLE=signals
```

ChromaDB is optional and used automatically when installed, or explicitly with:

```bash
uv sync --extra test --extra vector
# or, without uv:
python -m pip install -r requirements-vector.txt
export INTERNET_RADAR_VECTOR_BACKEND=chroma
export INTERNET_RADAR_CHROMA_PATH=data/chroma
```

Set `INTERNET_RADAR_VECTOR_BACKEND=deterministic` to stay fully lightweight.

## Alerts

All alert paths are wired. Add the relevant env keys and set dispatch on:

```bash
export INTERNET_RADAR_DISPATCH_ALERTS=1
export INTERNET_RADAR_NTFY_TOPIC=your-topic
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
export DISCORD_WEBHOOK_URL=...
export MAILGUN_DOMAIN=...
export MAILGUN_API_KEY=...
export INTERNET_RADAR_EMAIL_TO=you@example.com
export INTERNET_RADAR_EMAIL_FROM=radar@example.com
```

With `INTERNET_RADAR_FREE_ONLY=1`, Mailgun email remains disabled even if old Mailgun values are present. The Profile page shows alert readiness for ntfy, Telegram, Discord, and email.

## Run Tests

```bash
uv run pytest -q
```

## Run Dashboard

```bash
uv run streamlit run dashboard/app.py --server.headless true --server.port 8501
```

Open `http://localhost:8501`.

The architecture-compatible root commands also work from the repo checkout:

```bash
python scheduler/runner.py
python scheduler/runner.py --once
python scheduler/runner.py --loop
python run_scheduler.py
python alerts/telegram_bot.py
```

`alerts/telegram_bot.py` runs once by default. Add `--watch` to keep polling.

## Docker Compose

```bash
docker compose up dashboard
docker compose --profile background up scheduler
docker compose --profile alerts up telegram-bot
docker compose --profile local-llm up ollama
```

Compose stores app data in named volumes instead of the repo checkout.
If a `.env` file is present, Docker Compose uses it for the interpolated API key and alert credentials.

## Run One Collection

```bash
uv run internet-radar-run --db data/radar.sqlite
uv run internet-radar-run --live --db data/radar.sqlite
```

## Ollama

If Ollama is running, the router checks installed local models and prefers the smallest available local model for classification. If Ollama is not available, classification falls back to deterministic rules so tests and demos still pass.
