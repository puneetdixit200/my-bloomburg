# Internet Radar App Explained

This file explains what the Internet Radar app is, how the full system works, where each part lives, and how the app calculates the numbers shown in the dashboard.

The app is a local-first Streamlit dashboard. It collects public internet signals, normalizes them into one common `SignalRecord` shape, stores them in SQLite, enriches them with scoring and analysis, and renders them across radar pages like GitHub Radar, Hackathon Radar, Startup Gap Finder, Research Radar, Funding Radar, and Skill Radar.

## Quick Mental Model

```text
Public sources
  -> collectors
  -> SignalRecord objects
  -> deduplication
  -> SQLite storage
  -> signal_snapshots history
  -> pipeline analysis artifacts
  -> latest payload cache
  -> dashboard payload builder
  -> Streamlit pages and tables
```

The important files are:

| Area | File | Purpose |
| --- | --- | --- |
| Streamlit app | `dashboard/app.py` | Main dashboard UI, tabs, filters, clickable tables, source health, refresh button. |
| Dashboard payload | `internet_radar/dashboard_data.py` | Builds all page-specific data and derived analyses. |
| Pipeline | `internet_radar/pipeline.py` | Runs collectors, deduplicates, stores, and returns a `BriefingPayload`. |
| Live collectors | `internet_radar/collectors/live.py` | Public/API collectors and source-specific parsing formulas. |
| Collector runner | `internet_radar/collectors/runner.py` | Runs collectors in parallel and marks sources as live, fallback, or error. |
| Source registry | `internet_radar/sources/registry.py` | Master source list, category, auth requirement, default enabled flag. |
| Models | `internet_radar/storage/models.py` | Core Pydantic models like `SignalRecord`, `SignalSnapshot`, `HistoricalTrend`, `SourceDefinition`, `BriefingPayload`. |
| SQLite store | `internet_radar/storage/db.py` | Saves latest signals and per-run metric snapshots from `data/radar.sqlite`. |
| Payload cache | `internet_radar/storage/payload_cache.py` | Saves latest successful dashboard payload to `data/latest_payload.json`. |
| Scorers | `internet_radar/scoring/*.py` | Domain-specific formulas for trends, gaps, research, funding, jobs, hackathons. |
| Signal analysis | `internet_radar/signals/*.py` | Deduplication, sentiment, startup gaps, semantic clusters, cross-source agreement. |
| LLM routing | `internet_radar/brain/llm_router.py` | Chooses Ollama/local, online free-tier, or deterministic rules. |
| Alerts | `internet_radar/alerts/*.py` | Builds and optionally dispatches alerts. |
| Scheduler | `internet_radar/scheduler/*.py` | Defines scheduled collection jobs, smart triggers, and runtime heartbeats. |

## Running The App

The local dashboard runs on:

```bash
uv run streamlit run dashboard/app.py --server.headless true --server.port 8501
```

Open:

```text
http://127.0.0.1:8501
```

Run one collection from the CLI:

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

The readiness command loads the local `.env` file and latest cached payload, then returns a JSON Make It Real audit so you can see whether the remaining work is code, runtime, or external credentials.
Add `--verify-external` to readiness when you want that audit to verify the configured Reddit OAuth and Telegram credentials against their APIs.
The credential-setup command prints missing credential keys and verification commands without printing the configured secret values. For Reddit, use app type `script`; the collector does not use a browser redirect, so `http://localhost:8080` is the redirect URI to enter in the Reddit app form.
The reddit-check command requests a Reddit OAuth token and reports whether the configured Reddit script app credentials are valid.
The ntfy-check command sends one ntfy delivery probe to the configured topic without writing a durable outbox row.
The telegram-chats command uses Telegram `getUpdates` to list chat IDs after you send one message to the bot.
The telegram-check command uses Telegram `getChat` to verify the configured token and chat ID without sending a message.
The test-alert command sends a controlled alert to every ready configured channel and persists failures to the alert outbox.
The alert-outbox-compact command coalesces duplicate pending failures after an outage.
The retry-alerts command retries due pending outbox rows for channels that are currently credential-ready; raise `--alert-retry-limit` when recovering a large backlog. Add `--force-alert-retry` for a manual recovery probe that ignores backoff.
The digest-alerts command sends one summary notification per ready channel and marks the channel backlog as digested, avoiding a burst of stale phone notifications after delivery recovers.

Run the real scheduler entrypoint:

```bash
python run_scheduler.py
```

Run tests:

```bash
uv run pytest -q
```

## Modes: Sample, Live, Fallback, Free-Only

### Sample Mode

When `INTERNET_RADAR_USE_LIVE` is off, the app uses deterministic sample signals. This keeps tests and demos reliable without network calls.

### Live Mode

When `INTERNET_RADAR_USE_LIVE=1` or the sidebar toggle is on, the app calls public sources. Each collector returns zero or more `SignalRecord` objects.

