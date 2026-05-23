# Internet Radar v2

Local-first signal intelligence dashboard based on `INTERNET_RADAR_V2_ARCHITECTURE.md`.

## What Works

- 64+ source registry covering code, social, news, jobs, hackathons, research, finance, search, and app stores.
- Live no-key collector layer for GitHub, Hacker News, Reddit JSON, Dev.to, Lobsters, RemoteOK, The Muse, Arbeitnow, Codeforces, arXiv, OpenAlex, Wikipedia Pageviews, DuckDuckGo, Google Trends, YC Companies, SEC EDGAR, Papers With Code, CoinGecko, iTunes, Steam, PyPI, and npm package signals.
- Parallel collector runner with per-source health reporting so one failing source does not stop the pipeline.
- Collector utilities for per-source rate limiting, TTL request caching, optional proxy rotation, and HTML cleanup for scraper-style sources.
- Deterministic sample fallback so the app runs without API keys or network.
- SQLite persistence in `data/radar.sqlite`.
- Cross-source validation, deduplication, scoring, and local-first LLM routing.
- Cross-source agreement matrix with architecture multipliers for weak, strong, and act-now signals.
- Dedicated research and funding scorers for academic momentum and market-validation signals.
- Space-conscious local embeddings, vector search, and semantic clusters for related signals without requiring a heavy vector database.
- Deterministic sentiment/frustration scoring and startup gap clustering for pain-heavy social and app-store signals.
- Profile-aware relevance scoring from `config/interests.yaml`, including skills, interests, goals, blocked topics, alert threshold, and suggested Radar Search queries.
- Local-first LLM routing with Groq, Gemini, and OpenRouter online free-tier choices for heavy, huge-context, and overflow analysis, plus Radar Search deep-dive summaries.
- Architecture-style alert templates for hackathons, startup gaps, research signals, funding signals, and skill radar items, filtered by profile threshold and notification channels.
- Multi-channel alert dispatch adapters for ntfy, Telegram, Discord, and Mailgun email, with credential-free dry-run coverage in tests.
- Architecture-style daily briefing and skill learning recommendations derived from job, code, and research momentum.
- APScheduler-backed job catalog for the architecture cadence map, plus smart triggers for high scores, 3-source topic spikes, and hackathon crowd jumps.
- Scheduler priority queue so immediate alerts, deep analysis, and crowd warnings run before routine cadence jobs.
- Special intelligence modules for abandoned-tool opportunities, conference topic radar, salary velocity, and early wave prediction.
- Ollama integration with installed local models such as `qwen2.5:0.5b`; rule fallback when Ollama is unavailable.
- Streamlit dashboard with all 13 architecture pages.
- Pytest coverage for pipeline, storage, scoring, collectors, LLM routing, dashboard smoke paths, and Streamlit rendering.

## Setup

```bash
uv sync --python 3.12 --extra test
cp .env.example .env
```

The app defaults to sample data to keep it reliable and fast. To call public no-key APIs, set:

```bash
export INTERNET_RADAR_USE_LIVE=1
```

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
