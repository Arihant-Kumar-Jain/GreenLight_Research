"""Settings from .env. Keys hot-reload: `refresh()` re-reads .env on every health check, so adding a key needs no restart."""

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"

load_dotenv(REPO_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)) or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)) or default)
    except ValueError:
        return default


@dataclass
class Settings:
    # ---- LLM provider plug-in (providers.py). Nebius wins when both keys are set.
    nebius_api_key: str = field(default_factory=lambda: _env("NEBIUS_API_KEY"))
    nebius_base_url: str = field(default_factory=lambda: _env("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/"))
    openrouter_api_key: str = field(default_factory=lambda: _env("OPENROUTER_API_KEY"))
    llm_provider: str = field(default_factory=lambda: _env("GLR_LLM_PROVIDER"))
    prefer_free_models: bool = field(default_factory=lambda: _env("GLR_PREFER_FREE_MODELS") == "1")
    # Model roles; empty = auto-pick from the provider's live catalog (llm.resolve_models).
    model_fast: str = field(default_factory=lambda: _env("GLR_MODEL_FAST"))
    model_reason: str = field(default_factory=lambda: _env("GLR_MODEL_REASON"))
    model_judge: str = field(default_factory=lambda: _env("GLR_MODEL_JUDGE"))
    model_embed: str = field(default_factory=lambda: _env("GLR_MODEL_EMBED"))

    # ---- Web + scholarly sources
    tavily_api_key: str = field(default_factory=lambda: _env("TAVILY_API_KEY"))
    tavily_budget: int = field(default_factory=lambda: _int("GLR_TAVILY_BUDGET", 0))
    tavily_search_depth: str = field(default_factory=lambda: _env("GLR_TAVILY_SEARCH_DEPTH", "basic"))
    openalex_mailto: str = field(default_factory=lambda: _env("OPENALEX_MAILTO"))   # OpenAlex polite pool
    openalex_api_key: str = field(default_factory=lambda: _env("OPENALEX_API_KEY"))  # free key: own daily budget
    s2_api_key: str = field(default_factory=lambda: _env("S2_API_KEY"))             # optional Semantic Scholar
    hf_token: str = field(default_factory=lambda: _env("HF_TOKEN"))                 # optional, higher HF rate limits
    cache_web: bool = field(default_factory=lambda: _env("GLR_CACHE_WEB", "1") == "1")

    # ---- Agent harness budgets (per research run)
    max_usd_per_run: float = field(default_factory=lambda: _float("GLR_MAX_USD_PER_RUN", 0.75))
    max_research_rounds: int = field(default_factory=lambda: _int("GLR_RESEARCH_ROUNDS", 2))
    max_scouts: int = field(default_factory=lambda: _int("GLR_MAX_SCOUTS", 4))
    context_budget_tokens: int = field(default_factory=lambda: _int("GLR_CONTEXT_BUDGET", 24000))
    papers_to_read: int = field(default_factory=lambda: _int("GLR_PAPERS_TO_READ", 8))
    thinking: bool = field(default_factory=lambda: _env("GLR_THINKING", "0") == "1")

    db_path: Path = field(default_factory=lambda: Path(_env("GLR_DB_PATH", str(DATA_DIR / "glr.db"))))
    public_base_url: str = field(default_factory=lambda: _env("GLR_PUBLIC_BASE_URL", "http://localhost:8100").rstrip("/"))
    cors_origins: str = field(default_factory=lambda: _env("GLR_CORS_ORIGINS", "*"))


settings = Settings()


def refresh() -> None:
    """Re-read .env so keys added while the server runs take effect without a restart."""
    load_dotenv(REPO_DIR / ".env", override=True)
    load_dotenv(BACKEND_DIR / ".env", override=True)
    fresh = Settings()
    for f in fields(Settings):
        setattr(settings, f.name, getattr(fresh, f.name))


def missing_keys() -> list[str]:
    from . import providers
    refresh()
    missing = [] if providers.active() else [providers.key_hint()]
    return missing + ([] if settings.tavily_api_key else ["TAVILY_API_KEY"])
