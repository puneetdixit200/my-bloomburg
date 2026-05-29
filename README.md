# Internet Radar v2

Local-first signal intelligence dashboard based on `INTERNET_RADAR_V2_ARCHITECTURE.md`.

## What Works

- 81-source registry covering code, social, news, jobs, hackathons, research, finance, search, and app stores.
- Live no-key collector layer for every enabled public registry source, including GitHub Search/Trending, GitLab, MCP Servers Directory, PyPI, npm, crates.io, HN Algolia, multi-subreddit Reddit JSON, Bluesky, Mastodon, Stack Overflow, Dev.to, Tech RSS, Hashnode, TLDR, Lobsters, Indie Hackers, RemoteOK, The Muse, Arbeitnow, YC Jobs, Devpost, MLH, LeetCode Contests, arXiv, OpenAlex, Hugging Face, Wikipedia Pageviews, DuckDuckGo, Focused Web Crawler, Wayback Machine, Google Trends, YC Companies, SEC EDGAR, Papers With Code, OpenCollective, CoinGecko, Yahoo Finance, iTunes, Google Play, and Steam.
- Credential-aware optional collectors for Reddit API, Libraries.io, Product Hunt, Adzuna, HackerEarth, Semantic Scholar, Crunchbase, Brave Search, and Tavily.
- Parallel collector runner with per-source health reporting so one failing source does not stop the pipeline.
- Collector utilities for per-source rate limiting, TTL request caching, optional proxy rotation, HTML cleanup, and Scrapy + Trafilatura focused page extraction for configured public seed URLs.
- Deterministic sample fallback so the app runs without API keys or network.
- SQLite persistence in `data/radar.sqlite`, including `signal_snapshots` history for per-run metric tracking.
- Cross-source validation, deduplication, scoring, and local-first LLM routing.
- Cross-source agreement matrix with architecture multipliers for weak, strong, and act-now signals.
- Dedicated research and funding scorers for academic momentum and market-validation signals.
- Space-conscious local embeddings, optional Gemini/Ollama/Cohere provider-backed embeddings, optional ChromaDB vector persistence, vector search, and semantic clusters for related signals.
- Deterministic sentiment/frustration scoring and startup gap clustering for pain-heavy social and app-store signals.
- Profile-aware relevance scoring from `config/interests.yaml`, including skills, interests, goals, blocked topics, alert threshold, and suggested Radar Search queries.
- Local-first LLM routing with Groq, Gemini, and OpenRouter online free-tier choices for heavy, huge-context, and overflow analysis, plus pipeline-stored briefing, gap, trend, idea, Radar Search deep-dive summaries, and an optional bounded LLM-generated morning insight.
- Architecture-style alert templates for hackathons, startup gaps, research signals, funding signals, and skill radar items, filtered by profile threshold and notification channels.
- Multi-channel alert dispatch adapters for ntfy, Telegram, Discord, and Mailgun email, with alert-readiness reporting, durable failed-send outbox, and credential-free dry-run coverage in tests.
- Architecture-style daily briefing and skill learning recommendations derived from job, code, and research momentum.
- APScheduler-backed job catalog for the architecture cadence map, with a persistent SQLite job store, named jobs wired to source-specific collectors/actions, scheduler heartbeats in SQLite, and smart triggers for high scores, 3-source topic spikes, and hackathon crowd jumps.
- Scheduler priority queue so immediate alerts, deep analysis, and crowd warnings run before routine cadence jobs.
- Special intelligence modules for abandoned-tool opportunities, conference topic radar, salary velocity, and early wave prediction.
- Ollama integration with installed local models such as `qwen2.5:0.5b`; rule fallback when Ollama is unavailable.
- Streamlit dashboard with all 12 active architecture pages, interactive filters, charts, CSV export, and signal drilldowns.
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

`config/crawl_seeds.yaml` controls the free focused crawler. It uses Scrapy link extraction and Trafilatura text extraction, respects `robots.txt` by default, stores only compact signal metadata, and can be tuned without paid crawler APIs:

```bash
export INTERNET_RADAR_ENABLE_CRAWLER=1
export INTERNET_RADAR_CRAWL_SEEDS=config/crawl_seeds.yaml
export INTERNET_RADAR_CRAWLER_MAX_TOTAL_PAGES=200
export INTERNET_RADAR_CRAWLER_MAX_PAGES_PER_SEED=20
export INTERNET_RADAR_CRAWLER_RESPECT_ROBOTS=1
export INTERNET_RADAR_CRAWLER_TIMEOUT_SECONDS=20
export INTERNET_RADAR_SIGNAL_MAX_AGE_DAYS=14
```

Signals older than `INTERNET_RADAR_SIGNAL_MAX_AGE_DAYS` are excluded before storage-backed dashboard views and LLM analysis. Crawler pages with stale published dates or expired deadlines are rejected even if they were crawled today.

No-key Reddit JSON scanning runs even without OAuth credentials. Tune it with:

```bash
export INTERNET_RADAR_REDDIT_SUBREDDITS=LocalLLaMA,MachineLearning,OpenAI,learnpython,webdev
```

To make the morning briefing call the selected LLM once for a concise JSON insight, enable:

```bash
export INTERNET_RADAR_ENABLE_LLM_ANALYSIS=1
```

If the model call fails or the flag is off, the pipeline stores a deterministic fallback insight and keeps running.

## Storage And Vectors

SQLite is the default storage backend:

