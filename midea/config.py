"""Configuration loading (config.yaml + .env + env overrides)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class Settings:
    raw: dict[str, Any]
    root: Path = ROOT
    path: Path | None = None
    _overrides: dict[str, Any] = field(default_factory=dict)

    def get(self, dotted: str, default: Any = None) -> Any:
        cur: Any = self.raw
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    @property
    def mode(self) -> str:
        return os.environ.get("MIDEA_MODE", self.raw.get("mode", "local"))

    @property
    def workspace(self) -> Path:
        p = Path(os.environ.get("MIDEA_WORKSPACE", self.raw.get("workspace", "./projects")))
        if not p.is_absolute():
            p = self.root / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def services(self) -> dict[str, dict[str, Any]]:
        return self.raw.get("services", {})


_settings: Settings | None = None


def load(path: str | Path | None = None) -> Settings:
    global _settings
    p = Path(path or os.environ.get("MIDEA_CONFIG", ROOT / "config.yaml"))
    _load_dotenv(ROOT / ".env")
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    _settings = Settings(raw=raw or {}, path=p)
    return _settings


def settings() -> Settings:
    return _settings or load()