### Fallback Mode

If a source is unavailable, too slow, blocked, or missing credentials, the collector returns a deterministic fallback signal. The collector runner marks a source as:

```text
live (N)      -> returned real records
fallback (N)  -> returned deterministic fallback records
error: ...    -> collector raised an error
```

The dashboard Source Health table shows this as `live`, `fallback`, or `error`.

### Free-Only Mode

`INTERNET_RADAR_FREE_ONLY=1` keeps paid paths disabled:

| Integration | Result |
| --- | --- |
| Brave Search API | Disabled |
| Crunchbase API | Disabled |
| Mailgun Email | Disabled |

Free keyed APIs can still run when keys exist, but paid integrations stay off.

Credentialed Reddit OAuth is optional. If `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` are present, the app adds the `Reddit API` collector. If those values are empty, the no-key `Reddit JSON` collector still scans the subreddits in `INTERNET_RADAR_REDDIT_SUBREDDITS` and only falls back when public Reddit JSON is unreachable.

## Source Registry

The app currently has:

```text
81 registered sources
61 enabled by default
```

Sources are grouped like this:

| Category | Registered | Enabled | Sources |
| --- | ---: | ---: | --- |
| `app_stores` | 4 | 4 | iTunes App Store, Google Play, Steam, F-Droid |
| `code` | 12 | 9 | GitHub Search, GitHub Trending, GitHub GraphQL, PyPI, npm Registry, crates.io, Libraries.io, GitLab Explore, Bitbucket Search, Docker Hub, RubyGems, MCP Servers Directory |
| `finance` | 9 | 7 | Crunchbase, YC Companies, SEC EDGAR, Grants.gov, USAspending, Yahoo Finance, CoinGecko, Alpha Vantage, OpenCollective |
| `hackathons` | 6 | 4 | Devpost, Unstop, MLH, HackerEarth, Codeforces, LeetCode Contests |
| `jobs` | 10 | 6 | RemoteOK, Adzuna, The Muse, Arbeitnow, YC Jobs, Wellfound, Career Page Watcher, Levels.fyi Search, Greenhouse Jobs, Lever Jobs |
| `news` | 9 | 8 | Tech RSS, Dev.to, Hashnode, Lobsters, Product Hunt, TLDR Newsletter, GDELT, Indie Hackers, Company Engineering Blogs |
| `research` | 14 | 12 | arXiv, OpenAlex, Crossref, Europe PMC, PubMed, bioRxiv, medRxiv, Semantic Scholar, Wikipedia Pageviews, Papers With Code, Kaggle Datasets, Hugging Face Models, Hugging Face Papers, Conference RSS |
| `search` | 7 | 5 | DuckDuckGo, Focused Web Crawler, Brave Search, Tavily, Wayback Machine, Common Crawl, Google Trends |
| `social` | 10 | 6 | Reddit API, Reddit JSON, Hacker News, HN Algolia, Bluesky, Mastodon, Nitter, Discord Monitor, YouTube Search, Stack Overflow |

The registry is metadata. The actual live behavior is in `default_collectors()` inside `internet_radar/collectors/live.py`.

## Focused Web Crawler

The app includes a free focused crawler for cases where public APIs are weak or paid search APIs are unavailable. It is intentionally small and seed-based.

```text
config/crawl_seeds.yaml
  -> FocusedWebCrawlerCollector
  -> Scrapy link extraction
  -> Trafilatura clean text extraction
  -> compact SignalRecord rows
  -> SQLite/dashboard
```

The crawler:

- crawls only configured seed URLs
- respects `robots.txt` by default
- follows only same-host links when a seed enables `follow_links`
- caps total pages with `INTERNET_RADAR_CRAWLER_MAX_TOTAL_PAGES`
- caps per-seed pages with `INTERNET_RADAR_CRAWLER_MAX_PAGES_PER_SEED`
- stores title, summary, URL, content hash, text length, and link count
- does not store raw HTML

Use these env vars to tune it:

```bash
INTERNET_RADAR_ENABLE_CRAWLER=1
INTERNET_RADAR_CRAWL_SEEDS=config/crawl_seeds.yaml
INTERNET_RADAR_CRAWLER_MAX_TOTAL_PAGES=8
INTERNET_RADAR_CRAWLER_MAX_PAGES_PER_SEED=2
INTERNET_RADAR_CRAWLER_RESPECT_ROBOTS=1
INTERNET_RADAR_CRAWLER_TIMEOUT_SECONDS=8
```

## Core Data Model

Every source is converted into this common shape:

```text
SignalRecord
  id: stable unique id
  topic: normalized topic
  title: display title
  source: source name
  category: code/social/news/jobs/hackathons/research/finance/search/app_stores
  url: source link
  score: 0-100 primary score
  velocity: numeric momentum metric
  summary: short text
  observed_at: timestamp
  metadata: source-specific extra data
```

