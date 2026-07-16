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

DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small"
DEFAULT_AGENT_MODEL = "openai/gpt-4o-mini"
DEFAULT_REACT_MAX_STEPS = 12
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 200
DEFAULT_TOP_K = 6

EMBEDDING_DIMENSIONS = {
    "openai/text-embedding-3-small": 1536,
    "openai/text-embedding-3-large": 3072,
    "qwen/qwen3-embedding-8b": 4096,
}


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
