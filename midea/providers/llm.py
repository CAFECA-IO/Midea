"""Qwen3.8-Flash-Next via any OpenAI-compatible endpoint (llama-server / vLLM / SGLang)."""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

import httpx

from ..config import settings
from ..gpu import scheduler
from ..log import get_logger
from . import mock_llm

log = get_logger("llm")

_JSON_RE = re.compile(r"\{.*\}|\[.*\]", re.S)


def _extract_json(text: str) -> Any:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_RE.search(text)
        if not m:
            raise
        return json.loads(m.group(0))


def _image_part(path: str | Path) -> dict:
    data = base64.b64encode(Path(path).read_bytes()).decode()
    ext = Path(path).suffix.lstrip(".").lower().replace("jpg", "jpeg") or "png"
    return {"type": "image_url", "image_url": {"url": f"data:image/{ext};base64,{data}"}}


class LLM:
    service = "qwen"

    def __init__(self) -> None:
        cfg = settings().services.get(self.service, {})
        self.base_url = cfg.get("base_url", "http://127.0.0.1:8080/v1")
        self.sampling = cfg.get("sampling", {})
        self.model = cfg.get("model", "qwen")

    def chat(self, system: str, user: str, *, images: list[str | Path] | None = None,
             max_tokens: int = 8192, temperature: float | None = None) -> str:
        content: Any = user
        if images:
            content = [{"type": "text", "text": user}, *(_image_part(p) for p in images[:12])]
        body = {"model": self.model, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
                **{k: v for k, v in self.sampling.items() if k in ("temperature", "top_p", "top_k", "presence_penalty")}}
        if temperature is not None:
            body["temperature"] = temperature
        with scheduler().lease(self.service):
            r = httpx.post(f"{self.base_url}/chat/completions", json=body, timeout=1800)
            r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def json(self, task: str, system: str, user: str, *, images: list | None = None,
             context: dict | None = None, retries: int = 2) -> Any:
        """Ask for strict JSON. In mock mode a deterministic local planner answers instead."""
        if settings().mode == "mock":
            return mock_llm.answer(task, user, context or {})
        sys = system + "\n\nRespond with ONE valid JSON value only. No prose, no markdown fences."
        last: Exception | None = None
        for attempt in range(retries + 1):
            text = self.chat(sys, user if attempt == 0 else f"{user}\n\n(Previous answer was not valid JSON: {last})",
                             images=images, temperature=0.4 if attempt else None)
            try:
                return _extract_json(text)
            except Exception as e:  # noqa: BLE001
                last = e
                log.warning("LLM returned invalid JSON for %s (attempt %d): %s", task, attempt + 1, e)
        raise ValueError(f"LLM failed to return JSON for task {task}: {last}")


_llm: LLM | None = None


def llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLM()
    return _llm