The `score` field is the main ranking score. It is always clamped to `0-100`.

## Full Collection Flow

`run_radar_once()` in `internet_radar/pipeline.py` does this:

1. Decide live or sample mode.
2. Build the collector list.
3. Run collectors in parallel with `collect_from_sources()`.
4. Build source health:
   - `live (N)`
   - `fallback (N)`
   - `error: message`
5. Flatten all collector results into one signal list.
6. Deduplicate signals.
7. Store them in SQLite.
8. Read back up to `INTERNET_RADAR_DASHBOARD_SIGNAL_LIMIT` signals, default `500`.
9. Ask the LLM router which model path would be used.
10. Build pipeline analysis artifacts: summary, classifications, gap analysis, trend predictions, idea validation, daily briefing, and LLM insight.
11. Return a `BriefingPayload`.

The app keeps 500 signals for dashboard tabs because some categories, like hackathons, can have lower raw scores than code/social signals. Keeping only the global top 100 can hide whole tabs.

## Deduplication

Deduplication uses normalized `topic + title`.

```text
dedupe_key = lowercase(topic + title)
dedupe_key = remove punctuation and repeated spaces
```

If two signals have the same key, the app keeps the one with the higher `(score, observed_at)`.

## Storage

SQLite table:

```text
signals(
  id,
  topic,
  title,
  source,
  category,
  url,
  score,
  velocity,
  summary,
  observed_at,
  metadata
)
```

`metadata` is stored as JSON text.

The dashboard also uses `data/latest_payload.json`. This keeps the app responsive because the dashboard can load the latest successful payload instead of recollecting everything on every page load.

## Dashboard Rendering

`dashboard/app.py` renders:

1. Top metrics.
2. Free-only guardrails.
3. Daily report export.
4. Top Signals Preview.
5. Source Health.
6. All radar tabs.

The URL columns use Streamlit `LinkColumn`, so links are clickable.

The top preview and visible data tables use balanced ordering. This prevents one source, such as `crates.io`, from filling the first screen.

Display balancing does not change stored data. It only changes table order:

```text
group signals by source
round-robin sources
for preview: max 2 per source first
if not enough sources exist, release the cap and fill remaining rows
```

## Dashboard Pages

### Morning Intelligence Briefing

Purpose: show the most important overall signals.

Built from all signals.

Shows:

- signal summary
- daily brief
- act-now alerts
- visible data
- category chart
- source chart
- CSV export
- signal detail JSON

Calculation:

```text
top signals = stored signals sorted by score desc, observed_at desc
act_now = signals with score >= 85, otherwise top 3-5 signals
narrative = top topic + signal count + active sources + category coverage
```

### GitHub Radar

Purpose: show repositories, packages, and developer tooling movement.

Uses code sources like:

- GitHub Search
- GitHub Trending
- GitLab Explore
- MCP Servers Directory
- PyPI
- npm
- crates.io
- Docker Hub
- RubyGems
- Libraries.io

Project detail suggests an action based on score:

```text
score >= 90 -> watch now and inspect
score >= 75 -> track and compare
else        -> background context
```

### Hackathon Radar

Purpose: show contests and hackathon opportunities.

Uses:

- Devpost
- MLH
- Codeforces
- LeetCode Contests
- HackerEarth when keyed

The tab appears when stored dashboard signals include category `hackathons`. The app now keeps 500 signals so hackathons do not disappear behind higher-scored sources.

### Internship Radar

Purpose: show job and internship opportunities.

Uses:

- RemoteOK
- The Muse
- Arbeitnow
- YC Jobs
- Adzuna when keyed
- Greenhouse Jobs
- Lever Jobs

The domain scorer adds an `internship_score` in metadata.

### Startup Gap Finder

Purpose: find product ideas from repeated pain.

Input categories:

```text
social
news
app_stores
```

Flow:

```text
signals
  -> sentiment/frustration scoring
  -> keep signals with frustration >= 45
  -> group by normalized topic
  -> require repeated complaints
  -> choose best quote
  -> calculate startup gap score
  -> create idea card
  -> validate idea against all evidence
```

Idea cards show:

- problem
- evidence quote
- complaint count
- pain level
- score
- market size
- competition level
- MVP difficulty
- recommended next step

### Multi-Source Trend Velocity

Purpose: show which topics are appearing across multiple sources.

It builds:

- source agreement
- trend correlations
- trend predictions

A topic confirmed by multiple sources gets stronger.

### Research Radar

Purpose: show academic and research momentum.

Uses:

- arXiv
- OpenAlex
- Crossref
- Europe PMC
- PubMed
- bioRxiv
- medRxiv
- Papers With Code
- Hugging Face Models/Papers
- Wikipedia Pageviews
- Conference RSS

It adds research-specific scores and academic momentum tables.

