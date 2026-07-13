from __future__ import annotations

import random
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup


@dataclass
class FetchResult:
    text: str | None
    status: str
    image_url: str | None = None


class SourceArticleFetcher:
    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float = 12.0,
        min_chars: int = 800,
        max_chars: int = 30000,
        min_delay_seconds: float = 2.0,
        jitter_seconds: float = 1.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 2.0,
        respect_robots: bool = True,
        extract_images: bool = True,
    ):
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.min_delay_seconds = min_delay_seconds
        self.jitter_seconds = jitter_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.respect_robots = respect_robots
        self.extract_images = extract_images

        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.8",
            }
        )
        self._last_request_by_host: dict[str, float] = {}
        self._robots_cache: dict[str, RobotFileParser] = {}

    def fetch(self, source_url: str) -> FetchResult:
        parsed = urlparse(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return FetchResult(text=None, status="invalid_url")

        host = parsed.netloc.lower()
        if self.respect_robots and not self._is_allowed_by_robots(parsed):
            return FetchResult(text=None, status="robots_disallowed")

        self._respect_pacing(host)

        for attempt in range(1, self.max_retries + 2):
            try:
                response = self._session.get(source_url, timeout=self.timeout_seconds)
                status_code = response.status_code
                if status_code in {429, 500, 502, 503, 504} and attempt <= self.max_retries + 1:
                    self._sleep_backoff(attempt)
                    continue

                response.raise_for_status()
                content_type = (response.headers.get("Content-Type") or "").lower()
                if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                    return FetchResult(text=None, status="non_html")

                # Parse the document exactly once and reuse the tree for both
                # image detection and main-content extraction. Re-parsing the
                # full page a second time was needlessly expensive per fetch.
                soup = BeautifulSoup(response.text, "html.parser")
                image_url = None
                if self.extract_images:
                    image_url = self._extract_lead_image(soup, source_url)

                article_html, article_text = self._extract_main_html(soup, source_url)
                if len(article_text) < self.min_chars:
                    return FetchResult(text=None, status="too_short", image_url=image_url)
                if len(article_html) > self.max_chars * 3:
                    return FetchResult(text=None, status="too_long", image_url=image_url)
                return FetchResult(text=article_html, status="ok", image_url=image_url)
            except requests.RequestException:
                if attempt > self.max_retries:
                    return FetchResult(text=None, status="request_error")
                self._sleep_backoff(attempt)

        return FetchResult(text=None, status="request_error")

    def _respect_pacing(self, host: str) -> None:
        now = time.monotonic()
        last_request = self._last_request_by_host.get(host)
        if last_request is not None:
            wait_seconds = self.min_delay_seconds - (now - last_request)
            if wait_seconds > 0:
                time.sleep(wait_seconds)

        if self.jitter_seconds > 0:
            time.sleep(random.uniform(0, self.jitter_seconds))

        self._last_request_by_host[host] = time.monotonic()

    def _sleep_backoff(self, attempt: int) -> None:
        base = max(0.0, self.retry_backoff_seconds)
        jitter = random.uniform(0, 0.8)
        time.sleep(base * attempt + jitter)

    def _is_allowed_by_robots(self, parsed_url) -> bool:
        host = parsed_url.netloc.lower()
        robots = self._robots_cache.get(host)
        if robots is None:
            robots_url = f"{parsed_url.scheme}://{host}/robots.txt"
            robots = RobotFileParser()
            robots.set_url(robots_url)
            try:
                # IMPORTANT: RobotFileParser.read() performs a blocking network
                # fetch with no timeout. A flaky/slow robots.txt would hang this
                # thread forever, leaking a DB connection and the process lock,
                # eventually freezing the whole server. Always fetch with a
                # bounded timeout via the session and parse the text ourselves.
                robots_timeout = min(8.0, max(3.0, self.timeout_seconds))
                resp = self._session.get(robots_url, timeout=robots_timeout)
                robots.parse(resp.text.splitlines())
            except Exception:
                # If robots cannot be read, fail open to avoid false negatives.
                self._robots_cache[host] = robots
                return True
            self._robots_cache[host] = robots

        try:
            return robots.can_fetch(self.user_agent, parsed_url.geturl())
        except Exception:
            return True

    # Class/id substrings that strongly suggest boilerplate regions.
    _BOILERPLATE_HINTS = frozenset([
        "nav", "menu", "sidebar", "footer", "header", "breadcrumb",
        "related", "share", "social", "cookie", "promo", "banner",
        "ad", "advertisement", "comment", "widget", "newsletter",
        "subscribe", "popup", "modal", "overlay", "masthead",
    ])

    def _extract_main_html(self, soup: BeautifulSoup, base_url: str | None = None) -> tuple[str, str]:

        # Strip universally useless tags.
        for bad in soup(["script", "style", "noscript", "svg", "iframe",
                         "form", "button", "input", "select", "textarea",
                         "picture", "figure"]):
            bad.unwrap()

        # Strip structural boilerplate by tag.
        for bad in soup(["nav", "header", "footer", "aside"]):
            bad.decompose()

        # Strip elements whose role marks them as non-content.
        for el in soup.find_all(
            attrs={"role": ["navigation", "banner", "contentinfo",
                            "complementary", "search", "form"]}
        ):
            el.decompose()

        # Strip elements whose class/id strongly hints at boilerplate.
        for el in soup.find_all(True):
            if el.attrs is None:
                continue
            tokens = " ".join(
                (el.get("class") or []) + [el.get("id") or ""]
            ).lower()
            if any(hint in tokens for hint in self._BOILERPLATE_HINTS):
                el.decompose()

        # Priority: <article> > <main> > biggest-text-density block.
        candidate = soup.find("article") or soup.find("main")
        if candidate is None:
            best_node = None
            best_len = 0
            for tag in soup.find_all(["section", "div"]):
                text_len = len(tag.get_text(" ", strip=True))
                if text_len > best_len:
                    best_len = text_len
                    best_node = tag
            candidate = best_node or soup.body

        if candidate is None:
            return "", ""

        # Absolutize image URLs against the article URL so hotlinked body
        # images resolve to the origin host rather than our own.
        if base_url:
            for img in candidate.find_all("img"):
                for attr in ("src", "data-src", "data-lazy-src"):
                    raw = img.get(attr)
                    if not raw:
                        continue
                    absolute = self._normalize_image_url(raw, base_url)
                    if absolute:
                        img[attr] = absolute
                srcset = img.get("srcset")
                if srcset:
                    rewritten = []
                    for part in srcset.split(","):
                        part = part.strip()
                        if not part:
                            continue
                        tokens = part.split()
                        candidate_url = tokens[0]
                        absolute = self._normalize_image_url(candidate_url, base_url)
                        if absolute:
                            tokens[0] = absolute
                        rewritten.append(" ".join(tokens))
                    img["srcset"] = ", ".join(rewritten)

        article_text = " ".join(candidate.get_text(" ", strip=True).split())
        article_html = str(candidate)
        return article_html, article_text

    _IMAGE_META_PROPERTIES = (
        "og:image",
        "og:image:url",
        "og:image:secure_url",
        "twitter:image",
        "twitter:image:src",
        "image",
    )

    _IMAGE_EXTENSIONS = frozenset([
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp", ".svg",
    ])

    def _normalize_image_url(self, raw_url: str | None, base_url: str) -> str | None:
        if not raw_url:
            return None
        candidate = raw_url.strip()
        if not candidate:
            return None
        # Resolve relative paths against the article URL.
        try:
            absolute = urljoin(base_url, candidate)
        except ValueError:
            return None
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        return absolute

    def _extract_lead_image(self, soup: BeautifulSoup, base_url: str) -> str | None:

        # 1) Open Graph / Twitter / schema image metadata (most reliable).
        for prop in self._IMAGE_META_PROPERTIES:
            tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
            if tag and tag.get("content"):
                normalized = self._normalize_image_url(tag["content"], base_url)
                if normalized:
                    return normalized

        # 2) First meaningful <img> inside the main article content.
        candidate = soup.find("article") or soup.find("main") or soup.body
        if candidate is not None:
            for img in candidate.find_all("img"):
                src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
                if not src:
                    continue
                normalized = self._normalize_image_url(src, base_url)
                if not normalized:
                    continue
                path = urlparse(normalized).path.lower()
                if any(path.endswith(ext) for ext in self._IMAGE_EXTENSIONS):
                    return normalized
                # Accept CDN-style URLs that lack a clean extension but look media-like.
                if any(token in path for token in ("/image", "/img", "/photo", "/media", "/wp-content/uploads", "/assets")):
                    return normalized

        return None
