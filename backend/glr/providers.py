"""LLM providers as plug-ins. Every agent talks to llm.py; llm.py talks to whichever provider is active here.

Both providers speak the OpenAI API and serve the same open models (Nemotron Nano / Super / Ultra, Qwen3 embeddings),
so switching changes the endpoint, key, catalog and a few request details, never the agent code.

Choice: GLR_LLM_PROVIDER=nebius|openrouter, or empty = auto (Nebius when NEBIUS_API_KEY is set, else OpenRouter).
Adding a provider: subclass Provider, implement the hooks that differ, register it in PROVIDERS.
"""

from dataclasses import dataclass
from typing import Any

import httpx

from .config import settings


@dataclass(frozen=True)
class Provider:
    name: str        # id used in GLR_LLM_PROVIDER
    label: str       # shown in the activity panel and trace
    base_url: str
    key_env: str

    @property
    def api_key(self) -> str:
        return ""

    def headers(self) -> dict[str, str]:
        return {}

    def thinking_body(self, on: bool) -> dict[str, Any]:
        """extra_body that switches Nemotron's reasoning trace on or off."""
        return {}

    def request_body(self) -> dict[str, Any]:
        """extra_body sent with every chat request."""
        return {}

    async def catalog(self) -> dict[str, dict]:
        """Live model list: {id: {"pricing": {"prompt": usd_per_token, "completion": ...}, "context_length": n}}."""
        return await self._get_models("/models")

    async def _get_models(self, path: str, params: dict | None = None) -> dict[str, dict]:
        async with httpx.AsyncClient(timeout=30) as h:
            r = await h.get(self.base_url.rstrip("/") + path, params=params,
                            headers={"Authorization": f"Bearer {self.api_key}", **self.headers()})
            r.raise_for_status()
            return {m["id"]: m for m in r.json().get("data", [])}


class Nebius(Provider):
    @property
    def api_key(self) -> str:
        return settings.nebius_api_key

    def thinking_body(self, on: bool) -> dict[str, Any]:
        return {"chat_template_kwargs": {"enable_thinking": on}}  # vLLM chat template switch

    async def catalog(self) -> dict[str, dict]:
        return await self._get_models("/models", {"verbose": "true"})


class OpenRouter(Provider):
    @property
    def api_key(self) -> str:
        return settings.openrouter_api_key

    def headers(self) -> dict[str, str]:
        return {"HTTP-Referer": settings.public_base_url, "X-Title": "GreenLight Research"}

    def thinking_body(self, on: bool) -> dict[str, Any]:
        return {"reasoning": {"enabled": on}}

    def request_body(self) -> dict[str, Any]:
        # Route only to upstreams that support every parameter we send (JSON mode, tools, reasoning switch).
        return {"provider": {"require_parameters": True}}

    async def catalog(self) -> dict[str, dict]:
        # Chat and embedding models are listed separately on OpenRouter.
        return {**await self._get_models("/models"), **await self._get_models("/embeddings/models")}


PROVIDERS: dict[str, Provider] = {
    "nebius": Nebius("nebius", "Nebius Token Factory", settings.nebius_base_url, "NEBIUS_API_KEY"),
    "openrouter": OpenRouter("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
}


def active() -> Provider | None:
    """The provider to use now, or None when no key is configured. Re-evaluated on each call (keys hot-reload)."""
    choice = settings.llm_provider.lower()
    if choice:
        p = PROVIDERS.get(choice)
        return p if p and p.api_key else None
    for p in PROVIDERS.values():  # auto: first provider with a key, Nebius first
        if p.api_key:
            return p
    return None


def key_hint() -> str:
    """What to put in .env when no provider is usable."""
    choice = settings.llm_provider.lower()
    if choice in PROVIDERS:
        return PROVIDERS[choice].key_env
    return " or ".join(p.key_env for p in PROVIDERS.values())