### Funding Radar

Purpose: show market validation and money movement.

Uses:

- YC Companies
- SEC EDGAR
- Grants.gov
- USAspending
- Yahoo Finance
- CoinGecko
- OpenCollective
- Crunchbase only when not free-only and keyed

It builds funding signals from finance records and related job/hackathon records.

### Skill Radar

Purpose: recommend skills that are heating up.

Uses:

```text
jobs + code + research
```

It extracts skills from titles, summaries, topics, and metadata. It excludes skills already in your profile.

### Community Pulse

Purpose: show developer/social discussion and sentiment.

Uses social sources and sentiment counts:

```text
positive
neutral
negative
```

### App Store Pain Miner

Purpose: find product pain in app-store-like sources.

Uses:

- iTunes App Store
- Google Play
- Steam
- F-Droid

App-store signals get a frustration bonus because reviews are a strong pain source.

### Radar Search

Purpose: search collected signals.

It performs keyword matching, optional profile relevance, optional semantic fallback, and a deep-dive summary.

### Your Profile

Reads `config/interests.yaml`.

Current profile fields:

```text
skills
interests
goals
blocked_topics
alert_threshold
notification_channels
llm_preference
```

The profile affects:

- relevance score
- personalized feed
- skill recommendations
- alerts
- search ranking

## Primary Source Scores

Collectors convert different source metrics into a `score` from 0 to 100. The formulas are intentionally simple and source-specific.

Examples:

### Hacker News

```text
points = score or points
comments = descendants or num_comments
signal_score = min(points // 3 + comments // 2, 100)
velocity = points
```

### Dev.to

```text
reactions = public_reactions_count
signal_score = min(35 + reactions, 100)
velocity = reactions
```

### RemoteOK

```text
if tags include ai/python/ml/machine learning:
  signal_score = 70
else:
  signal_score = 55
velocity = signal_score
```

### GitHub Search

```text
stars = stargazers_count
signal_score = min(50 + stars // 500, 100)
velocity = stars
```

### crates.io

```text
downloads = downloads
recent = recent_downloads
signal_score = min(58 + recent // 10000 + downloads // 1000000, 100)
velocity = max(recent, downloads, 1)
```

This is why crates can score very high: large Rust packages have huge download counts. The dashboard balances display so those do not dominate the first rows.

### Docker Hub

```text
pulls = pull_count
stars = star_count
signal_score = min(58 + pulls // 100000 + stars // 50, 100)
velocity = max(pulls, stars, 1)
```

### RubyGems

```text
downloads = downloads or version_downloads
signal_score = min(58 + downloads // 10000, 100)
velocity = max(downloads, 1)
```

### Grants.gov

```text
if title includes ai/technology/research/innovation:
  signal_score = 72
else:
  signal_score = 60
velocity = 1
```

### USAspending

```text
amount = award amount
signal_score = min(60 + amount // 1000000, 100)
velocity = max(amount, 1)
```

### iTunes App Store

```text
rating = averageUserRating
pain_bonus = 20 if 0 < rating < 3 else 0
signal_score = min(55 + pain_bonus + userRatingCount // 100, 100)
velocity = rating
```

## Domain Scores

The raw `SignalRecord.score` comes from the collector. The dashboard then adds domain scores into `metadata`, such as:

```text
research_score
funding_score
hackathon_score
internship_score
startup_gap_score
trend_score
```

These are shown as `domain_score` in tables and used by page-specific views.

## Historical Velocity

Every pipeline run writes numeric metrics to SQLite:

```text
signal_snapshots
  run_id
  signal_id
  topic/title/source/category
  metric
  value
  observed_at
```

The snapshot writer stores:

```text
score
velocity
numeric metadata fields such as stars, downloads, recent_downloads,
views, citations, amount, participants, result_count, pull_count
```

The historical velocity engine picks the best available metric for each signal. It prefers direct demand metrics before raw score:

```text
stars
recent_downloads
downloads
pull_count
views
citations
result_count
participants
current_participants
amount
score
velocity
```

For a current value and older baselines:

```text
delta_3d = current_value - value_3d_ago
delta_7d = current_value - value_7d_ago

acceleration_3d_per_day = delta_3d / 3
acceleration_7d_per_day = delta_7d / 7

velocity_score = clamp(((current_value - value_3d_ago) / value_3d_ago) * 100, 0, 100)
```

Direction:

```text
current > baseline -> up
current < baseline -> down
equal              -> flat
no baseline        -> new
```

Confidence:

```text
3-day and 7-day baselines -> 90
3-day baseline only       -> 70
previous run only         -> 55
new signal                -> 35
```

The Trend Velocity page shows the resulting `HistoricalTrend` rows in a Historical Velocity table.

## Trend Score

Used for code/search/news and signals with trend metadata.

Formula:

```text
velocity_score = min(velocity_score or velocity, 30)
source_count = min(confirming_sources * 5, 25)
timing_score = timing_bonus(phase) * 25
funding_bonus = 20 if funding_detected else 0

trend_score = min(sum(components), 100)
```

Timing bonus:

```text
EMERGING     -> 1.0
ACCELERATING -> 0.8
PEAKING      -> 0.3
DECLINING    -> 0.0
unknown      -> 0.5
```

## Startup Gap Score

Used for pain-heavy social/news/app-store signals.

Formula:

```text
pain_intensity = min(complaint_count / 10, 30)
market_signals = market_score * 20
competition_gap = (1 - competition_score) * 20
tech_feasible = feasibility_score * 15
timing = timing_bonus(trend_phase) * 15

startup_gap_score = min(sum(components), 100)
```

Recommendation:

```text
score >= 75 -> validate now
score >= 55 -> interview users
else        -> watch
```

## Sentiment And Frustration Score

The app detects pain terms from built-in words plus `config/gap_patterns.yaml`.

Pain examples:

```text
broken
expensive
manual
slow
hard to debug
keeps breaking
```

Formula:

```text
pain_terms = matched pain terms in topic/title/summary/source
positive_hits = matched positive terms
rating_penalty = 20 if rating is below 3 stars
source_bonus = 10 for app_stores, 8 for social, 0 otherwise
weighted_pain = sum(configured pain weights)

frustration_score =
  min(max(len(pain_terms) * 18, weighted_pain * 12)
      + rating_penalty
      + source_bonus,
      100)

sentiment_score =
  clamp(50 + positive_hits * 15 - frustration_score // 2, 0, 100)
```

Label:

```text
frustration_score >= 45 -> negative
positive_hits > 0 and frustration < 30 -> positive
else -> neutral
```

Startup Gap Finder keeps signals with frustration score at least `45`.

## Research Score

Formula:

```text
paper_velocity = min(papers_per_week * 2, 30)
citation_growth = min(citation_velocity * 2, 25)
institution_quality = min(top_institution_count * 2, 20)
github_code = 20 if has_code_repos else 0
industry_adoption = min(industry_mentions * 5, 15)

research_score = min(sum(components), 100)
```

Academic signals group research records by topic. The final academic score is:

```text
calculated_score = research formula above
observed_score = average raw score for topic records
source_bonus = min(unique_source_count * 3, 12)

academic_score = max(calculated_score, min(observed_score + source_bonus, 100))
```

## Funding Score

Formula:

```text
amount_signal = min(log10(amount + 1) * 5, 35)
investor_quality = premium investor score or investor count score
freshness = 20 if <= 7 days, 15 if <= 30, 8 if <= 90, else 3
hiring_signal = min(related_jobs * 3, 15)
sector_signal = 10 if sector contains ai/developer/automation/agent else 5

funding_score = min(sum(components), 100)
```

Market validation label:

```text
score >= 80 -> high
score >= 55 -> medium
else        -> watch
```

Premium investors:

```text
a16z, sequoia, yc, accel, benchmark, greylock, lightspeed
```

## Hackathon Score

Formula:

```text
prize_score = min(log10(prize_pool + 1) * 12, 30)
crowd_score = (1 - crowd_ratio) * 25
urgency_score = urgency(days_left) * 15
sponsor_score = sponsor_quality(sponsors) * 15
remote_score = 10 if remote else 0
skill_match = skill_match(theme, user_profile) * 5

hackathon_score = min(sum(components), 100)
```

Urgency:

```text
days_left <= 0  -> 0.0
days_left <= 7  -> 1.0
days_left <= 21 -> 0.7
else            -> 0.4
```

Recommendation:

```text
score >= 85 -> apply now
score >= 65 -> watch
else        -> wait
```

Crowd prediction:

```text
projected_participants = current + daily_growth * days_left
crowd_ratio = projected_participants / capacity

if days_left <= 0 -> EXPIRED
if days_left <= 14 and crowd_ratio <= 0.65 -> APPLY NOW
if crowd_ratio <= 0.85 -> WATCH
else -> WAIT
```

## Internship Score

Formula:

```text
freshness = freshness_score(posted_hours_ago) * 30
low_applicants = (1 - applicant_ratio) * 25
company_health = company_growth/company_health * 20
skill_match = skill_match(description, user_profile) * 25

internship_score = min(sum(components), 100)
```

Freshness:

```text
posted < 6h    -> 1.0
posted < 24h   -> 0.8
posted < 72h   -> 0.6
posted < 168h  -> 0.3
older          -> 0.1
```

Recommendation:

```text
score >= 80 -> apply today
score >= 60 -> shortlist
else        -> watch
```

## Cross-Source Agreement

Groups signals by normalized topic.

Multiplier:

```text
source_count >= 5 -> 1.30
source_count >= 3 -> 1.15
else              -> 1.00
```

Score:

