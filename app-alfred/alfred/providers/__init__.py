"""Capability wrappers over external services. No business logic here."""

from __future__ import annotations

import json
import os

from ..settings_keys import (
    DEFAULT_AGENT_MODEL,
    DEFAULT_EMBEDDING_MODEL,
    resolve_agent_model,
    resolve_embedding_model,
)


def _api_key():
    from ..services.settings import get_setting

    key = get_setting("alfred_openrouter_api_key", "")
    if key:
        return key
    return os.getenv("OPENROUTER_API_KEY", "")


def _openai_client():
    from openai import OpenAI

    return OpenAI(
        base_url=os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1"),
        api_key=_api_key() or "missing",
    )


def resolve_provider_ok():
    """Best-effort check that an LLM client can be constructed (P4 #11)."""
    try:
        _openai_client()
        return True
    except Exception:  # noqa: BLE001
        return False


class LLMProvider:
    """OpenRouter chat completions (OpenAI-compatible)."""

    @staticmethod
    def chat(messages, model=None, temperature=0.2, max_tokens=2000, response_format=None):
        model = model or resolve_agent_model() or DEFAULT_AGENT_MODEL
        client = _openai_client()
        kwargs = dict(model=model, messages=messages, temperature=temperature, max_tokens=max_tokens)
        if response_format:
            kwargs["response_format"] = response_format
        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content

    @staticmethod
    def chat_json(messages, model=None, temperature=0.2, max_tokens=2000):
        """Request a JSON object; parse defensively."""
        content = LLMProvider.chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return LLMProvider._extract_json(content)

    @staticmethod
    def _extract_json(content):
        if content is None:
            return {}
        content = content.strip()
        try:
            return json.loads(content)
        except (ValueError, TypeError):
            pass
        # Strip markdown fences if present.
        if content.startswith("```"):
            content = content.split("\n", 1)[-1] if "\n" in content else content
            if content.endswith("```"):
                content = content[: -3]
            content = content.strip()
            try:
                return json.loads(content)
            except (ValueError, TypeError):
                return {}
        return {}


class EmbeddingProvider:
    """OpenRouter embeddings (OpenAI-compatible)."""

    @staticmethod
    def embed(text, model=None):
        model = model or resolve_embedding_model() or DEFAULT_EMBEDDING_MODEL
        client = _openai_client()
        resp = client.embeddings.create(model=model, input=text)
        return resp.data[0].embedding

    @staticmethod
    def embed_batch(texts, model=None):
        if not texts:
            return []
        model = model or resolve_embedding_model() or DEFAULT_EMBEDDING_MODEL
        client = _openai_client()
        resp = client.embeddings.create(model=model, input=texts)
        return [item.embedding for item in resp.data]
