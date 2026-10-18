"""LLM client: model routing, JSON outputs, embeddings, cost trace. (Ported from Greenlight; the tool loop lives in
harness/agent.py.)

The endpoint comes from the active provider plug-in (providers.py): Nebius Token Factory, or OpenRouter as a
stand-in with the same open models. Agents never see which one is used.

Model roles (larger and smaller models working together):
  fast   - Nemotron Nano class: high-volume work (scouts' triage, paper audits, quote checks, context compression)
  reason - Nemotron Super class: multi-step agents (lead researcher, scouts, novelty mapping, Chamber speakers, chat)
  judge  - Nemotron Ultra class: the Speaker's green/amber/red ruling, where judgment matters most
  embed  - Qwen3 Embedding 8B: dense retrieval over the paper corpus
Roles resolve against the active provider's live catalog unless pinned in .env.
"""

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypeVar

from json_repair import repair_json
from openai import AsyncOpenAI, BadRequestError
from pydantic import BaseModel, ValidationError

from . import providers, trace
from .privacy import scrub_secrets
from .config import settings

ROLE_PREFERENCES: dict[str, list[str]] = {
    "fast": ["nemotron-3-nano", "nemotron-3_5-lightning", "nemotron-3_5-nano", "nemotron-nano"],
    "reason": ["nemotron-3-super", "nemotron-3_5-super", "nemotron-super"],
    "judge": ["nemotron-3-ultra", "nemotron-3_5-ultra", "nemotron-ultra"],
    "embed": ["qwen3-embedding-8b", "qwen3-embedding-4b", "qwen3-embedding", "bge-en-icl"],
}
FALLBACK_ROLE = {"judge": "reason", "reason": "fast", "fast": "reason"}
NOT_CHAT = ("embed", "omni", "-vl", "vision", "reward", "guard", "safety", "parse", "flux", "image")

_client: AsyncOpenAI | None = None
_client_for: tuple[str, str, bool] | None = None  # (provider, key, prefer_free) the caches below belong to
_catalog: dict[str, dict] | None = None
_resolved: dict[str, str] = {}
_thinking_param_ok = True
_catalog_lock = asyncio.Lock()


class LLMError(RuntimeError):
    pass


def provider() -> providers.Provider:
    p = providers.active()
    if p is None:
        raise LLMError(f"No LLM provider key set. Add {providers.key_hint()} to GreenLight_Research/.env")
    return p


def provider_label() -> str:
    p = providers.active()
    return p.label if p else "none"


def client() -> AsyncOpenAI:
    global _client, _client_for, _catalog, _thinking_param_ok
    p = provider()
    ident = (p.name, p.api_key, settings.prefer_free_models)
    if _client is None or _client_for != ident:
        _client = AsyncOpenAI(base_url=p.base_url, api_key=p.api_key, default_headers=p.headers() or None,
                              timeout=240, max_retries=3)
        _client_for = ident
        _catalog = None  # new provider or key: re-read the catalog and re-resolve model roles
        _resolved.clear()
        _thinking_param_ok = True
    return _client


# ---------------------------------------------------------------- catalog & routing

async def catalog() -> dict[str, dict]:
    """Live model list with pricing (USD per token) and context length."""
    global _catalog
    client()  # validates the key (and resets the cache if the provider changed)
    async with _catalog_lock:
        if _catalog is None:
            _catalog = await provider().catalog()
        return _catalog


def _price(model: str) -> tuple[float, float]:
    m = (_catalog or {}).get(model) or {}
    p = m.get("pricing") or {}
    try:
        return float(p.get("prompt") or 0), float(p.get("completion") or 0)
    except (TypeError, ValueError):
        return 0.0, 0.0


def _pick(ids: list[str], role: str) -> str | None:
    for pref in ROLE_PREFERENCES[role]:
        hits = [i for i in ids if pref in i.lower()]
        if role != "embed":
            hits = [i for i in hits if not any(x in i.lower() for x in NOT_CHAT)]
        if hits:
            # Prefer the base flavour over "-fast" for reasoning roles, and the fast flavour for "fast".
            # ":free" variants (OpenRouter) only when GL_PREFER_FREE_MODELS=1.
            hits.sort(key=lambda i: (i.endswith(":free") != settings.prefer_free_models,
                                     ("-fast" in i.lower()) != (role == "fast"), len(i)))
            return hits[0]
    return None


