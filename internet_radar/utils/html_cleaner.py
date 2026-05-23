from __future__ import annotations

import html
import re
from urllib.parse import urljoin


NOISE_TAGS = {"script", "style", "noscript", "svg", "canvas", "nav", "footer"}


def clean_html(raw_html: str) -> str:
    text = raw_html
    for tag in NOISE_TAGS:
        text = re.sub(rf"<{tag}\b[^>]*>.*?</{tag}>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("\xa0", " ")
    return " ".join(text.split())


def extract_links(raw_html: str, base_url: str = "") -> list[str]:
    links: list[str] = []
    for match in re.finditer(r"<a\b[^>]*\bhref=[\"']([^\"']+)[\"']", raw_html, flags=re.I):
        href = html.unescape(match.group(1)).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        resolved = urljoin(base_url, href) if base_url else href
        if resolved not in links:
            links.append(resolved)
    return links
