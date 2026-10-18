"""Tools for the agent harness: a Python function + its signature become an OpenAI tool schema.

    @tool("Search arXiv for papers.")
    async def search_arxiv(query: Annotated[str, Field(description="keywords")], max_results: int = 8) -> dict: ...

Arguments are validated with a pydantic model built from the signature. Tools never raise into the loop: bad
arguments and exceptions come back to the model as {"error", "detail"} so it can correct itself.
Each tool may define `digest(result) -> str`, the short form kept when context compression elides old results.
"""

import inspect
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, get_type_hints

from pydantic import BaseModel, ValidationError, create_model


def _clean(schema: dict) -> dict:
    """Drop pydantic's noise (titles) so schemas stay small in every request."""
    if isinstance(schema, dict):
        return {k: _clean(v) for k, v in schema.items() if k != "title"}
    if isinstance(schema, list):
        return [_clean(v) for v in schema]
    return schema


@dataclass
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    fn: Callable[..., Awaitable[Any]]
    terminal: bool = False                       # calling it ends the agent run (a "finish" tool)
    digest: Callable[[Any], str] | None = None

    def schema(self) -> dict:
        params = _clean(self.args.model_json_schema())
        params.setdefault("properties", {})
        return {"type": "function", "function": {"name": self.name, "description": self.description,
                                                 "parameters": params}}

    def parse(self, raw: str | dict | None) -> BaseModel:
        data = raw if isinstance(raw, dict) else json.loads(raw or "{}")
        return self.args.model_validate(data)

    async def call(self, raw: str | dict | None) -> Any:
        try:
            args = self.parse(raw)
        except (ValidationError, ValueError) as e:
            return {"error": "bad_arguments", "detail": str(e)[:800]}
        try:
            return await self.fn(**args.model_dump())
        except Exception as e:  # the model sees the error and can change course
            return {"error": type(e).__name__, "detail": str(e)[:800]}


def tool(description: str, *, name: str | None = None, terminal: bool = False,
         digest: Callable[[Any], str] | None = None) -> Callable[[Callable], Tool]:
    def deco(fn: Callable) -> Tool:
        hints = get_type_hints(fn, include_extras=True)
        fields: dict[str, Any] = {}
        for p in inspect.signature(fn).parameters.values():
            ann = hints.get(p.name, Any)
            fields[p.name] = (ann, ... if p.default is inspect.Parameter.empty else p.default)
        model = create_model(f"{fn.__name__}_args", **fields)
        return Tool(name or fn.__name__, description.strip(), model, fn, terminal, digest)
    return deco


def finish_tool(model: type[BaseModel], description: str, name: str = "finish") -> Tool:
    """A terminal tool whose arguments are the agent's structured output."""
    async def _finish(**kwargs):
        return kwargs
    return Tool(name, description, model, _finish, terminal=True)


def short(value: Any, n: int = 160) -> str:
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[: n - 1] + "…"