async def resolve_models() -> dict[str, str]:
    client()  # resets the cached roles first if the provider or key changed
    if _resolved:
        return _resolved
    pinned = {"fast": settings.model_fast, "reason": settings.model_reason,
              "judge": settings.model_judge, "embed": settings.model_embed}
    ids = list((await catalog()).keys())
    for role in ("fast", "reason", "judge", "embed"):
        _resolved[role] = pinned[role] or _pick(ids, role) or ""
    for role in ("judge", "reason", "fast"):
        if not _resolved[role]:
            _resolved[role] = _resolved.get(FALLBACK_ROLE[role], "")
    if not _resolved["reason"]:
        raise LLMError(f"No Nemotron model found in the {provider().label} catalog: {ids[:30]}")
    return _resolved


def pretty_model(model_id: str) -> str:
    name = model_id.split("/")[-1].replace("_", ".")
    name = re.sub(r"(?i)^nvidia-", "", name)
    return name


async def model_info() -> dict:
    roles = await resolve_models()
    cat = await catalog()
    out = {"provider": provider().label}
    for role, mid in roles.items():
        m = cat.get(mid, {})
        pin, pout = _price(mid)
        out[role] = {"id": mid, "name": pretty_model(mid), "context_length": m.get("context_length"),
                     "price_in_per_m": round(pin * 1e6, 4), "price_out_per_m": round(pout * 1e6, 4)}
    return out


# ---------------------------------------------------------------- helpers

THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def strip_think(text: str | None) -> str:
    if not text:
        return ""
    text = THINK_RE.sub("", text)
    if "</think>" in text:  # opening tag was in the prompt template
        text = text.split("</think>", 1)[1]
    return text.strip()


def extract_json(text: str) -> Any:
    text = strip_think(text)
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON object in model output")
    end = max(text.rfind("}"), text.rfind("]"))
    blob = text[start:end + 1]
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        # Long outputs (the comparison matrix) sometimes carry a stray quote or a missing comma.
        fixed = repair_json(blob, return_objects=True)
        if not isinstance(fixed, (dict, list)) or not fixed:
            raise ValueError("model output is not repairable JSON")
        return fixed


@dataclass
class ChatResult:
    text: str
    model: str
    tool_calls: list[dict] = field(default_factory=list)
    reasoning: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    raw_message: dict | None = None


# ---------------------------------------------------------------- chat

# Offline test seam: when set, chat() calls this instead of the provider (tests/test_harness.py).
FAKE: Callable[..., Awaitable["ChatResult"]] | None = None