```text
agreement_score = min(max_topic_signal_score * multiplier, 100)
```

Verdict:

```text
source_count >= known_source_count -> ACT NOW
source_count >= 3                  -> STRONG
source_count >= 2                  -> WEAK SIGNAL
else                               -> SINGLE SOURCE - WATCH
```

## Trend Correlation

Groups by topic and requires at least two sources.

Formula:

```text
average_score = mean(signal.score)
average_velocity = mean(signal.velocity)

correlation_score =
  average_score * 0.55
  + min(source_count * 13, 35)
  + min(category_count * 8, 25)
  + min(average_velocity / 10, 10)

correlation_score = min(correlation_score, 100)
```

Verdict:

```text
5+ sources or 5+ categories -> ACT NOW
3+ sources or 3+ categories or score >= 80 -> STRONG
else -> WEAK SIGNAL
```

## Relevance Score

Personal relevance is based on `config/interests.yaml`.

Formula:

```text
start = 35
+30 for each matching interest
+18 for each matching skill
+12 for each matching goal
+min(signal.score // 10, 10)
cap at 100
```

If a blocked topic appears, relevance is `0`.

Goal matches:

```text
intern goal    -> jobs
hackathon goal -> hackathons
startup goal   -> pain/gap/complaint/abandoned
learn goal     -> jobs/research/code
```

The personalized feed ranks by:

```text
relevance_score + signal.score
```

## Skill Recommendation Score

Skill Radar extracts skills from:

- metadata `skills`
- topic
- title
- summary
- known keyword map

Known examples:

```text
agent -> agents
browser automation -> playwright
llm -> llm
ollama -> ollama
mcp -> mcp
streamlit -> streamlit
typescript -> typescript
```

It skips skills already listed in your profile.

Formula:

```text
average_score = mean(signal.score)
average_velocity = mean(signal.velocity)

skill_score =
  average_score * 0.65
  + min(signal_count * 12, 28)
  + min(source_count * 5, 15)
  + min(average_velocity / 3, 8)

skill_score = clamp(skill_score, 0, 100)
```

## Radar Search Score

For keyword search:

```text
term_hits = number of query terms found
exact_bonus = 25 if full query appears in signal text
relevance_bonus = profile_relevance // 4, if profile exists

match_score =
  min(signal.score + term_hits * 15 + exact_bonus + relevance_bonus, 200)
```

If semantic search is enabled and keyword results are too few, vector search can add results:

```text
semantic_match_score = min(similarity * 100 + signal.score // 2, 200)
```

## Semantic Clusters

Semantic clusters use deterministic labels:

```text
resume/cv            -> resume
browser/automation   -> browser agents
mcp/model context    -> mcp
local llm/ollama     -> local llm
else                 -> first topic word
```

Clusters require at least two signals.

Cluster fields:

```text
label
signal_ids
sources
size
top keywords
```

## Alert Score

Alerts are built from signals and your profile.

Formula:

```text
alert_score = max(signal.score, relevance_score if present)
```

The alert fires only if:

```text
alert_score >= profile.alert_threshold
```

Default profile threshold is `80`.

Alert kind:

```text
hackathons -> HACKATHON
research -> RESEARCH_SIGNAL
finance -> FUNDING_ALERT
social/app_stores/pain metadata -> STARTUP_GAP
else -> SKILL_RADAR
```

Default channel is `ntfy`, unless profile notification channels override it.

Failed dispatches are written to SQLite in `alert_outbox` with the signal, channel, attempt count, last error, and status. The scheduler passes `INTERNET_RADAR_ALERT_OUTBOX_DB` (or `INTERNET_RADAR_DB`) into alert dispatch, so ntfy timeouts or missing downstream channels remain visible and retryable instead of being lost. The `alert_outbox_retry` APScheduler job runs every 15 minutes and retries up to `INTERNET_RADAR_ALERT_OUTBOX_RETRY_LIMIT` due pending rows. Recent repeated failures use exponential backoff, while the CLI `--force-alert-retry` flag can probe recovery immediately.

## LLM Routing

The app can use local or online models, but has deterministic fallback.

Routing rules:

```text
very large content > 50,000 chars -> Gemini
preferred local Ollama model exists -> Ollama
heavy task and no local model -> Groq
nontrivial task and no local model -> OpenRouter
classification/sentiment/keywords with no model -> deterministic rules
```

Common local preferences:

```text
classify/sentiment/keywords -> phi3:mini, qwen2.5:0.5b
summarize/score/filter -> llama3.2, qwen2.5:0.5b
gap_analysis/idea/trend -> mistral, llama3.2, qwen2.5:0.5b
```

The dashboard shows the route as:

```text
provider:model
```

