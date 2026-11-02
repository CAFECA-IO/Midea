"""Configuration loading (config.yaml + .env + env overrides)."""
from __future__ import annotations

import os
import re
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

    def mocked(self, service: str) -> bool:
        """True when `service` should use its offline stand-in: global mock mode, or listed in
        MIDEA_MOCK_SERVICES (e.g. "h3,acestep") to test real planning while GPU models are unavailable."""
        if self.mode == "mock":
            return True
        listed = os.environ.get("MIDEA_MOCK_SERVICES", self.raw.get("mock_services", "")) or ""
        if isinstance(listed, list):
            listed = ",".join(listed)
        return service in {x.strip() for x in listed.split(",") if x.strip()} or "all" in listed

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
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    # ${VAR} / ${VAR:-default} expansion so one config works on laptops and shared servers
    text = re.sub(r"\$\{(\w+)(?::-([^}]*))?\}", lambda m: os.environ.get(m.group(1), m.group(2) or ""), text)
    raw = yaml.safe_load(text) if text else {}
    _settings = Settings(raw=raw or {}, path=p)
    return _settings


def settings() -> Settings:
    return _settings or load()
