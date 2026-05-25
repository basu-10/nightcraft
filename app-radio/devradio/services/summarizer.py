from __future__ import annotations

import json

import requests

OPENROUTER_CHAT_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
SUMMARY_MODEL = "openai/gpt-4o-mini"


def generate_editorial_bundle(article_title, article_excerpt, source_url, api_key):
    fallback = {
        "short_headline": article_title[:120],
        "bullet_summary": "- Key update from source\n- Why this matters for builders\n- What to watch next",
        "narration_script": (
            f"Headline: {article_title}. Here is what happened and why this matters. "
            "Check the summary panel for more detail."
        ),
        "tags": "tech,news",
        "internal_content": article_excerpt or "Summary pending editorial updates.",
    }

    if not api_key:
        return fallback

    prompt = (
        "Create JSON with keys short_headline, bullet_summary, narration_script, tags, internal_content. "
        "Do not reproduce article verbatim. Keep bullet_summary as markdown bullets. "
        f"Title: {article_title}\nExcerpt: {article_excerpt}\nSource: {source_url}"
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": SUMMARY_MODEL,
        "messages": [
            {"role": "system", "content": "You are an editorial assistant for concise tech radio."},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
    }

    try:
        response = requests.post(OPENROUTER_CHAT_ENDPOINT, headers=headers, json=payload, timeout=40)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return {
            "short_headline": parsed.get("short_headline", fallback["short_headline"]),
            "bullet_summary": parsed.get("bullet_summary", fallback["bullet_summary"]),
            "narration_script": parsed.get("narration_script", fallback["narration_script"]),
            "tags": parsed.get("tags", fallback["tags"]),
            "internal_content": parsed.get("internal_content", fallback["internal_content"]),
        }
    except Exception:
        return fallback