When `INTERNET_RADAR_ENABLE_LLM_ANALYSIS=1`, the pipeline also makes one bounded JSON generation call for the Morning Intelligence Briefing. The prompt includes only the top signals and asks for a headline, narrative, opportunities, risks, actions, and confidence. If the selected LLM is unavailable or returns invalid JSON, the app stores a deterministic fallback insight instead of failing collection.

## Semantic Embeddings

Radar Search can use deterministic local embeddings or provider-backed embeddings.

Routing order:

```text
Ollama nomic-embed-text installed -> local Ollama embeddings
GEMINI_API_KEY set                -> Gemini gemini-embedding-2
COHERE_API_KEY set                -> Cohere embed-english-light-v3.0
otherwise                         -> deterministic hashed bag-of-words
```

The local `.env` can force Gemini-backed semantic search with:

```text
INTERNET_RADAR_VECTOR_BACKEND=gemini
```

Gemini embeddings use the Gemini API `embedContent` REST endpoint and request 768 output dimensions to keep vectors smaller while still using provider-backed semantic similarity.

## Morning Intelligence Briefing Calculation

The briefing uses all dashboard signals.

```text
ranked = sort by score desc, velocity desc
top_signal = ranked[0]
act_now = signals with score >= 85, limited to 5
if no act_now: use top 3-5
job_market = top jobs
research = top research
opportunities = top hackathons/finance/app_stores
```

Narrative:

```text
Top topic is X at score Y.
N signals across M active sources cover categories A, B, C.
Use Act Now list first, then job and research momentum.
```

## Startup Gap Finder Calculation

Startup Gap Finder has two passes:

### Pass 1: Sentiment/Frustration

For each social/news/app-store signal:

```text
calculate frustration_score
keep if frustration_score >= 45
group by normalized topic
```

### Pass 2: Cluster And Idea

For each group:

```text
complaint_count = number of frustrated signals
pain_level = average frustration / 10, clamped 1-10
best_quote = highest frustration and highest score signal
score = StartupGapScorer formula
startup_idea = "Build a simpler fix for <problem> focused on repeated pain"
```

### Idea Card Fields

```text
Problem: normalized topic
Evidence: best quote
Complaints: count
Pain: 1-10
Score: startup gap score
Who pays / market: large/medium/small
Competition: low if pain >= 8 else medium
MVP difficulty: medium if score >= 60 else low
Next step: interview users/prototype if score strong, otherwise watch
```

### Build-First Logic

```text
build_first = score >= 70 and pain_level >= 5
```

If `build_first` is true:

```text
Interview users and prototype the narrow fix.
```

Otherwise:

```text
Keep watching for more complaints.
```

## Idea Validation Calculation

For each generated idea:

Evidence counts:

```text
pain = count(frustration >= 45 or social/app_stores)
funding = count(finance)
research = count(research)
jobs = count(jobs)
code = count(code)
source_count = unique sources
```

Score:

```text
score = 25
+ min(pain * 15, 25)
+ min(funding * 20, 25)
+ min(research * 12, 15)
+ min(jobs * 10, 15)
+ min(code * 10, 12)
+ min(source_count * 3, 12)
+ 6 if idea mentions one of your profile skills
cap at 100
```

Validation:

```text
score >= 80 -> strong, build prototype
score >= 60 -> moderate, validate with users
else        -> weak, watch for more evidence
```

Risks:

```text
source_count < 3 -> needs broader source confirmation
no funding -> no direct funding validation yet
painful signal exists -> include first pain quote
```

## Source Health Calculation

The collector runner examines returned signals.

```text
if collector raises:
  status = error: message
elif all returned signals are fallback signals:
  status = fallback (N)
else:
  status = live (N)
```

A fallback signal is detected when:

```text
metadata.fallback is true
or metadata.requires_api_key is true
or id starts with source-fallback:
or id starts with keyed-fallback:
```

Active sources:

```text
active_sources = count(status not starting with "error")
```

## Top Signals And Tables

Stored signal order:

```text
ORDER BY score DESC, observed_at DESC
LIMIT dashboard_signal_limit
```

Default dashboard limit:

```text
INTERNET_RADAR_DASHBOARD_SIGNAL_LIMIT or 500
```

Visible table order:

```text
balanced by source
clickable URL column
CSV export still includes raw URLs
```

This solves the issue where `crates.io` produced many high-scoring records and filled the first screen.

## Scheduler

The scheduler defines cadence groups:

| Group | Examples |
| --- | --- |
| high frequency | GitHub trending, hackathon deadlines, career page watcher, HN front page |
| hourly | Reddit, Bluesky, Mastodon, Dev.to, RSS, RemoteOK |
| three hourly | GitHub search, Product Hunt, package velocity, Google Trends, Devpost, Adzuna |
| six hourly | cross-source validation, gap finder, sentiment, semantic clustering, scoring, arXiv, OpenAlex |
| daily | daily briefing, YC companies, Wikipedia pageviews, SEC EDGAR, Skill Radar, app-store pain mining |

