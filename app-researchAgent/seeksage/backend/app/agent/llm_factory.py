from __future__ import annotations

import os

from langchain_openai import ChatOpenAI

from ..models import ConnectionProfile, Workspace


def _openrouter_llm(api_key: str, model: str, temperature: float = 0.4) -> ChatOpenAI:
    return ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key or "not-needed",
        model=model,
        temperature=temperature,
        default_headers={"HTTP-Referer": "http://localhost", "X-Title": "SeekSage Web"},
    )


def _local_llm(api_base: str, model: str, temperature: float = 0.4) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=api_base,
        api_key="not-needed",
        model=model,
        temperature=temperature,
    )


def _resolve_profile(user_id: str, workspace_id: str) -> ConnectionProfile | None:
    workspace = Workspace.query.filter_by(id=workspace_id, user_id=user_id).first()
    if workspace and workspace.profile_id:
        profile = ConnectionProfile.query.filter_by(
            id=workspace.profile_id,
            user_id=user_id,
        ).first()
        if profile:
            return profile

    return ConnectionProfile.query.filter_by(user_id=user_id, is_active=True).first()


def _build_llm_from_role_cfg(cfg: dict, shared_or_key: str = "") -> ChatOpenAI | None:
    provider = cfg.get("provider", "lm_studio")
    model = (cfg.get("model") or "").strip()
    if not model:
        return None
    if provider == "openrouter":
        api_key = (cfg.get("api_key") or shared_or_key or "").strip()
        return _openrouter_llm(api_key, model)

    default_base = "http://localhost:11434/v1" if provider == "ollama" else "http://localhost:1234/v1"
    api_base = (cfg.get("api_base") or default_base).strip()
    return _local_llm(api_base, model)


def build_agent_llms(user_id: str, workspace_id: str) -> list[tuple[ChatOpenAI, str]]:
    profile = _resolve_profile(user_id, workspace_id)
    entries: list[tuple[ChatOpenAI, str]] = []

    if profile and profile.provider == "advanced":
        settings = profile.settings or {}
        shared_key = settings.get("or_api_key", "")
        seen: set[str] = set()
        for role in ("agent", "agent_fallback"):
            cfg = settings.get(role) or {}
            llm = _build_llm_from_role_cfg(cfg, shared_key)
            if llm:
                name = cfg.get("model", role)
                if name not in seen:
                    entries.append((llm, name))
                    seen.add(name)
        if entries:
            return entries

    if profile and profile.provider == "openrouter":
        settings = profile.settings or {}
        api_key = settings.get("api_key") or os.getenv("OPENROUTER_API_KEY", "")
        primary = (settings.get("agent_model") or "openai/gpt-4o-mini").strip()
        fallback = (settings.get("agent_model_fallback") or "").strip()
        entries.append((_openrouter_llm(api_key, primary), primary))
        if fallback and fallback != primary:
            entries.append((_openrouter_llm(api_key, fallback), fallback))
        return entries

    if profile and profile.provider in ("lm_studio", "ollama"):
        settings = profile.settings or {}
        api_base = (
            settings.get("api_base")
            or ("http://localhost:11434/v1" if profile.provider == "ollama" else "http://localhost:1234/v1")
        )
        primary = (
            settings.get("model")
            or ("llama3.2" if profile.provider == "ollama" else "gpt-4o-mini")
        )
        fallback = (settings.get("model_fallback") or "").strip()
        entries.append((_local_llm(api_base, primary), primary))
        if fallback and fallback != primary:
            entries.append((_local_llm(api_base, fallback), fallback))
        return entries

    default_base = os.getenv("LM_STUDIO_API_BASE", "http://localhost:1234/v1")
    default_model = os.getenv("LM_STUDIO_MODEL", "gpt-4o-mini")
    return [(_local_llm(default_base, default_model), default_model)]


def build_code_llms(user_id: str, workspace_id: str) -> list[tuple[ChatOpenAI, str]]:
    """Build LLM chain for code generation: code → code_fallback → agent chain."""
    profile = _resolve_profile(user_id, workspace_id)
    entries: list[tuple[ChatOpenAI, str]] = []

    if profile and profile.provider == "advanced":
        settings = profile.settings or {}
        shared_key = settings.get("or_api_key", "")
        seen: set[str] = set()
        for role in ("code", "code_fallback"):
            cfg = settings.get(role) or {}
            llm = _build_llm_from_role_cfg(cfg, shared_key)
            if llm:
                name = cfg.get("model", role)
                if name not in seen:
                    entries.append((llm, name))
                    seen.add(name)
        if entries:
            # Append agent chain as additional fallback
            for llm, name in build_agent_llms(user_id, workspace_id):
                if name not in seen:
                    entries.append((llm, name))
                    seen.add(name)
            return entries

    # Fall back to the agent chain for non-advanced providers
    return build_agent_llms(user_id, workspace_id)


def build_summary_llms(user_id: str, workspace_id: str) -> list[tuple[ChatOpenAI, str]]:
    """Build LLM chain for summarisation/slide structuring: summarization → fallback → code → agent."""
    profile = _resolve_profile(user_id, workspace_id)
    entries: list[tuple[ChatOpenAI, str]] = []

    if profile and profile.provider == "advanced":
        settings = profile.settings or {}
        shared_key = settings.get("or_api_key", "")
        seen: set[str] = set()
        for role in ("summarization", "summarization_fallback"):
            cfg = settings.get(role) or {}
            llm = _build_llm_from_role_cfg(cfg, shared_key)
            if llm:
                name = cfg.get("model", role)
                if name not in seen:
                    entries.append((llm, name))
                    seen.add(name)
        # Append code chain then agent chain as additional fallbacks
        for llm, name in build_code_llms(user_id, workspace_id):
            if name not in seen:
                entries.append((llm, name))
                seen.add(name)
        if entries:
            return entries

    return build_agent_llms(user_id, workspace_id)


def invoke_with_fallbacks(
    llm_chain: list[tuple[ChatOpenAI, str]],
    messages: list,
) -> tuple:
    """
    Try each (llm, name) in llm_chain until one succeeds.
    Returns (response, model_name).  Raises the last error if all fail.
    """
    last_exc: Exception | None = None
    for llm, name in llm_chain:
        try:
            response = llm.invoke(messages)
            return response, name
        except Exception as exc:
            last_exc = exc
            continue
    if last_exc:
        raise last_exc
    raise RuntimeError("invoke_with_fallbacks: empty llm_chain")

