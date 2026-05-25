"""
Source citation extraction — ported from chotu_PySide6/app/agent/worker.py.

Provides `append_deterministic_sources(answer, messages)` that injects
inline citation markers and a Sources footer into the final answer.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


_URL_RE = re.compile(r"https?://[^\s)\]>\"']+", re.IGNORECASE)
_SOURCES_HEADING_RE = re.compile(
    r"\n{1,3}(?:#{1,6}\s*)?(?:sources?|citations?|references?)\s*:?.*\Z",
    re.IGNORECASE | re.DOTALL,
)
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_\-/]{1,}", re.IGNORECASE)
_SENTENCE_RE = re.compile(r"[^.!?\n]+(?:[.!?](?:[\"')\]]+)?)?", re.MULTILINE)
_INLINE_CITE_RE = re.compile(r"\[(\d+)\]\((https?://[^)\s]+)\)", re.IGNORECASE)
_MD_TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$"
)
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "have", "has", "had", "into", "your", "their", "about", "after", "before",
    "over", "under", "there", "here", "what", "when", "where", "which", "while",
    "than", "then", "them", "they", "will", "would", "could", "should", "also",
    "only", "just", "onto", "each", "such", "using", "used", "use",
    "source", "sources", "result", "results", "query", "page", "visited",
}


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _canonicalize_url(url: str) -> str:
    cleaned = (url or "").strip().rstrip(".,;)]}")
    if not cleaned:
        return ""
    try:
        parsed = urlparse(cleaned)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return cleaned
        norm = parsed._replace(fragment="")
        return urlunparse(norm).rstrip("/")
    except Exception:
        return cleaned


def _extract_url_candidates(text: str) -> list[str]:
    if not text:
        return []
    return [_canonicalize_url(m.group(0)) for m in _URL_RE.finditer(text)]


def _is_valid_source_url(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Tool message extraction
# ---------------------------------------------------------------------------

def _extract_turn_tool_messages(messages: list[Any]) -> list[ToolMessage]:
    last_human_idx = max(
        (i for i, msg in enumerate(messages) if isinstance(msg, HumanMessage)),
        default=-1,
    )
    current_turn = messages[last_human_idx:] if last_human_idx >= 0 else messages
    return [msg for msg in current_turn if isinstance(msg, ToolMessage)]


def _extract_source_rows_from_tool_content(content: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not content:
        return rows

    lines = [ln.rstrip() for ln in content.splitlines()]
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = re.match(r"^(\d+)\.\s+(.+)$", line)
        if not m:
            i += 1
            continue
        title = m.group(2).strip()
        url = ""
        snippet_parts: list[str] = []
        j = i + 1
        while j < len(lines):
            probe = lines[j].strip()
            if re.match(r"^\d+\.\s+", probe):
                break
            lower_probe = probe.lower()
            if lower_probe.startswith(("link:", "url:")):
                maybe = probe.split(":", 1)[1].strip() if ":" in probe else ""
                if maybe:
                    url = _canonicalize_url(maybe)
            elif lower_probe.startswith(("snippet:", "abstract:", "description:", "body:")):
                text_part = probe.split(":", 1)[1].strip() if ":" in probe else ""
                if text_part:
                    snippet_parts.append(text_part)
            j += 1
        if url:
            rows.append({"title": title, "url": url, "evidence_text": " ".join(snippet_parts).strip()})
        i = j

    page_m = re.search(r"^---\s*Page:\s*(.+?)\s*---\s*$", content, re.MULTILINE)
    page_url_m = re.search(r"^URL:\s*(https?://\S+)\s*$", content, re.MULTILINE | re.IGNORECASE)
    if page_m and page_url_m:
        rows.append({
            "title": page_m.group(1).strip(),
            "url": _canonicalize_url(page_url_m.group(1).strip()),
            "evidence_text": page_m.group(1).strip(),
        })

    for vm in re.finditer(r"^\[Video:\s*(.+?)\]\s*$", content, re.MULTILINE):
        title = vm.group(1).strip()
        after = content[vm.end():]
        um = re.search(r"^URL:\s*(https?://\S+)\s*$", after, re.MULTILINE | re.IGNORECASE)
        if um:
            rows.append({"title": title, "url": _canonicalize_url(um.group(1).strip()), "evidence_text": title})

    if content.lstrip().startswith("{"):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                url = _canonicalize_url(str(parsed.get("url", "")))
                title = str(parsed.get("title", "")).strip() or "Visited page"
                evidence = str(parsed.get("description", "")).strip()
                if url:
                    rows.append({"title": title, "url": url, "evidence_text": evidence})
        except Exception:
            pass

    for wm in re.finditer(r"^Page:\s*(.+?)\s*$", content, re.MULTILINE):
        page_title = wm.group(1).strip()
        if page_title:
            wiki_url = f"https://en.wikipedia.org/wiki/{quote(page_title.replace(' ', '_'))}"
            rows.append({"title": f"Wikipedia: {page_title}", "url": _canonicalize_url(wiki_url), "evidence_text": page_title})

    seen_urls = {r["url"] for r in rows if r.get("url")}
    for url in _extract_url_candidates(content):
        if url and url not in seen_urls:
            rows.append({"title": "Source", "url": url, "evidence_text": ""})
            seen_urls.add(url)

    return [r for r in rows if r.get("url")]


# ---------------------------------------------------------------------------
# Source extraction + relevance scoring
# ---------------------------------------------------------------------------

def _tokenize_relevance_text(text: str) -> set[str]:
    if not text:
        return set()
    return {
        t.lower() for t in _WORD_RE.findall(text.lower())
        if len(t) >= 3 and t.lower() not in _STOPWORDS
    }


def _source_relevance_score(answer_text: str, source_row: dict[str, str]) -> tuple[int, bool]:
    answer_lower = answer_text.lower()
    url = source_row.get("url", "")
    title = source_row.get("title", "")
    evidence = source_row.get("evidence_text", "")

    explicit_url_match = bool(url and url.lower() in answer_lower)
    explicit_title_match = bool(title and len(title) >= 8 and title.lower() in answer_lower)

    answer_tokens = _tokenize_relevance_text(answer_text)
    source_tokens = _tokenize_relevance_text(f"{title} {evidence}")
    overlap = len(answer_tokens & source_tokens)

    score = overlap
    if explicit_title_match:
        score += 3
    if explicit_url_match:
        score += 5

    try:
        domain = urlparse(url).netloc.lower()
    except Exception:
        domain = ""
    if domain:
        core_domain = domain.replace("www.", "").split(":", 1)[0]
        domain_tokens = [p for p in re.split(r"[.\-]", core_domain) if p and p not in {"com", "org", "net", "co", "io"}]
        if any(tok in answer_lower for tok in domain_tokens):
            score += 1

    return score, explicit_url_match or explicit_title_match


def _extract_sources_from_messages(messages: list[Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue
        for tc in getattr(msg, "tool_calls", None) or []:
            name = str(tc.get("name", "")).strip()
            args = tc.get("args") or {}
            if isinstance(args, dict):
                raw_url = args.get("url")
                if isinstance(raw_url, str) and raw_url.strip():
                    url = _canonicalize_url(raw_url)
                    if url:
                        title = "Visited page" if name == "visit_url" else "Visited URL"
                        rows.append({"title": title, "url": url, "evidence_text": ""})

    for msg in _extract_turn_tool_messages(messages):
        content = str(getattr(msg, "content", "") or "")
        rows.extend(_extract_source_rows_from_tool_content(content))

    deduped_by_url: dict[str, dict[str, str]] = {}
    for row in rows:
        url = _canonicalize_url(row.get("url", ""))
        if not url:
            continue
        title = (row.get("title", "") or "Source").strip()
        evidence_text = (row.get("evidence_text", "") or "").strip()
        existing = deduped_by_url.get(url)
        if existing is None:
            deduped_by_url[url] = {"title": title, "url": url, "evidence_text": evidence_text}
        else:
            if len(evidence_text) > len(existing.get("evidence_text", "")):
                existing["evidence_text"] = evidence_text
            if existing.get("title", "").lower() in ("source", "visited url") and title:
                existing["title"] = title
    return list(deduped_by_url.values())


def _select_relevant_sources(answer_text: str, sources: list[dict[str, str]]) -> list[dict[str, str]]:
    scored = []
    for src in sources:
        score, explicit = _source_relevance_score(answer_text, src)
        scored.append((score, explicit, src))
    scored.sort(key=lambda item: (item[1], item[0]), reverse=True)
    selected = [src for score, explicit, src in scored if explicit or score >= 2]
    if not selected:
        selected = [src for score, _explicit, src in scored if score >= 1][:3]
    if not selected and len(sources) <= 2:
        selected = sources[:]
    return selected


# ---------------------------------------------------------------------------
# Source footer + inline citation injection
# ---------------------------------------------------------------------------

def _strip_trailing_sources_section(answer: str) -> str:
    if not answer:
        return ""
    return _SOURCES_HEADING_RE.sub("", answer).rstrip()


def _build_source_registry(answer: str, messages: list[Any], limit: int = 40) -> tuple[list[dict[str, Any]], int]:
    base = _strip_trailing_sources_section(answer or "")
    sources = _extract_sources_from_messages(messages)
    selected = _select_relevant_sources(base, sources)
    registry: list[dict[str, Any]] = []
    for idx, src in enumerate(selected[:limit], start=1):
        url = _canonicalize_url(str(src.get("url", "")))
        if not url:
            continue
        title = str(src.get("title", "") or "Source").strip()
        evidence_text = str(src.get("evidence_text", "") or "").strip()
        try:
            domain = urlparse(url).netloc.lower()
        except Exception:
            domain = ""
        registry.append({"id": idx, "title": title, "url": url, "evidence_text": evidence_text, "domain": domain})
    return registry, len(selected)


def _code_fence_ranges(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"```[\s\S]*?```", text)]


def _markdown_table_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    if not text:
        return ranges

    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line)

    i = 0
    while i < len(lines):
        if not _MD_TABLE_SEPARATOR_RE.match(lines[i]):
            i += 1
            continue
        if i == 0 or "|" not in lines[i - 1]:
            i += 1
            continue

        start_line = i - 1
        while start_line > 0 and "|" in lines[start_line - 1] and lines[start_line - 1].strip():
            start_line -= 1

        end_line = i
        while end_line + 1 < len(lines) and "|" in lines[end_line + 1] and lines[end_line + 1].strip():
            end_line += 1

        start_pos = offsets[start_line]
        end_pos = offsets[end_line] + len(lines[end_line])
        ranges.append((start_pos, end_pos))
        i = end_line + 1

    return ranges


def _inside_ranges(position: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in ranges)


def _citation_overlap_score(sentence_text: str, source_row: dict[str, Any]) -> int:
    sentence_tokens = _tokenize_relevance_text(sentence_text)
    source_tokens = _tokenize_relevance_text(f"{source_row.get('title', '')} {source_row.get('evidence_text', '')}")
    return len(sentence_tokens & source_tokens)


def _is_valid_citation_candidate(sentence_text: str, source_row: dict[str, Any], score: int, explicit: bool) -> bool:
    if not _is_valid_source_url(str(source_row.get("url", ""))):
        return False
    overlap = _citation_overlap_score(sentence_text, source_row)
    return explicit or (score >= 2 and overlap >= 1)


def _inject_inline_citations(answer_text: str, registry: list[dict[str, Any]], max_per_sentence: int = 2) -> str:
    if not answer_text or not registry:
        return answer_text

    protected_ranges = _code_fence_ranges(answer_text) + _markdown_table_ranges(answer_text)
    parts: list[str] = []
    cursor = 0

    for match in _SENTENCE_RE.finditer(answer_text):
        start, end = match.start(), match.end()
        sentence = match.group(0)
        parts.append(answer_text[cursor:start])
        cursor = end

        if _inside_ranges(start, protected_ranges) or _INLINE_CITE_RE.search(sentence):
            parts.append(sentence)
            continue
        if len(_tokenize_relevance_text(sentence)) < 4:
            parts.append(sentence)
            continue

        scored = []
        for src in registry:
            score, explicit = _source_relevance_score(sentence, src)
            if (score > 0 or explicit) and _is_valid_citation_candidate(sentence, src, score, explicit):
                scored.append((score, explicit, src))

        if not scored:
            parts.append(sentence)
            continue

        scored.sort(key=lambda item: (item[1], item[0]), reverse=True)
        markers: list[str] = []
        seen_ids: set[int] = set()
        for _score, _explicit, src in scored:
            src_id = int(src["id"])
            if src_id in seen_ids:
                continue
            seen_ids.add(src_id)
            markers.append(f"[{src_id}]({src['url']})")
            if len(markers) >= max_per_sentence:
                break

        parts.append(f"{sentence.rstrip()} {' '.join(markers)}" if markers else sentence)

    parts.append(answer_text[cursor:])
    return "".join(parts).strip()


def _format_sources_footer(registry: list[dict[str, Any]], total_selected: int) -> str:
    lines = ["Sources (smart-collected from tools):"]
    for src in registry:
        lines.append(f"{src['id']}. {src['title']} - {src['url']}")
    if total_selected > len(registry):
        lines.append(f"... and {total_selected - len(registry)} more source(s).")
    return "\n".join(lines)


def append_deterministic_sources(answer: str, messages: list[Any], limit: int = 40) -> str:
    """Inject validated inline citations and a Sources footer into `answer`."""
    base = _strip_trailing_sources_section(answer or "")
    registry, total_selected = _build_source_registry(base, messages, limit=limit)
    if not registry:
        return base

    try:
        inline_answer = _inject_inline_citations(base, registry)
    except Exception:
        inline_answer = base

    suffix = _format_sources_footer(registry, total_selected)
    return f"{inline_answer}\n\n{suffix}" if inline_answer else suffix
