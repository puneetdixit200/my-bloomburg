from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from typing import Any

from internet_radar.collectors.base import HTTPCollector
from internet_radar.special.radar import build_special_signals
from internet_radar.storage.models import SignalRecord


DEFAULT_TOPICS = ["browser agents", "local llm", "mcp", "streamlit", "agentic ai"]


def infer_topic(title: str) -> str:
    cleaned = re.sub(r"^(show hn:|ask hn:|launch hn:)\s*", "", title.strip(), flags=re.I)
    cleaned = re.sub(r"[^A-Za-z0-9.+# -]+", "", cleaned).strip().lower()
    words = cleaned.split()
    return " ".join(words[:5]) if words else "technology trend"


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return default


def _payload_list(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        value = payload.get(key, [])
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def parse_hackernews_items(items: list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in items:
        title = html.unescape(str(item.get("title") or "Untitled HN item"))
        points = int(item.get("score") or item.get("points") or 0)
        comments = int(item.get("descendants") or item.get("num_comments") or 0)
        score = min(points // 3 + comments // 2, 100)
        records.append(
            SignalRecord(
                id=f"hn:{item.get('id', title)}",
                topic=infer_topic(title),
                title=title,
                source="Hacker News",
                category="social",
                url=str(item.get("url") or f"https://news.ycombinator.com/item?id={item.get('id', '')}"),
                score=score,
                velocity=points,
                metadata={"comments": comments},
            )
        )
    return records


def parse_devto_articles(items: list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in items:
        title = str(item.get("title") or "Dev.to article")
        reactions = int(item.get("public_reactions_count") or 0)
        tags = item.get("tag_list") or []
        records.append(
            SignalRecord(
                id=f"devto:{item.get('id', title)}",
                topic=infer_topic(" ".join(tags) if tags else title),
                title=title,
                source="Dev.to",
                category="news",
                url=str(item.get("url") or ""),
                score=min(35 + reactions, 100),
                velocity=reactions,
                metadata={"tags": tags},
            )
        )
    return records


def parse_remoteok_jobs(items: list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in items:
        if not item.get("position"):
            continue
        title = f"{item.get('position')} at {item.get('company', 'Unknown')}"
        tags = [str(tag).lower() for tag in item.get("tags") or []]
        score = 70 if any(tag in {"ai", "python", "ml", "machine learning"} for tag in tags) else 55
        records.append(
            SignalRecord(
                id=f"remoteok:{item.get('id', title)}",
                topic=infer_topic(" ".join(tags) if tags else str(item.get("position"))),
                title=title,
                source="RemoteOK",
                category="jobs",
                url=str(item.get("url") or ""),
                score=score,
                velocity=score,
                metadata={"tags": tags},
            )
        )
    return records


def parse_arxiv_feed(text: str) -> list[SignalRecord]:
    root = ET.fromstring(text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    records: list[SignalRecord] = []
    for entry in root.findall("atom:entry", ns):
        title = " ".join((entry.findtext("atom:title", default="", namespaces=ns) or "").split())
        summary = " ".join((entry.findtext("atom:summary", default="", namespaces=ns) or "").split())
        url = entry.findtext("atom:id", default="", namespaces=ns) or ""
        if not title:
            continue
        records.append(
            SignalRecord(
                id=f"arxiv:{url or title}",
                topic=infer_topic(title),
                title=title,
                source="arXiv",
                category="research",
                url=url,
                score=72,
                velocity=1,
                summary=summary[:280],
            )
        )
    return records


def parse_github_repositories(items: list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in items:
        title = str(item.get("full_name") or item.get("name") or "GitHub repository")
        stars = int(item.get("stargazers_count") or 0)
        records.append(
            SignalRecord(
                id=f"github:{item.get('id', title)}",
                topic=infer_topic(" ".join(item.get("topics") or []) or title),
                title=title,
                source="GitHub Search",
                category="code",
                url=str(item.get("html_url") or ""),
                score=min(50 + stars // 500, 100),
                velocity=stars,
                summary=str(item.get("description") or "")[:280],
                metadata={"language": item.get("language"), "stars": stars},
            )
        )
    return records


def parse_reddit_children(children: list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for child in children:
        item = child.get("data", child)
        title = str(item.get("title") or "Reddit discussion")
        ups = int(item.get("ups") or item.get("score") or 0)
        records.append(
            SignalRecord(
                id=f"reddit:{item.get('id', title)}",
                topic=infer_topic(title),
                title=title,
                source="Reddit JSON",
                category="social",
                url=f"https://reddit.com{item.get('permalink', '')}" if item.get("permalink") else str(item.get("url") or ""),
                score=min(40 + ups // 10, 100),
                velocity=ups,
                metadata={"subreddit": item.get("subreddit")},
            )
        )
    return records


def parse_rss_entries(text: str) -> list[SignalRecord]:
    titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>", text, flags=re.I | re.S)
    links = re.findall(r"<link>(.*?)</link>", text, flags=re.I | re.S)
    records: list[SignalRecord] = []
    for index, title_pair in enumerate(titles[1:8]):
        title = html.unescape(next((part for part in title_pair if part), "")).strip()
        if not title:
            continue
        records.append(
            SignalRecord(
                id=f"rss:{index}:{title}",
                topic=infer_topic(title),
                title=title,
                source="Tech RSS",
                category="news",
                url=links[index + 1] if index + 1 < len(links) else "",
                score=58,
                velocity=1,
            )
        )
    return records


def parse_lobsters_stories(items: list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in items:
        title = str(item.get("title") or "Lobsters story")
        score = _as_int(item.get("score"))
        comments = _as_int(item.get("comments_count"))
        records.append(
            SignalRecord(
                id=f"lobsters:{item.get('short_id', title)}",
                topic=infer_topic(title),
                title=title,
                source="Lobsters",
                category="news",
                url=str(item.get("url") or item.get("comments_url") or ""),
                score=min(45 + score + comments, 100),
                velocity=score + comments,
                metadata={"comments": comments},
            )
        )
    return records


def parse_themuse_jobs(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "results"):
        title = str(item.get("name") or "The Muse job")
        company = str((item.get("company") or {}).get("name") or "Unknown")
        categories = [str(category.get("name", "")).lower() for category in item.get("categories") or [] if isinstance(category, dict)]
        full_title = f"{title} at {company}"
        score = 72 if "intern" in title.lower() or "engineering" in categories else 58
        records.append(
            SignalRecord(
                id=f"themuse:{item.get('id', full_title)}",
                topic=infer_topic(" ".join(categories) if categories else title),
                title=full_title,
                source="The Muse",
                category="jobs",
                url=str((item.get("refs") or {}).get("landing_page") or ""),
                score=score,
                velocity=score,
                metadata={"categories": categories},
            )
        )
    return records


def parse_arbeitnow_jobs(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "data"):
        title = str(item.get("title") or "Arbeitnow job")
        company = str(item.get("company_name") or "Unknown")
        tags = [str(tag).lower() for tag in item.get("tags") or []]
        score = 72 if any(tag in {"ai", "python", "machine learning", "ml"} for tag in tags) else 57
        records.append(
            SignalRecord(
                id=f"arbeitnow:{item.get('slug', title)}",
                topic=infer_topic(" ".join(tags) if tags else title),
                title=f"{title} at {company}",
                source="Arbeitnow",
                category="jobs",
                url=str(item.get("url") or ""),
                score=score,
                velocity=score,
                metadata={"tags": tags},
            )
        )
    return records


def parse_codeforces_contests(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "result"):
        if str(item.get("phase", "")).upper() not in {"BEFORE", "CODING"}:
            continue
        title = str(item.get("name") or "Codeforces contest")
        starts_in = abs(_as_int(item.get("relativeTimeSeconds")))
        score = 75 if starts_in <= 7 * 24 * 3600 else 60
        records.append(
            SignalRecord(
                id=f"codeforces:{item.get('id', title)}",
                topic=infer_topic(title),
                title=title,
                source="Codeforces",
                category="hackathons",
                url=f"https://codeforces.com/contest/{item.get('id', '')}",
                score=score,
                velocity=max(1, starts_in),
                metadata={"phase": item.get("phase"), "starts_in_seconds": starts_in},
            )
        )
    return records


def parse_openalex_works(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "results"):
        title = str(item.get("display_name") or "OpenAlex work")
        citations = _as_int(item.get("cited_by_count"))
        institutions = []
        for authorship in item.get("authorships") or []:
            if isinstance(authorship, dict):
                institutions.extend(str(inst.get("display_name")) for inst in authorship.get("institutions") or [] if isinstance(inst, dict))
        records.append(
            SignalRecord(
                id=f"openalex:{item.get('id', title)}",
                topic=infer_topic(title),
                title=title,
                source="OpenAlex",
                category="research",
                url=str(item.get("id") or ""),
                score=min(62 + citations // 5, 100),
                velocity=citations,
                metadata={"citations": citations, "institutions": [name for name in institutions if name]},
            )
        )
    return records


def parse_wikipedia_pageviews(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    items = _payload_list(payload, "items")
    if not items:
        return []
    article = str(items[-1].get("article") or "Wikipedia topic")
    total_views = sum(_as_int(item.get("views")) for item in items)
    return [
        SignalRecord(
            id=f"wikipedia:{article}",
            topic=infer_topic(article.replace("_", " ")),
            title=f"{article.replace('_', ' ')} pageview momentum",
            source="Wikipedia Pageviews",
            category="research",
            url=f"https://en.wikipedia.org/wiki/{article}",
            score=min(50 + total_views // 1000, 100),
            velocity=total_views,
            metadata={"days": len(items)},
        )
    ]


def parse_coingecko_trending(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for coin in _payload_list(payload, "coins"):
        item = coin.get("item", coin)
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("id") or "CoinGecko asset")
        rank_score = _as_int(item.get("score"))
        records.append(
            SignalRecord(
                id=f"coingecko:{item.get('id', name)}",
                topic=infer_topic(name),
                title=f"{name} ({str(item.get('symbol') or '').upper()}) trending on CoinGecko".strip(),
                source="CoinGecko",
                category="finance",
                url=f"https://www.coingecko.com/en/coins/{item.get('id', '')}",
                score=max(55, 85 - rank_score * 3),
                velocity=max(1, 20 - rank_score),
                metadata={"symbol": item.get("symbol"), "rank_score": rank_score},
            )
        )
    return records


def parse_itunes_results(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "results"):
        title = str(item.get("trackName") or item.get("collectionName") or "App Store result")
        rating = float(item.get("averageUserRating") or 0)
        pain_bonus = 20 if 0 < rating < 3 else 0
        records.append(
            SignalRecord(
                id=f"itunes:{item.get('trackId', title)}",
                topic=infer_topic(title),
                title=title,
                source="iTunes App Store",
                category="app_stores",
                url=str(item.get("trackViewUrl") or ""),
                score=min(55 + pain_bonus + _as_int(item.get("userRatingCount")) // 100, 100),
                velocity=rating,
                metadata={"rating": rating, "ratings": item.get("userRatingCount")},
            )
        )
    return records


def parse_steam_featured(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    items: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        for key in ("large_capsules", "featured_win"):
            items.extend(_payload_list(payload, key))
        for section in ("top_sellers", "specials", "new_releases"):
            section_value = payload.get(section)
            if isinstance(section_value, dict):
                items.extend(_payload_list(section_value, "items"))
    else:
        items = _payload_list(payload, "items")

    records: list[SignalRecord] = []
    for item in items:
        title = str(item.get("name") or "Steam app")
        discount = _as_int(item.get("discount_percent"))
        records.append(
            SignalRecord(
                id=f"steam:{item.get('id', title)}",
                topic=infer_topic(title),
                title=title,
                source="Steam",
                category="app_stores",
                url=f"https://store.steampowered.com/app/{item.get('id', '')}",
                score=min(55 + discount, 100),
                velocity=discount,
                metadata={"image": item.get("header_image")},
            )
        )
    return records


def parse_pypi_package(package: str, payload: dict[str, Any]) -> list[SignalRecord]:
    info = payload.get("info") or {}
    summary = str(info.get("summary") or "")
    return [
        SignalRecord(
            id=f"pypi:{package}",
            topic=infer_topic(package),
            title=f"{package} package signal",
            source="PyPI",
            category="code",
            url=str(info.get("package_url") or f"https://pypi.org/project/{package}/"),
            score=64,
            velocity=1,
            summary=summary[:280],
            metadata={"version": info.get("version")},
        )
    ]


def parse_npm_package(package: str, payload: dict[str, Any]) -> list[SignalRecord]:
    description = str(payload.get("description") or "")
    return [
        SignalRecord(
            id=f"npm:{package}",
            topic=infer_topic(package),
            title=f"{package} npm package signal",
            source="npm Registry",
            category="code",
            url=str(payload.get("homepage") or f"https://www.npmjs.com/package/{package}"),
            score=64,
            velocity=1,
            summary=description[:280],
            metadata={"version": (payload.get("dist-tags") or {}).get("latest")},
        )
    ]


def parse_yc_companies(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    items = _payload_list(payload, "companies") or _payload_list(payload, "results") or _payload_list(payload, "data")
    records: list[SignalRecord] = []
    for item in items:
        name = str(item.get("name") or item.get("company") or "YC company")
        one_liner = str(item.get("one_liner") or item.get("description") or item.get("tagline") or "")
        industries = [str(industry) for industry in item.get("industries") or item.get("tags") or []]
        haystack = f"{name} {one_liner} {' '.join(industries)}".lower()
        score = 76 if any(term in haystack for term in ["ai", "agent", "developer", "automation"]) else 64
        records.append(
            SignalRecord(
                id=f"yc:{item.get('id', name)}",
                topic=infer_topic(" ".join(industries) if industries else name),
                title=f"{name} YC company signal",
                source="YC Companies",
                category="finance",
                url=str(item.get("url") or item.get("website") or "https://www.ycombinator.com/companies"),
                score=score,
                velocity=score,
                summary=one_liner[:280],
                metadata={"batch": item.get("batch"), "industries": industries},
            )
        )
    return records


def parse_sec_submissions(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    if not isinstance(payload, dict):
        return []
    company = str(payload.get("name") or payload.get("entityName") or "SEC company")
    cik = str(payload.get("cik") or payload.get("cik_str") or "").zfill(10)
    recent = ((payload.get("filings") or {}).get("recent") or {}) if isinstance(payload.get("filings"), dict) else {}
    forms = list(recent.get("form") or [])
    accessions = list(recent.get("accessionNumber") or [])
    dates = list(recent.get("filingDate") or [])
    records: list[SignalRecord] = []
    for index, form in enumerate(forms[:6]):
        form_name = str(form)
        accession = str(accessions[index]) if index < len(accessions) else f"{company}:{index}"
        filing_date = str(dates[index]) if index < len(dates) else ""
        score = 78 if form_name in {"10-K", "10-Q", "8-K", "S-1"} else 62
        records.append(
            SignalRecord(
                id=f"sec:{cik}:{accession}",
                topic=infer_topic(f"{company} {form_name}"),
                title=f"{company} filed {form_name}",
                source="SEC EDGAR",
                category="finance",
                url=f"https://www.sec.gov/edgar/browse/?CIK={cik.lstrip('0')}",
                score=score,
                velocity=score,
                summary=f"SEC filing {form_name} submitted {filing_date}".strip(),
                metadata={"cik": cik, "form": form_name, "accession": accession, "filing_date": filing_date},
            )
        )
    return records


def parse_duckduckgo_results(text: str) -> list[SignalRecord]:
    links = re.findall(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', text, flags=re.I | re.S)
    snippets = re.findall(r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>|<div[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>', text, flags=re.I | re.S)
    snippet_texts = [_clean_html(next((part for part in pair if part), "")) for pair in snippets]
    records: list[SignalRecord] = []
    for index, (url, title_html) in enumerate(links[:8]):
        title = _clean_html(title_html)
        if not title:
            continue
        summary = snippet_texts[index] if index < len(snippet_texts) else ""
        records.append(
            SignalRecord(
                id=f"duckduckgo:{index}:{title}",
                topic=infer_topic(title),
                title=title,
                source="DuckDuckGo",
                category="search",
                url=html.unescape(url),
                score=65 + min(index, 5),
                velocity=max(1, 8 - index),
                summary=summary[:280],
            )
        )
    return records


def parse_google_trends_rss(text: str) -> list[SignalRecord]:
    root = ET.fromstring(text)
    records: list[SignalRecord] = []
    for index, item in enumerate(root.findall(".//item")[:8]):
        title = (item.findtext("title") or "Google trend").strip()
        if not title:
            continue
        traffic = _traffic_to_int(_find_child_text(item, "approx_traffic"))
        news_url = _find_child_text(item, "news_item_url") or (item.findtext("link") or "")
        records.append(
            SignalRecord(
                id=f"google-trends:{index}:{title.lower()}",
                topic=infer_topic(title),
                title=f"{title} is trending on Google",
                source="Google Trends",
                category="search",
                url=news_url,
                score=min(62 + traffic // 50_000, 100) if traffic else 62,
                velocity=traffic,
                summary=_find_child_text(item, "news_item_title")[:280],
                metadata={"approx_traffic": traffic},
            )
        )
    return records


def parse_paperswithcode_results(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "results"):
        title = str(item.get("title") or "Papers With Code paper")
        repositories = [repo for repo in item.get("repositories") or [] if isinstance(repo, dict)]
        repo_stars = max([_as_int(repo.get("stars")) for repo in repositories] or [0])
        records.append(
            SignalRecord(
                id=f"pwc:{item.get('id', title)}",
                topic=infer_topic(title),
                title=title,
                source="Papers With Code",
                category="research",
                url=str(item.get("url_abs") or item.get("url") or "https://paperswithcode.com"),
                score=min(68 + repo_stars // 100, 100),
                velocity=max(1, repo_stars),
                summary=str(item.get("abstract") or "")[:280],
                metadata={"repo_stars": repo_stars},
            )
        )
    return records


def _clean_html(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def _find_child_text(element: ET.Element, local_name: str) -> str:
    for child in element.iter():
        if child.tag.rsplit("}", 1)[-1] == local_name and child.text:
            return " ".join(child.text.split())
    return ""


def _traffic_to_int(value: str) -> int:
    cleaned = value.upper().replace("+", "").replace(",", "").strip()
    if not cleaned:
        return 0
    multiplier = 1
    if cleaned.endswith("K"):
        multiplier = 1_000
        cleaned = cleaned[:-1]
    elif cleaned.endswith("M"):
        multiplier = 1_000_000
        cleaned = cleaned[:-1]
    try:
        return int(float(cleaned) * multiplier)
    except ValueError:
        return 0


class GitHubSearchCollector(HTTPCollector):
    def __init__(self, topic: str = "agentic ai") -> None:
        super().__init__(name="GitHub Search", category="code")
        self.topic = topic

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json(
                "https://api.github.com/search/repositories",
                q=f"{self.topic} pushed:>2026-01-01",
                sort="stars",
                order="desc",
                per_page=8,
            )
            return parse_github_repositories(list(data.get("items", [])))  # type: ignore[union-attr]
        except Exception:
            return sample_signals("code")


class HackerNewsCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="Hacker News", category="social")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://hn.algolia.com/api/v1/search", tags="front_page", hitsPerPage=8)
            hits = list(data.get("hits", []))  # type: ignore[union-attr]
            return parse_hackernews_items(hits)
        except Exception:
            return sample_signals("social")


class RedditJSONCollector(HTTPCollector):
    def __init__(self, subreddit: str = "LocalLLaMA") -> None:
        super().__init__(name="Reddit JSON", category="social")
        self.subreddit = subreddit

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json(f"https://www.reddit.com/r/{self.subreddit}/hot.json", limit=8)
            children = data.get("data", {}).get("children", [])  # type: ignore[union-attr]
            return parse_reddit_children(list(children))
        except Exception:
            return sample_signals("social")


class DevToCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="Dev.to", category="news")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://dev.to/api/articles", tag="ai", top=7, per_page=8)
            return parse_devto_articles(list(data))  # type: ignore[arg-type]
        except Exception:
            return sample_signals("news")


class RemoteOKCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="RemoteOK", category="jobs")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://remoteok.com/api")
            return parse_remoteok_jobs(list(data))  # type: ignore[arg-type]
        except Exception:
            return sample_signals("jobs")


class ArxivCollector(HTTPCollector):
    def __init__(self, query: str = "agentic AI") -> None:
        super().__init__(name="arXiv", category="research")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            text = self.get_text(
                "https://export.arxiv.org/api/query",
                search_query=f"all:{self.query}",
                start=0,
                max_results=8,
                sortBy="submittedDate",
                sortOrder="descending",
            )
            return parse_arxiv_feed(text)
        except Exception:
            return sample_signals("research")


class PackageCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="Package Velocity", category="code")

    def collect(self) -> list[SignalRecord]:
        signals: list[SignalRecord] = []
        for package in ["ollama", "streamlit", "playwright"]:
            try:
                pypi_payload = self.get_json(f"https://pypi.org/pypi/{package}/json")
                if isinstance(pypi_payload, dict):
                    signals.extend(parse_pypi_package(package, pypi_payload))
            except Exception:
                signals.extend(sample_signals("code")[:1])
        for package in ["ollama", "playwright"]:
            try:
                npm_payload = self.get_json(f"https://registry.npmjs.org/{package}")
                if isinstance(npm_payload, dict):
                    signals.extend(parse_npm_package(package, npm_payload))
            except Exception:
                signals.extend(sample_signals("code")[:1])
        return signals


class LobstersCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="Lobsters", category="news")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://lobste.rs/hottest.json")
            return parse_lobsters_stories(list(data))  # type: ignore[arg-type]
        except Exception:
            return sample_signals("news")


class TheMuseCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="The Muse", category="jobs")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://www.themuse.com/api/public/jobs", page=1, category="Computer and IT")
            return parse_themuse_jobs(data if isinstance(data, dict) else [])
        except Exception:
            return sample_signals("jobs")


class ArbeitnowCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="Arbeitnow", category="jobs")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://www.arbeitnow.com/api/job-board-api")
            return parse_arbeitnow_jobs(data if isinstance(data, dict) else [])
        except Exception:
            return sample_signals("jobs")


class CodeforcesCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="Codeforces", category="hackathons")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://codeforces.com/api/contest.list")
            return parse_codeforces_contests(data if isinstance(data, dict) else [])
        except Exception:
            return sample_signals("hackathons")


class OpenAlexCollector(HTTPCollector):
    def __init__(self, query: str = "agentic ai") -> None:
        super().__init__(name="OpenAlex", category="research")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://api.openalex.org/works", search=self.query, per_page=8, sort="cited_by_count:desc")
            return parse_openalex_works(data if isinstance(data, dict) else [])
        except Exception:
            return sample_signals("research")


class WikipediaPageviewsCollector(HTTPCollector):
    def __init__(self, article: str = "Large_language_model") -> None:
        super().__init__(name="Wikipedia Pageviews", category="research")
        self.article = article

    def collect(self) -> list[SignalRecord]:
        end = datetime.now(UTC) - timedelta(days=1)
        start = end - timedelta(days=6)
        try:
            data = self.get_json(
                f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{self.article}/daily/{start:%Y%m%d}/{end:%Y%m%d}"
            )
            return parse_wikipedia_pageviews(data if isinstance(data, dict) else [])
        except Exception:
            return sample_signals("research")


class CoinGeckoCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="CoinGecko", category="finance")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://api.coingecko.com/api/v3/search/trending")
            return parse_coingecko_trending(data if isinstance(data, dict) else [])
        except Exception:
            return sample_signals("finance")


class ITunesCollector(HTTPCollector):
    def __init__(self, term: str = "AI assistant") -> None:
        super().__init__(name="iTunes App Store", category="app_stores")
        self.term = term

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://itunes.apple.com/search", term=self.term, entity="software", limit=8)
            return parse_itunes_results(data if isinstance(data, dict) else [])
        except Exception:
            return sample_signals("app_stores")


class SteamCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="Steam", category="app_stores")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://store.steampowered.com/api/featuredcategories")
            return parse_steam_featured(data if isinstance(data, dict) else [])
        except Exception:
            return sample_signals("app_stores")


class DuckDuckGoCollector(HTTPCollector):
    def __init__(self, query: str = "browser agents startup pain") -> None:
        super().__init__(name="DuckDuckGo", category="search")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            text = self.get_text("https://duckduckgo.com/html/", q=self.query)
            records = parse_duckduckgo_results(text)
            return records or sample_signals("search")
        except Exception:
            return sample_signals("search")


class GoogleTrendsCollector(HTTPCollector):
    def __init__(self, geo: str = "US") -> None:
        super().__init__(name="Google Trends", category="search")
        self.geo = geo

    def collect(self) -> list[SignalRecord]:
        try:
            text = self.get_text("https://trends.google.com/trending/rss", geo=self.geo)
            records = parse_google_trends_rss(text)
            return records or google_trends_fallback()
        except Exception:
            return google_trends_fallback()


class YCCompaniesCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="YC Companies", category="finance")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://www.ycombinator.com/companies.json")
            return parse_yc_companies(data if isinstance(data, (dict, list)) else [])
        except Exception:
            return sample_signals("finance")


class SECEdgarCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="SEC EDGAR", category="finance")

    def collect(self) -> list[SignalRecord]:
        records: list[SignalRecord] = []
        for cik in ["0001045810", "0000789019"]:
            try:
                data = self.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
                records.extend(parse_sec_submissions(data if isinstance(data, dict) else {}))
            except Exception:
                records.extend(sample_signals("finance")[:1])
        return records


class PapersWithCodeCollector(HTTPCollector):
    def __init__(self, query: str = "agentic ai") -> None:
        super().__init__(name="Papers With Code", category="research")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://paperswithcode.com/api/v1/papers/", q=self.query)
            return parse_paperswithcode_results(data if isinstance(data, dict) else [])
        except Exception:
            return sample_signals("research")


class SpecialIntelligenceCollector:
    name = "Special Intelligence"
    category = "mixed"

    def collect(self) -> list[SignalRecord]:
        return build_special_signals()


def default_collectors(use_live_network: bool = True) -> list[object]:
    if not use_live_network:
        return [SampleCollector()]
    return [
        GitHubSearchCollector(),
        HackerNewsCollector(),
        RedditJSONCollector(),
        DevToCollector(),
        LobstersCollector(),
        RemoteOKCollector(),
        TheMuseCollector(),
        ArbeitnowCollector(),
        CodeforcesCollector(),
        ArxivCollector(),
        OpenAlexCollector(),
        WikipediaPageviewsCollector(),
        CoinGeckoCollector(),
        ITunesCollector(),
        SteamCollector(),
        DuckDuckGoCollector(),
        GoogleTrendsCollector(),
        YCCompaniesCollector(),
        SECEdgarCollector(),
        PapersWithCodeCollector(),
        PackageCollector(),
        SpecialIntelligenceCollector(),
    ]


class SampleCollector:
    name = "Sample Radar"
    category = "mixed"

    def collect(self) -> list[SignalRecord]:
        records: list[SignalRecord] = []
        for category in ["code", "social", "news", "jobs", "hackathons", "research", "finance", "app_stores"]:
            records.extend(sample_signals(category))
        records.extend(build_special_signals())
        return records


def google_trends_fallback() -> list[SignalRecord]:
    return [
        SignalRecord(
            id="sample:search:google-trends",
            topic="browser agents",
            title="browser agents is rising on Google Trends",
            source="Google Trends",
            category="search",
            url="https://trends.google.com/trends/explore?q=browser%20agents",
            score=68,
            velocity=50_000,
            metadata={"approx_traffic": 50_000},
        )
    ]


def sample_signals(category: str) -> list[SignalRecord]:
    now = datetime.now(UTC)
    samples = {
        "code": [
            ("browser agents", "Browser automation agents gain repository momentum", "GitHub Search", 88, "https://github.com/search?q=browser+agents"),
            ("mcp", "MCP servers directory keeps expanding", "GitHub Search", 82, "https://github.com/modelcontextprotocol/servers"),
        ],
        "social": [
            ("local llm", "Developers discuss local LLM workflows", "Hacker News", 76, "https://news.ycombinator.com"),
            ("browser agents", "Reddit asks how to run browser agents locally", "Reddit JSON", 71, "https://reddit.com"),
        ],
        "news": [
            ("streamlit", "Python dashboards remain fast path for internal AI tools", "Dev.to", 68, "https://dev.to"),
        ],
        "jobs": [
            ("ai intern", "AI intern role mentions agents and automation", "RemoteOK", 79, "https://remoteok.com"),
        ],
        "hackathons": [
            ("algorithm contest", "Upcoming Codeforces contest window is open", "Codeforces", 70, "https://codeforces.com/contests"),
        ],
        "research": [
            ("agentic browser automation", "Agentic browser automation papers increase", "arXiv", 77, "https://arxiv.org"),
        ],
        "finance": [
            ("ai infrastructure", "Funding pulse favors AI infrastructure tooling", "YC Companies", 73, "https://www.ycombinator.com/companies"),
        ],
        "search": [
            ("browser agents", "Search results show browser agents startup pain", "DuckDuckGo", 67, "https://duckduckgo.com"),
        ],
        "app_stores": [
            ("ai assistant pain", "Users complain about expensive AI assistant subscriptions", "iTunes App Store", 66, "https://itunes.apple.com"),
        ],
    }
    return [
        SignalRecord(
            id=f"sample:{category}:{index}",
            topic=topic,
            title=title,
            source=source,
            category=category,  # type: ignore[arg-type]
            url=url,
            score=score,
            velocity=max(score - 50, 1),
            observed_at=now,
        )
        for index, (topic, title, source, score, url) in enumerate(samples.get(category, []))
    ]
