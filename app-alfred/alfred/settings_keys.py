"""Alfred admin-configurable runtime settings (per-app, admin-only)."""

# Encrypted settings
SETTING_OPENROUTER_API_KEY = "alfred_openrouter_api_key"

# Plain settings
SETTING_EMBEDDING_MODEL = "alfred_embedding_model"
SETTING_AGENT_MODEL = "alfred_agent_model"
SETTING_REACT_MAX_STEPS = "alfred_react_max_steps"
SETTING_CHUNK_SIZE = "alfred_chunk_size"
SETTING_CHUNK_OVERLAP = "alfred_chunk_overlap"
SETTING_TOP_K = "alfred_top_k"

# Runtime policy bounds (P1 #2 / follow-up F1). Each is optional; unset => unbounded.
SETTING_MAX_RUNTIME_SECONDS = "alfred_max_runtime_seconds"
SETTING_IDLE_TIMEOUT_SECONDS = "alfred_idle_timeout_seconds"
SETTING_TOKEN_BUDGET = "alfred_token_budget"
SETTING_COST_BUDGET_USD = "alfred_cost_budget_usd"

DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small"
DEFAULT_AGENT_MODEL = "openai/gpt-4o-mini"
DEFAULT_REACT_MAX_STEPS = 12
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 200
DEFAULT_TOP_K = 6
DEFAULT_MAX_RUNTIME_SECONDS = 600
DEFAULT_IDLE_TIMEOUT_SECONDS = 120
DEFAULT_TOKEN_BUDGET = 200000
DEFAULT_COST_BUDGET_USD = 2.0

EMBEDDING_DIMENSIONS = {
    "openai/text-embedding-3-small": 1536,
    "openai/text-embedding-3-large": 3072,
    "qwen/qwen3-embedding-8b": 4096,
}


# Per-model blended cost (USD per 1M tokens) so token/cost budgets (P1 #2 / F2)
# map to real spend instead of a single flat rate. Used by the executor's
# _usage_from_response. Rates are blended (prompt+completion averaged) and
# conservative; models not listed fall back to DEFAULT_TOKEN_COST_USD_PER_1M.
DEFAULT_TOKEN_COST_USD_PER_1M = 2.0

MODEL_TOKEN_COST_USD_PER_1M = {
    # OpenAI chat
    "openai/gpt-4o": 5.0,
    "openai/gpt-4o-mini": 0.5,
    "openai/gpt-4-turbo": 10.0,
    "openai/gpt-3.5-turbo": 1.0,
    # OpenRouter / other providers share the openai/ prefix convention.
    "openai/claude-3.5-sonnet": 3.0,
    "openai/claude-3-haiku": 0.25,
    "anthropic/claude-3.5-sonnet": 3.0,
    "anthropic/claude-3-haiku": 0.25,
}


def resolve_token_cost_per_1m(model=None):
    """Blended USD cost per 1M tokens for ``model`` (N2).

    Falls back to DEFAULT_TOKEN_COST_USD_PER_1M for unknown / unset models so the
    cost budget never silently breaks when a new model is configured.
    """
    if model and model in MODEL_TOKEN_COST_USD_PER_1M:
        return MODEL_TOKEN_COST_USD_PER_1M[model]
    return DEFAULT_TOKEN_COST_USD_PER_1M


def resolve_embedding_model():
    from .services.settings import get_setting

    return get_setting(SETTING_EMBEDDING_MODEL, DEFAULT_EMBEDDING_MODEL)


def resolve_agent_model():
    from .services.settings import get_setting

    return get_setting(SETTING_AGENT_MODEL, DEFAULT_AGENT_MODEL)


def resolve_react_max_steps():
    from .services.settings import get_setting_int

    return get_setting_int(SETTING_REACT_MAX_STEPS, DEFAULT_REACT_MAX_STEPS)


def resolve_chunk_size():
    from .services.settings import get_setting_int

    return get_setting_int(SETTING_CHUNK_SIZE, DEFAULT_CHUNK_SIZE)


def resolve_chunk_overlap():
    from .services.settings import get_setting_int

    return get_setting_int(SETTING_CHUNK_OVERLAP, DEFAULT_CHUNK_OVERLAP)


def resolve_top_k():
    from .services.settings import get_setting_int

    return get_setting_int(SETTING_TOP_K, DEFAULT_TOP_K)


def resolve_max_runtime_seconds():
    from .services.settings import get_setting_int

    return get_setting_int(SETTING_MAX_RUNTIME_SECONDS, DEFAULT_MAX_RUNTIME_SECONDS)


def resolve_idle_timeout_seconds():
    from .services.settings import get_setting_int

    return get_setting_int(SETTING_IDLE_TIMEOUT_SECONDS, DEFAULT_IDLE_TIMEOUT_SECONDS)


def resolve_token_budget():
    from .services.settings import get_setting_int

    return get_setting_int(SETTING_TOKEN_BUDGET, DEFAULT_TOKEN_BUDGET)


def resolve_cost_budget_usd():
    from .services.settings import get_setting_float

    return get_setting_float(SETTING_COST_BUDGET_USD, DEFAULT_COST_BUDGET_USD)
