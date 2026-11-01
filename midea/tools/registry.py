"""Tool registry: every production capability is a named, documented, discoverable tool.

    from midea.tools import registry
    registry.discover()
    registry.call("video.ken_burns", image="a.jpg", out="a.mp4", seconds=5)

Tools declare a category, a GPU service (if any) and a rough cost model so the
planner can estimate spend before the approval gate.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    fn: Callable[..., Any]
    category: str
    summary: str
    service: str | None = None           # GPU service the tool leases (None = CPU / ffmpeg)
    est_seconds: Callable[..., float] | None = None
    tags: list[str] = field(default_factory=list)

    @property
    def params(self) -> dict:
        sig = inspect.signature(self.fn)
        return {k: (None if v.default is inspect._empty else repr(v.default)) for k, v in sig.parameters.items()}

    def describe(self) -> dict:
        return {"name": self.name, "category": self.category, "summary": self.summary,
                "service": self.service, "params": self.params, "tags": self.tags}


_REGISTRY: dict[str, Tool] = {}
_CALL_LOG: list[dict] = []


def tool(name: str, category: str, *, service: str | None = None, est_seconds: Callable[..., float] | None = None,
         tags: list[str] | None = None):
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        summary = (inspect.getdoc(fn) or "").split("\n")[0]
        _REGISTRY[name] = Tool(name, fn, category, summary, service, est_seconds, tags or [])
        fn.tool_name = name  # type: ignore[attr-defined]
        return fn
    return deco


def discover() -> dict[str, Tool]:
    from midea import tools as pkg
    for m in pkgutil.iter_modules(pkg.__path__):
        if m.name not in ("registry", "__init__"):
            importlib.import_module(f"midea.tools.{m.name}")
    return _REGISTRY


def get(name: str) -> Tool:
    if not _REGISTRY:
        discover()
    return _REGISTRY[name]


def call(name: str, **kwargs: Any) -> Any:
    t = get(name)
    t0 = time.time()
    try:
        return t.fn(**kwargs)
    finally:
        _CALL_LOG.append({"tool": name, "seconds": round(time.time() - t0, 3), "service": t.service})


def catalog() -> list[dict]:
    if not _REGISTRY:
        discover()
    return [t.describe() for t in sorted(_REGISTRY.values(), key=lambda t: (t.category, t.name))]


def call_log() -> list[dict]:
    return list(_CALL_LOG)