Smart triggers:

```text
score > 90 -> immediate alert
hackathon participant growth >= 50 -> crowd alert
same topic from 3+ sources in 1 hour -> deep analysis
```

The runnable entrypoint is:

```bash
python run_scheduler.py
```

It builds an APScheduler `BlockingScheduler` with a persistent SQLite job store:

```text
INTERNET_RADAR_SCHEDULER_DB=data/scheduler_jobs.sqlite
INTERNET_RADAR_SCHEDULER_HEARTBEAT_MAX_AGE_MINUTES=30
```

Scheduler startup, daemon keepalives, every named scheduler job, and every `scheduler/runner.py --once` cycle write rows to `scheduler_heartbeats` in `INTERNET_RADAR_DB`. The Make It Real readiness audit uses the latest fresh heartbeat as runtime evidence that scheduled collection is actually alive; by default, heartbeats older than 30 minutes are treated as stale.

This lets job definitions survive process restarts. SQLite remains the source of truth for both current signals and historical snapshots, while dashboard distribution analytics can run through DuckDB when `INTERNET_RADAR_ANALYTICS_BACKEND=auto` or `duckdb`. If DuckDB is unavailable, the app falls back to the lightweight Python analytics path.

## Alert Dispatch

Supported channels:

```text
ntfy
telegram
discord
email via Mailgun
```

In free-only mode, Mailgun credentials are blanked out so email dispatch stays disabled.

If a configured channel fails, the dispatch result is persisted in `alert_outbox`. Automatic scheduler alerts first filter profile channels to the channels that are credential-ready, which prevents known-missing channels from generating repeated failures. Repeated failures for the same signal/channel update the existing pending row and increment attempts instead of creating unbounded duplicates. Retried rows move to `sent` after successful delivery; unconfigured channels are skipped until credentials exist, and recent repeated failures wait for exponential backoff before another automatic attempt. Other failures remain `pending` with the latest error. The Make It Real readiness audit treats pending outbox rows for currently configured channels as an alert-delivery blocker, so the app does not claim phone alerts are working only because a topic or token is configured; pending rows for unconfigured channels remain visible but are covered by their own credential blockers. The Profile page includes the latest outbox rows next to channel readiness, and the scheduler automatically runs the retry job while the background process is active.

Alert readiness is also exposed:

```text
ntfy      -> ready when INTERNET_RADAR_NTFY_TOPIC is set
telegram  -> ready when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set
discord   -> ready when DISCORD_WEBHOOK_URL is set
email     -> disabled by free-only mode, otherwise requires Mailgun and email addresses
```

## Why Some Tabs Can Look Empty

Common reasons:

1. Sidebar source groups exclude that category.
2. Sidebar search/min-score/source filter hides rows.
3. The latest cache was built before new collectors or dashboard changes.
4. A source returned fallback only.
5. A category's signals are lower scoring than the global top signals.

Current mitigation:

- dashboard keeps 500 signals
- tables are source-balanced
- Source Health shows live/fallback/error clearly
- refresh button rebuilds the payload

## Files To Edit For Common Changes

| Change | File |
| --- | --- |
| Add a source to registry | `internet_radar/sources/registry.py` |
| Add live source collection | `internet_radar/collectors/live.py` |
| Change source health behavior | `internet_radar/collectors/runner.py` |
| Change dashboard tabs | `internet_radar/dashboard_data.py` and `dashboard/app.py` |
| Change score formulas | `internet_radar/scoring/*.py` |
| Change Startup Gap logic | `internet_radar/signals/gap_finder.py`, `internet_radar/brain/gap_analyzer.py` |
| Change profile interests | `config/interests.yaml` |
| Change pain terms | `config/gap_patterns.yaml` |
| Change alerts | `internet_radar/alerts/*.py` |
| Change schedule | `internet_radar/scheduler/jobs.py` |

## Current Safety Rules

Keep these true unless intentionally changing behavior:

```text
INTERNET_RADAR_FREE_ONLY=1
Brave Search disabled
Crunchbase disabled
Mailgun disabled
SQLite default storage
Ollama local-first when available
fallbacks instead of hard failures
```

## Verification Checklist

After changing app behavior:

```bash
uv run pytest -q
curl -sS http://127.0.0.1:8501/_stcore/health
```

Useful runtime check:

```bash
uv run python - <<'PY'
from internet_radar.storage.payload_cache import load_briefing_payload

payload = load_briefing_payload()
print("signals", payload.signals_24h)
print("categories", sorted({s.category for s in payload.top_signals}))
print("status prefixes", sorted({v.split(" ", 1)[0] for v in payload.source_health.values()}))
PY
```

Expected healthy state:

```text
health endpoint -> ok
source health -> live/fallback/error, not ambiguous
dashboard has clickable links
top preview has mixed sources
category tabs have data when sources returned that category
```
