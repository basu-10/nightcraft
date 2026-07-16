"""Web search capability wrapper (DuckDuckGo HTML + optional ArXiv/News)."""

from __future__ import annotations

import time

import requests
from bs4 import BeautifulSoup

from .rate_limit import RateLimiter

_search_limiter = RateLimiter(max_calls=20, window_seconds=60)


def _duckduckgo(query, max_results=5):
    results = []
    try:
        url = "https://html.duckduckgo.com/html/"
        resp = requests.post(url, data={"q": query}, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for row in soup.select(".result__a")[:max_results]:
            href = row.get("href")
            title = row.get_text(strip=True)
            if href and title:
                results.append({"title": title, "url": href, "snippet": ""})
        snippets = soup.select(".result__snippet")
        for i, snip in enumerate(snippets[: len(results)]):
            results[i]["snippet"] = snip.get_text(strip=True)
    except Exception:
        pass
    return results


def web_search(query, max_results=5):
    _search_limiter.acquire()
    return _duckduckgo(query, max_results=max_results)


def visit_url(url, max_chars=8000):
    """Fetch a page, return cleaned text. Returns empty string on failure."""
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[:max_chars]
    except Exception:
        return ""