```bash
export INTERNET_RADAR_STORAGE_BACKEND=sqlite
export INTERNET_RADAR_DB=data/radar.sqlite
export INTERNET_RADAR_SCHEDULER_DB=data/scheduler_jobs.sqlite
export INTERNET_RADAR_SCHEDULER_HEARTBEAT_MAX_AGE_MINUTES=30
export INTERNET_RADAR_PAYLOAD_CACHE=data/latest_payload.json
export INTERNET_RADAR_BACKGROUND_REFRESH_SECONDS=3600
export INTERNET_RADAR_ANALYTICS_BACKEND=auto
```

SQLite remains the source of truth. `signals` stores the latest known state; `signal_snapshots` stores per-run metric history such as score, velocity, stars, downloads, citations, amount, and participants. Dashboard distribution queries use DuckDB when `INTERNET_RADAR_ANALYTICS_BACKEND=auto` or `duckdb`; if DuckDB is unavailable, they fall back to the lightweight Python path instead of breaking the app.

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

Gemini embeddings can be used without ChromaDB when `GEMINI_API_KEY` is configured:

```bash
export INTERNET_RADAR_VECTOR_BACKEND=gemini
```

The Gemini path uses `gemini-embedding-2` with 768 output dimensions. Ollama `nomic-embed-text` and Cohere `embed-english-light-v3.0` are also supported by the embedding router.

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
export INTERNET_RADAR_ALERT_OUTBOX_DB=data/radar.sqlite
export INTERNET_RADAR_ALERT_OUTBOX_RETRY_LIMIT=25
```

With `INTERNET_RADAR_FREE_ONLY=1`, Mailgun email remains disabled even if old Mailgun values are present. Automatic scheduler alerts are filtered to channels that are currently credential-ready, so a profile can mention Telegram without filling the outbox until the bot credentials exist. Failed sends are stored in the `alert_outbox` table so network timeouts stay visible and retryable instead of disappearing. Repeated failures for the same signal/channel update the existing pending row instead of creating unbounded duplicates, and retries skip channels that are still unconfigured. APScheduler retries due pending outbox rows every 15 minutes through `alert_outbox_retry`; recent repeated failures use exponential backoff so a down notification service is not hammered every scheduler cycle. The Make It Real readiness audit blocks alert dispatch while currently configured channels have pending outbox failures, because a configured topic is not enough proof that alerts actually fire; failures for unconfigured channels are covered by their own credential blockers. The Profile page shows alert readiness for ntfy, Telegram, Discord, email, and the latest outbox rows.

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
Scheduler startup, daemon keepalives, and named job runs write `scheduler_heartbeats` rows to `INTERNET_RADAR_DB`, so `--readiness` can prove that the background scheduler is currently alive instead of only checking that jobs are defined. By default, scheduler readiness blocks when the newest heartbeat is older than 30 minutes; tune that with `INTERNET_RADAR_SCHEDULER_HEARTBEAT_MAX_AGE_MINUTES`.

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
uv run internet-radar-run --readiness --db data/radar.sqlite
uv run internet-radar-run --readiness --verify-external --db data/radar.sqlite
uv run internet-radar-run --credential-setup
uv run internet-radar-run --reddit-check
uv run internet-radar-run --ntfy-check
uv run internet-radar-run --telegram-chats
uv run internet-radar-run --telegram-check
uv run internet-radar-run --test-alert --db data/radar.sqlite
uv run internet-radar-run --alert-outbox-compact --db data/radar.sqlite
uv run internet-radar-run --retry-alerts --alert-retry-limit 100 --db data/radar.sqlite
uv run internet-radar-run --retry-alerts --force-alert-retry --alert-retry-limit 10 --db data/radar.sqlite
uv run internet-radar-run --digest-alerts --alert-channel ntfy --db data/radar.sqlite
```

`--readiness` loads the local `.env` file automatically and prints the Make It Real audit as JSON, including ready checks and external blockers such as missing Reddit OAuth or Telegram credentials.
Add `--verify-external` to `--readiness` when you want the audit to make live Reddit OAuth and Telegram `getChat` calls instead of only checking that credential variables are present.
`--credential-setup` prints safe setup guidance for Reddit, ntfy, and Telegram without echoing secret values. For Reddit, create a developer app of type `script`; the collector does not use a browser redirect, so use `http://localhost:8080` as the redirect URI.
`--reddit-check` requests a Reddit OAuth access token with `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` and reports whether the script app credentials are valid without storing the token.
`--ntfy-check` sends one ntfy delivery probe to the configured topic without writing a durable outbox row, which is useful for separating server reachability problems from backlog retry state.
`--telegram-chats` calls Telegram `getUpdates` with `TELEGRAM_BOT_TOKEN` and prints candidate `TELEGRAM_CHAT_ID` values after you message the bot once.
`--telegram-check` calls Telegram `getChat` with `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to verify the configured chat without sending a message.
`--test-alert` sends a controlled test notification to the currently configured ready channels and records failures in the alert outbox.
`--alert-outbox-compact` coalesces duplicate pending failures after an outage.
`--retry-alerts` retries due pending outbox rows for channels that are currently credential-ready; use `--alert-retry-limit` to raise the batch size after network delivery recovers. Use `--force-alert-retry` for a manual recovery probe that ignores backoff.
`--digest-alerts` sends one summary notification per ready channel and marks those pending rows as digested, which avoids replaying hundreds of stale outage alerts one-by-one.

## Ollama

If Ollama is running, the router checks installed local models and prefers the smallest available local model for classification. If Ollama is not available, classification falls back to deterministic rules so tests and demos still pass.
