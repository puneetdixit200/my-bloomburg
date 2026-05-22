# Internet Radar v2

Local-first signal intelligence dashboard based on `INTERNET_RADAR_V2_ARCHITECTURE.md`.

## What Works

- 64+ source registry covering code, social, news, jobs, hackathons, research, finance, search, and app stores.
- Live no-key collector layer for GitHub, Hacker News, Reddit JSON, Dev.to, Lobsters, RemoteOK, The Muse, Arbeitnow, Codeforces, arXiv, OpenAlex, Wikipedia Pageviews, CoinGecko, iTunes, Steam, PyPI, and npm package signals.
- Deterministic sample fallback so the app runs without API keys or network.
- SQLite persistence in `data/radar.sqlite`.
- Cross-source validation, deduplication, scoring, and local-first LLM routing.
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

## Run One Collection

```bash
uv run internet-radar-run --db data/radar.sqlite
uv run internet-radar-run --live --db data/radar.sqlite
```

## Ollama

If Ollama is running, the router checks installed local models and prefers the smallest available local model for classification. If Ollama is not available, classification falls back to deterministic rules so tests and demos still pass.