async def chat(role: str, messages: list[dict], *, title: str, tools: list[dict] | None = None,
               json_mode: bool = False, temperature: float = 0.2, max_tokens: int = 8192,
               thinking: bool | None = None) -> ChatResult:
    """One chat completion on the active provider, traced with tokens, latency and cost."""
    global _thinking_param_ok
    if FAKE is not None:
        res = await FAKE(role, messages, tools=tools, title=title)
        trace.log("llm", title, res.text[:1200] or str(res.tool_calls)[:1200], provider="fake", model=f"fake-{role}",
                  tokens_in=res.tokens_in, tokens_out=res.tokens_out, latency_ms=0, cost_usd=res.cost_usd)
        return res
    if thinking is None:
        thinking = settings.thinking
    roles = await resolve_models()
    model = roles.get(role) or role
    messages = [{**m, "content": scrub_secrets(m["content"])} if isinstance(m.get("content"), str) else m
                for m in messages]
    kwargs: dict[str, Any] = dict(model=model, messages=messages, temperature=temperature, max_tokens=max_tokens)
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    extra = dict(provider().request_body())
    if thinking is not None and _thinking_param_ok and "nemotron" in model.lower():
        extra.update(provider().thinking_body(thinking))
    if extra:
        kwargs["extra_body"] = extra

    t0 = time.perf_counter()
    try:
        resp = await client().chat.completions.create(**kwargs)
    except BadRequestError as e:
        msg = str(e).lower()
        retry = dict(kwargs)
        if "chat_template_kwargs" in msg or "enable_thinking" in msg or "reasoning" in msg:
            _thinking_param_ok = False
            retry.pop("extra_body", None)
        elif "response_format" in msg or "json" in msg:
            retry.pop("response_format", None)
        else:
            retry.pop("extra_body", None)
            retry.pop("response_format", None)
        resp = await client().chat.completions.create(**retry)
    latency = int((time.perf_counter() - t0) * 1000)

    msg = resp.choices[0].message
    extra = getattr(msg, "model_extra", None) or {}
    reasoning = getattr(msg, "reasoning_content", None) or extra.get("reasoning_content") or extra.get("reasoning")
    content = msg.content or ""
    if not reasoning and "<think>" in content:
        m = re.search(r"<think>(.*?)</think>", content, re.S)
        reasoning = m.group(1).strip() if m else None
    text = strip_think(content)

    tool_calls = [{"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
                  for tc in (msg.tool_calls or [])]
    if tools and not tool_calls:
        tool_calls = _text_tool_calls(text)

    usage = resp.usage
    tin = getattr(usage, "prompt_tokens", 0) or 0
    tout = getattr(usage, "completion_tokens", 0) or 0
    pin, pout = _price(model)
    cost = tin * pin + tout * pout

    raw_message: dict = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        raw_message["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]

    detail = text[:1200] if text else ("→ " + ", ".join(f"{t['name']}({t['arguments'][:160]})" for t in tool_calls))
    trace.log("llm", title, detail, provider=provider_label(), model=model, tokens_in=tin, tokens_out=tout,
              latency_ms=latency, cost_usd=cost)
    return ChatResult(text=text, model=model, tool_calls=tool_calls, reasoning=reasoning, tokens_in=tin,
                      tokens_out=tout, latency_ms=latency, cost_usd=cost, raw_message=raw_message)


def _text_tool_calls(text: str) -> list[dict]:
    """Some serving stacks return tool calls inline as <tool_call>{...}</tool_call>."""
    calls = []
    for i, m in enumerate(re.finditer(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.S)):
        try:
            obj = json.loads(m.group(1))
            calls.append({"id": f"inline_{i}", "name": obj.get("name"),
                          "arguments": json.dumps(obj.get("arguments", obj.get("parameters", {})))})
        except json.JSONDecodeError:
            continue
    return calls


T = TypeVar("T", bound=BaseModel)


async def chat_json(role: str, system: str, user: str, schema: type[T], *, title: str,
                    temperature: float = 0.1, max_tokens: int = 8192, thinking: bool | None = None) -> T:
    """Structured output: schema in the prompt + JSON mode + Pydantic validation + one repair turn."""
    schema_txt = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    sys = (f"{system}\n\nRespond with ONLY a JSON object (no prose, no markdown) that validates against "
           f"this JSON Schema:\n{schema_txt}")
    messages = [{"role": "system", "content": sys}, {"role": "user", "content": user}]
    last_err = None
    for attempt in range(3):
        res = await chat(role, messages, title=title if attempt == 0 else f"{title} (repair)", json_mode=True,
                         temperature=temperature, max_tokens=max_tokens, thinking=thinking)
        try:
            return schema.model_validate(extract_json(res.text))
        except (ValueError, ValidationError) as e:
            last_err = e
            messages += [{"role": "assistant", "content": res.text[:6000]},
                         {"role": "user", "content": f"That was not valid against the schema: {str(e)[:800]}. "
                                                     "Return the corrected JSON object only."}]
    raise LLMError(f"{title}: could not get valid JSON ({last_err})")


# ---------------------------------------------------------------- embeddings

EMBED_FAKE: Callable[[list[str]], list[list[float]]] | None = None  # offline test seam


async def embed(texts: list[str], *, query: bool = False, title: str = "Embed", batch: int = 64) -> list[list[float]]:
    if EMBED_FAKE is not None:
        return EMBED_FAKE(texts)
    roles = await resolve_models()
    model = roles["embed"]
    if query and "qwen3-embedding" in model.lower():
        # Qwen3-Embedding is instruction-aware on the query side.
        texts = [f"Instruct: Given a research question, retrieve scientific paper passages that answer it"
                 f"\nQuery: {t}" for t in texts]
    out: list[list[float]] = []
    t0 = time.perf_counter()
    tokens = 0
    for i in range(0, len(texts), batch):
        resp = await client().embeddings.create(model=model, input=texts[i:i + batch], encoding_format="float")
        out.extend(d.embedding for d in sorted(resp.data, key=lambda d: d.index))
        tokens += getattr(resp.usage, "total_tokens", 0) or 0
    pin, _ = _price(model)
    trace.log("llm", title, f"{len(texts)} text(s) → {len(out[0]) if out else 0}-dim vectors", provider=provider_label(),
              model=model, tokens_in=tokens, tokens_out=0, latency_ms=int((time.perf_counter() - t0) * 1000),
              cost_usd=tokens * pin)
    return out
