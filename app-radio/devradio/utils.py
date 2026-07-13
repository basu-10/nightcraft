import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Comment
from flask import current_app, has_app_context
from markupsafe import escape
from zoneinfo import ZoneInfo


DEFAULT_APP_TIMEZONE = "Asia/Kolkata"

_ARTICLE_ALLOWED_TAGS = {
    "a",
    "b",
    "blockquote",
    "br",
    "caption",
    "code",
    "em",
    "figcaption",
    "figure",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
}

_ARTICLE_ALLOWED_ATTRS = {
    "a": {"href", "title", "target", "rel"},
    "img": {"src", "alt", "title", "loading", "referrerpolicy", "width", "height"},
    "th": {"colspan", "rowspan", "scope"},
    "td": {"colspan", "rowspan", "scope"},
}

_ARTICLE_REMOVE_TAGS = {
    "script",
    "style",
    "noscript",
    "iframe",
    "object",
    "embed",
    "form",
    "svg",
    "canvas",
    "video",
    "audio",
    "button",
    "input",
    "textarea",
}


class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []

    def handle_data(self, data):
        self._parts.append(data)

    def get_text(self):
        return " ".join(self._parts)


def strip_html(raw: str) -> str:
    """Strip HTML tags, decode entities, and remove common RSS footers."""
    if not raw:
        return ""
    stripper = _HTMLStripper()
    stripper.feed(raw)
    text = stripper.get_text()
    # Remove RSS "The post … appeared first on …" footer
    text = re.sub(r"The post\s+.+?appeared first on\s+.+?\.", "", text, flags=re.DOTALL)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_safe_link(href: str) -> bool:
    if not href:
        return False
    parsed = urlparse(href)
    if not parsed.scheme:
        return href.startswith("/") or href.startswith("#")
    return parsed.scheme.lower() in {"http", "https", "mailto"}


def _is_safe_image_src(src: str) -> bool:
    """Only absolute http(s) image URLs are safe; relative/anchor/data URIs are rejected."""
    if not src:
        return False
    if src.startswith("data:") or src.startswith("#") or src.startswith("javascript:"):
        return False
    parsed = urlparse(src)
    if not parsed.scheme:
        return False
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


def sanitize_article_html(raw_html: str) -> str:
    if not raw_html:
        return ""

    soup = BeautifulSoup(raw_html, "html.parser")

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    for tag in soup.find_all(True):
        tag_name = (tag.name or "").lower()
        if tag_name in _ARTICLE_REMOVE_TAGS:
            tag.decompose()
            continue

        if tag_name not in _ARTICLE_ALLOWED_TAGS:
            tag.unwrap()
            continue

        allowed_attrs = _ARTICLE_ALLOWED_ATTRS.get(tag_name, set())
        for attr_name in list(tag.attrs.keys()):
            if attr_name not in allowed_attrs:
                del tag.attrs[attr_name]

        if tag_name == "a":
            href = (tag.get("href") or "").strip()
            if not _is_safe_link(href):
                for attr_name in ["href", "target", "rel", "title"]:
                    if attr_name in tag.attrs:
                        del tag.attrs[attr_name]
            else:
                if tag.get("target") == "_blank":
                    tag["rel"] = "noopener noreferrer"
                elif "target" in tag.attrs:
                    del tag.attrs["target"]
                    if "rel" in tag.attrs:
                        del tag.attrs["rel"]

        if tag_name == "img":
            src = (tag.get("src") or "").strip()
            if not _is_safe_image_src(src):
                tag.decompose()
                continue
            tag["referrerpolicy"] = "no-referrer"
            tag["loading"] = "lazy"

    for table_cell in soup.find_all(["th", "td"]):
        for span_attr in ["colspan", "rowspan"]:
            value = table_cell.get(span_attr)
            if value and not str(value).isdigit():
                del table_cell.attrs[span_attr]

    cleaned = str(soup).strip()
    return cleaned


def format_article_body_html(source_full_article: str, raw_excerpt: str, summary: str, fallback: str = "") -> str:
    candidate = (source_full_article or "").strip() or (raw_excerpt or "").strip() or (summary or "").strip()
    if not candidate:
        return f"<p>{escape(fallback or 'No article text available.')}</p>"

    # Preserve source structure when HTML is present, otherwise render readable paragraphs.
    if "<" in candidate and ">" in candidate:
        cleaned = sanitize_article_html(candidate)
        if cleaned:
            return cleaned

    plain_text = candidate if ("<" not in candidate and ">" not in candidate) else strip_html(candidate)
    normalized = plain_text.replace("\r\n", "\n").strip()
    if not normalized:
        return f"<p>{escape(fallback or 'No article text available.')}</p>"

    paragraphs = [chunk.strip() for chunk in re.split(r"\n\s*\n", normalized) if chunk.strip()]
    if not paragraphs:
        paragraphs = [normalized]

    rendered = []
    for paragraph in paragraphs:
        rendered.append(f"<p>{escape(paragraph).replace(chr(10), '<br>')}</p>")
    return "\n".join(rendered)


def now_utc():
    return datetime.now(timezone.utc)


def app_timezone_name():
    if has_app_context():
        return current_app.config.get("DEFAULT_TIMEZONE", DEFAULT_APP_TIMEZONE)
    return DEFAULT_APP_TIMEZONE


def safe_zoneinfo(tz_name):
    try:
        return ZoneInfo(tz_name)
    except Exception:
        # Use stdlib UTC tzinfo so we do not depend on external tzdata presence.
        return timezone.utc


def app_timezone():
    return safe_zoneinfo(app_timezone_name())


def now_app_timezone():
    return now_utc().astimezone(app_timezone())


def parse_datetime(value, assume_tz=timezone.utc):
    if value is None:
        return None
    if isinstance(value, datetime):
        dt_value = value
    elif isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            dt_value = datetime.fromisoformat(candidate)
        except ValueError:
            return None
    else:
        return None

    if dt_value.tzinfo is None:
        dt_value = dt_value.replace(tzinfo=assume_tz)
    return dt_value


def to_app_timezone(value):
    dt_value = parse_datetime(value)
    if dt_value is None:
        return None
    return dt_value.astimezone(app_timezone())


def format_in_app_timezone(value, fmt="%Y-%m-%d %H:%M:%S %Z"):
    localized = to_app_timezone(value)
    if localized is None:
        return ""
    return localized.strftime(fmt)


def to_user_timezone(dt_utc, tz_name):
    if dt_utc is None:
        return None
    return dt_utc.astimezone(safe_zoneinfo(tz_name))


def compute_loop_segment(segments, epoch_seconds=None, default_duration=90):
    if not segments:
        return None, 0, 0

    durations = [max(1, int(seg.duration_seconds or default_duration)) for seg in segments]
    total_duration = sum(durations)
    if total_duration <= 0:
        return segments[0], 0, 0

    now_epoch = int(epoch_seconds if epoch_seconds is not None else now_utc().timestamp())
    cursor = now_epoch % total_duration
    for segment, duration in zip(segments, durations):
        if cursor < duration:
            return segment, cursor, total_duration
        cursor -= duration

    return segments[-1], 0, total_duration
