# Internet Radar v2 - Local-First AI Trend Intelligence Dashboard

Internet Radar v2 is a local-first Streamlit dashboard that collects, ranks, and explains fresh internet signals across GitHub, research papers, developer communities, hackathons, startup pain, funding, app stores, jobs, RSS, search, and a free focused web crawler.

It is built for builders who want a private Bloomberg-style signal radar for AI trends, open-source projects, research momentum, startup gaps, hackathons, skill demand, and market movement without depending on paid crawler APIs.

**SEO keywords:** AI trend dashboard, local-first intelligence dashboard, GitHub radar, research radar, startup gap finder, hackathon radar, Streamlit analytics app, free web crawler, Scrapy Trafilatura crawler, Ollama dashboard, SQLite signal intelligence, AI market research tool, developer trend radar.

## Table Of Contents

- [What The App Does](#what-the-app-does)
- [Main Pages](#main-pages)
- [Requirements](#requirements)
- [Fast Install](#fast-install)
- [Run The App](#run-the-app)
- [Environment Variables](#environment-variables)
- [Data Sources](#data-sources)
- [Storage And Vectors](#storage-and-vectors)
- [Crawler Setup](#crawler-setup)
- [Alerts](#alerts)
- [Docker](#docker)
- [Testing](#testing)
- [Operations](#operations)
- [Cleanup](#cleanup)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)
- [Security And Privacy](#security-and-privacy)
- [GitHub Topics](#github-topics)

## What The App Does

Internet Radar v2 turns noisy public signals into ranked, fresh, actionable dashboards:

- Collects live public data from code, social, news, jobs, hackathons, research, finance, search, app-store, RSS, and crawler sources.
- Stores results locally in SQLite by default.
- Filters out stale, expired, and missing-deadline hackathon data.
- Limits every page to at most 3 visible items from the same source, so one source cannot dominate the dashboard.
- Embeds source links inside table titles instead of showing separate raw link columns.
- Uses deterministic analysis by default and optional Ollama, Gemini, Groq, OpenRouter, Cohere, or ChromaDB integrations when configured.
- Supports no-key live sources first; paid or credentialed APIs are optional.
- Provides alerts through ntfy, Telegram, Discord, and email adapters when credentials are configured.
- Includes a source-health and readiness audit so you can see what is working and what still needs credentials.

## Main Pages

1. **Morning Intelligence Briefing** - top signals, narrative summary, alerts, source health, metrics, and daily report export.
2. **GitHub Radar** - repositories, packages, MCP catalog entries, GitLab projects, and developer ecosystem movement.
3. **Hackathon Radar** - active contest opportunities only; expired or missing-deadline rows are hidden.
4. **Startup Gap Finder** - pain signals from social, news, and app-store data turned into product gaps.
5. **Multi-Source Trend Velocity** - cross-source trend confirmation and velocity analysis.
6. **Research Radar** - academic and technical momentum from research APIs, RSS, and crawler sources.
7. **Funding Radar** - finance, grants, public company, crypto, open-source funding, and YC money-flow signals.
8. **Skill Radar** - skill recommendations from code, research, and job demand signals.
9. **Community Pulse** - developer discussion and sentiment from Reddit JSON, Hacker News, Mastodon, Bluesky, Stack Overflow, and more.
10. **App Store Pain Miner** - review pain, competitor weakness, and software marketplace signals.
11. **Radar Search** - readable search tables and deep-dive analysis across collected signals.
12. **Your Profile** - interests, skills, alert thresholds, personalized feed, and alert readiness.

## Requirements

### Required

- macOS, Linux, or Windows.
- Python `>=3.11,<3.14`.
- `uv` recommended for fastest install.
- At least 1 GB free disk for the repo, virtualenv, SQLite data, and optional cache files.

### Optional

- Docker and Docker Compose for containerized dashboard, scheduler, Telegram bot, and Ollama services.
- Ollama for local LLM analysis.
- ChromaDB for persistent vector search.
- Supabase project if you want remote storage instead of SQLite.
- API keys for optional credentialed sources and alert channels.

## Fast Install

Clone and install:

```bash
git clone https://github.com/puneetdixit200/my-bloomburg.git
cd my-bloomburg
uv sync --python 3.12 --extra test
cp .env.example .env
```

Run with sample/fallback-safe data:

```bash
uv run streamlit run dashboard/app.py --server.headless true --server.address 127.0.0.1 --server.port 8501
```

Open:

```text
http://127.0.0.1:8501
```

### Install Without uv

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501
```

Windows PowerShell activation:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501
```

## Run The App

### Dashboard

```bash
uv run streamlit run dashboard/app.py --server.headless true --server.address 127.0.0.1 --server.port 8501
```

### One Collection

```bash
uv run internet-radar-run --db data/radar.sqlite
```

### Live Public Collection

```bash
INTERNET_RADAR_USE_LIVE=1 uv run internet-radar-run --live --db data/radar.sqlite
```

### Readiness Audit

```bash
uv run internet-radar-run --readiness --db data/radar.sqlite
uv run internet-radar-run --readiness --verify-external --db data/radar.sqlite
```

### Scheduler

```bash
uv run python run_scheduler.py
```

Alternative architecture-compatible commands:

```bash
python scheduler/runner.py
python scheduler/runner.py --once
python scheduler/runner.py --loop
python alerts/telegram_bot.py
python alerts/telegram_bot.py --watch
```

## Environment Variables

Start with:

```bash
cp .env.example .env
```

The app reads `.env` automatically for CLI and dashboard paths. Do not commit `.env`.

### Core Runtime

| Variable | Default | Purpose |
| --- | --- | --- |
| `INTERNET_RADAR_DB` | `data/radar.sqlite` | SQLite database path. |
| `INTERNET_RADAR_USE_LIVE` | `1` in `.env.example` | Enables live collectors when running with `--live`. |
| `INTERNET_RADAR_FREE_ONLY` | `1` | Keeps paid integrations disabled unless explicitly changed. |
| `INTERNET_RADAR_SIGNAL_MAX_AGE_DAYS` | `14` | Excludes old signals from dashboard and analysis. |
| `INTERNET_RADAR_PAYLOAD_CACHE` | `data/latest_payload.json` | Latest dashboard payload cache. |
| `INTERNET_RADAR_BACKGROUND_REFRESH_SECONDS` | `3600` | Dashboard background refresh interval. |
| `INTERNET_RADAR_USER_AGENT` | `internet-radar-v2/0.1` | User agent for public requests. |

### Crawler

| Variable | Default | Purpose |
| --- | --- | --- |
| `INTERNET_RADAR_ENABLE_CRAWLER` | `1` | Enables focused crawler collection. |
| `INTERNET_RADAR_CRAWL_SEEDS` | `config/crawl_seeds.yaml` | Seed URL config. |
| `INTERNET_RADAR_CRAWLER_MAX_TOTAL_PAGES` | `200` | Maximum crawler pages per run. |
| `INTERNET_RADAR_CRAWLER_MAX_PAGES_PER_SEED` | `20` | Per-seed crawler cap. |
| `INTERNET_RADAR_CRAWLER_RESPECT_ROBOTS` | `1` | Respects `robots.txt`. |
| `INTERNET_RADAR_CRAWLER_TIMEOUT_SECONDS` | `20` | Per-request timeout. |

### Storage

| Variable | Default | Purpose |
| --- | --- | --- |
| `INTERNET_RADAR_STORAGE_BACKEND` | `sqlite` | `sqlite` or `supabase`. |
| `SUPABASE_URL` | empty | Supabase project URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | empty | Supabase service role key. |
| `SUPABASE_TABLE` | `signals` | Supabase table name. |
| `INTERNET_RADAR_ANALYTICS_BACKEND` | `auto` | Uses DuckDB when available. |

### AI And Vectors

| Variable | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_HOST` | `http://localhost:11434` | Local Ollama endpoint. |
| `INTERNET_RADAR_ENABLE_LLM_ANALYSIS` | `0` | Makes one bounded LLM JSON call for morning insight. |
| `GEMINI_API_KEY` | empty | Gemini LLM/embedding support. |
| `GROQ_API_KEY` | empty | Groq LLM route. |
| `OPENROUTER_API_KEY` | empty | OpenRouter route. |
| `COHERE_API_KEY` | empty | Cohere embeddings. |
| `INTERNET_RADAR_VECTOR_BACKEND` | `auto` | `auto`, `deterministic`, `chroma`, `gemini`, `ollama`, or `cohere`. |
| `INTERNET_RADAR_CHROMA_PATH` | `data/chroma` | ChromaDB persistence path. |

### Alerts

| Variable | Default | Purpose |
| --- | --- | --- |
| `INTERNET_RADAR_DISPATCH_ALERTS` | `0` | Enables real alert sending. |
| `INTERNET_RADAR_NTFY_TOPIC` | empty | ntfy topic. |
| `INTERNET_RADAR_NTFY_SERVER` | `https://ntfy.sh` | ntfy server. |
| `TELEGRAM_BOT_TOKEN` | empty | Telegram bot token. |
| `TELEGRAM_CHAT_ID` | empty | Telegram chat ID. |
| `DISCORD_WEBHOOK_URL` | empty | Discord webhook. |
| `MAILGUN_DOMAIN` | empty | Optional Mailgun domain. |
| `MAILGUN_API_KEY` | empty | Optional Mailgun API key. |
| `INTERNET_RADAR_ALERT_OUTBOX_DB` | `data/radar.sqlite` | Durable failed-alert outbox path. |
| `INTERNET_RADAR_ALERT_OUTBOX_RETRY_LIMIT` | `25` | Retry batch size. |

### Optional Source Keys

| Variable | Source |
| --- | --- |
| `GITHUB_TOKEN` | GitHub higher-rate API access. |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | Reddit OAuth collector. |
| `LIBRARIES_IO_API_KEY` | Libraries.io. |
| `PRODUCTHUNT_TOKEN` | Product Hunt. |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Adzuna jobs. |
| `HACKEREARTH_API_KEY` | HackerEarth. |
| `SEMANTIC_SCHOLAR_API_KEY` | Semantic Scholar. |
| `BRAVE_SEARCH_API_KEY` | Brave Search, optional and paid/gated. |
| `TAVILY_API_KEY` | Tavily, optional and paid/gated. |
| `CRUNCHBASE_API_KEY` | Crunchbase, optional and paid/gated. |

## Data Sources

Internet Radar v2 has an 80+ source registry across:

- Code: GitHub Search, GitHub Trending, GitLab Explore, MCP Servers Directory, PyPI, npm, crates.io, Docker Hub, RubyGems, and optional Libraries.io.
- Social/community: Reddit JSON, Hacker News, HN Algolia, Bluesky, Mastodon, Stack Overflow, and optional Reddit OAuth.
- News/RSS: Tech RSS, Dev.to, Hashnode, TLDR, Lobsters, Indie Hackers, GDELT, company engineering blogs, and configured RSS feeds.
- Jobs: RemoteOK, The Muse, Arbeitnow, YC Jobs, Greenhouse, Lever, and optional Adzuna.
- Hackathons: Devpost, MLH, Codeforces, LeetCode Contests, and optional HackerEarth.
- Research: arXiv, OpenAlex, Crossref, Europe PMC, PubMed, bioRxiv, medRxiv, Wikipedia Pageviews, Papers With Code, Hugging Face Models, Hugging Face Papers, Conference RSS, and optional Semantic Scholar/Kaggle.
- Finance/funding: YC Companies, SEC EDGAR, Grants.gov, USAspending, Yahoo Finance, CoinGecko, OpenCollective, and optional Crunchbase.
- Search/crawler: DuckDuckGo, Wayback Machine, Common Crawl, Google Trends, and Focused Web Crawler.
- App stores: iTunes App Store, Google Play, Steam, and F-Droid.

Each dashboard page is source-balanced. No page should show more than 3 signal rows from the same source.

## Storage And Vectors

SQLite is the default and recommended local mode:

```bash
export INTERNET_RADAR_STORAGE_BACKEND=sqlite
export INTERNET_RADAR_DB=data/radar.sqlite
export INTERNET_RADAR_SCHEDULER_DB=data/scheduler_jobs.sqlite
```

SQLite tables include:

- `signals` for the latest known signal state.
- `signal_snapshots` for score, velocity, stars, downloads, citations, funding, and participant history.
- `scheduler_heartbeats` for proving that background jobs are alive.
- `alert_outbox` for durable alert retry state.

Supabase is available when configured:

```bash
export INTERNET_RADAR_STORAGE_BACKEND=supabase
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=your-key
export SUPABASE_TABLE=signals
```

Vector search options:

```bash
uv sync --extra test --extra vector
export INTERNET_RADAR_VECTOR_BACKEND=chroma
export INTERNET_RADAR_CHROMA_PATH=data/chroma
```

Lightweight alternatives:

```bash
export INTERNET_RADAR_VECTOR_BACKEND=deterministic
export INTERNET_RADAR_VECTOR_BACKEND=gemini
export INTERNET_RADAR_VECTOR_BACKEND=ollama
```

## Crawler Setup

The focused crawler is free and local. It uses Scrapy link extraction plus Trafilatura content extraction. It does not store raw HTML.

Crawler seed file:

```text
config/crawl_seeds.yaml
```

Recommended crawler env:

```bash
export INTERNET_RADAR_ENABLE_CRAWLER=1
export INTERNET_RADAR_CRAWL_SEEDS=config/crawl_seeds.yaml
export INTERNET_RADAR_CRAWLER_MAX_TOTAL_PAGES=200
export INTERNET_RADAR_CRAWLER_MAX_PAGES_PER_SEED=20
export INTERNET_RADAR_CRAWLER_RESPECT_ROBOTS=1
export INTERNET_RADAR_CRAWLER_TIMEOUT_SECONDS=20
```

Freshness rules:

- Signals older than `INTERNET_RADAR_SIGNAL_MAX_AGE_DAYS` are excluded.
- Expired deadlines are excluded.
- Hackathon records without a future actionable deadline are excluded.
- LLM analysis receives only fresh filtered signals.

## Alerts

Real alert delivery is off by default. Turn it on only after adding credentials:

```bash
export INTERNET_RADAR_DISPATCH_ALERTS=1
export INTERNET_RADAR_NTFY_TOPIC=your-topic
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
export DISCORD_WEBHOOK_URL=...
```

Useful checks:

```bash
uv run internet-radar-run --credential-setup
uv run internet-radar-run --ntfy-check
uv run internet-radar-run --telegram-chats
uv run internet-radar-run --telegram-check
uv run internet-radar-run --test-alert --db data/radar.sqlite
uv run internet-radar-run --alert-outbox-compact --db data/radar.sqlite
uv run internet-radar-run --retry-alerts --alert-retry-limit 100 --db data/radar.sqlite
uv run internet-radar-run --digest-alerts --alert-channel ntfy --db data/radar.sqlite
```

`INTERNET_RADAR_FREE_ONLY=1` keeps Mailgun disabled even if old Mailgun values are present.

## Docker

Run the dashboard:

```bash
docker compose up dashboard
```

Run background scheduler:

```bash
docker compose --profile background up scheduler
```

Run Telegram bot:

```bash
docker compose --profile alerts up telegram-bot
```

Run local Ollama service:

```bash
docker compose --profile local-llm up ollama
```

Docker stores app data in named volumes instead of the repo checkout. If `.env` exists, Docker Compose uses it for credentials.

## Testing

Run the full suite:

```bash
uv run --extra test pytest -q
```

Run dashboard smoke tests:

```bash
uv run --extra test pytest tests/test_dashboard_smoke.py -q
```

Run a readiness check:

```bash
uv run internet-radar-run --readiness --db data/radar.sqlite
```

## Operations

Common commands:

```bash
uv run internet-radar-run --db data/radar.sqlite
uv run internet-radar-run --live --db data/radar.sqlite
uv run internet-radar-run --readiness --db data/radar.sqlite
uv run internet-radar-run --readiness --verify-external --db data/radar.sqlite
uv run streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501
uv run python run_scheduler.py
```

Health check:

```bash
curl -fsS http://127.0.0.1:8501/_stcore/health
```

## Cleanup

Safe cleanup for low disk space:

```bash
find . -type d \( -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} +
rm -rf .ruff_cache .mypy_cache .coverage htmlcov
```

Large rebuildable local folders:

- `.venv/` can be deleted and rebuilt with `uv sync --python 3.12 --extra test`.
- `data/chroma/` can be deleted if you do not need persistent Chroma vectors.
- `data/*.sqlite` and `data/*.json` are local app state. Delete only if you are okay losing collected signals and cache.

Do not delete `.env` unless you have the credentials saved elsewhere.

## Troubleshooting

### App opens but no data appears

Run:

```bash
uv run internet-radar-run --readiness --db data/radar.sqlite
```

Then run a live collection:

```bash
INTERNET_RADAR_USE_LIVE=1 uv run internet-radar-run --live --db data/radar.sqlite
```

### Research Radar looks dominated by one source

Every page has a strict 3-items-per-source display cap. If only a few rows appear, the other research sources may not have fresh signals after freshness filtering.

### Hackathon Radar is empty

Expired hackathons and records missing future deadlines are intentionally hidden. Use Codeforces, LeetCode, Devpost, MLH, or configured crawler pages that expose future contest dates.

### Ollama is unavailable

The app still works. It falls back to deterministic analysis. To use Ollama:

```bash
ollama serve
ollama pull qwen2.5:0.5b
export OLLAMA_HOST=http://localhost:11434
```

### Paid APIs

The app does not require Brave Search, Mailgun, Tavily, Crunchbase, or other paid services. Keep:

```bash
export INTERNET_RADAR_FREE_ONLY=1
```

## Project Structure

```text
dashboard/                 Streamlit UI and page wrappers
internet_radar/            Collectors, pipeline, scoring, storage, alerts, search
internet_radar/collectors/ Live source collectors and focused crawler
internet_radar/signals/    Signal freshness, deduplication, correlations, gaps
internet_radar/brain/      LLM routing, summaries, classification, deep dives
internet_radar/storage/    SQLite, Supabase, analytics, payload cache, vectors
internet_radar/scheduler/  APScheduler jobs and heartbeat tracking
config/                    Sources, RSS feeds, crawler seeds, profile config
tests/                     Pytest suite
docs/APP_EXPLAINED.md      Full architecture and behavior reference
```

## Security And Privacy

- `.env` is ignored by Git.
- Local SQLite and payload cache files are ignored by Git.
- Raw crawler HTML is not stored.
- Alert failures are stored locally for retry visibility.
- Optional API keys are only used when configured.
- `INTERNET_RADAR_FREE_ONLY=1` keeps paid/gated integrations disabled by default.

## GitHub Topics

Recommended GitHub repository topics for discoverability:

```text
ai-dashboard, trend-intelligence, streamlit, sqlite, local-first, web-crawler, scrapy, trafilatura, ollama, github-radar, research-radar, startup-ideas, hackathon-radar, market-intelligence, developer-tools
```
