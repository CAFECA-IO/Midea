"""Project store: resumable JSON checkpoints, decision log, approval gates, event stream."""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .config import settings

_listeners: list[Callable[[str, dict], None]] = []
_locks: dict[str, threading.RLock] = {}


def on_event(fn: Callable[[str, dict], None]) -> None:
    _listeners.append(fn)


class Project:
    def __init__(self, pid: str):
        self.id = pid
        self.dir = settings().workspace / pid
        self.dir.mkdir(parents=True, exist_ok=True)
        self.lock = _locks.setdefault(pid, threading.RLock())
        self._gate_events: dict[str, threading.Event] = {}

    # ---------------------------------------------------------------- creation / io
    @classmethod
    def create(cls, brief: dict, pipeline: str) -> "Project":
        slug = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        p = cls(slug)
        p.save({"id": slug, "created": time.time(), "brief": brief, "pipeline": pipeline, "status": "created",
                "stage": None, "stages": {}, "gates": {}, "cost": {"estimated": 0.0, "actual": 0.0, "lines": []},
                "decisions": [], "events": [], "deliverables": {}})
        return p

    @property
    def file(self) -> Path:
        return self.dir / "project.json"

    def load(self) -> dict:
        with self.lock:
            return json.loads(self.file.read_text(encoding="utf-8"))

    def save(self, data: dict) -> None:
        with self.lock:
            tmp = self.file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            tmp.replace(self.file)

    def update(self, fn: Callable[[dict], None]) -> dict:
        with self.lock:
            d = self.load()
            fn(d)
            self.save(d)
            return d

    def path(self, *parts: str) -> Path:
        p = self.dir.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def rel(self, p: str | Path) -> str:
        try:
            return str(Path(p).resolve().relative_to(self.dir.resolve()))
        except ValueError:
            return str(p)

    # ---------------------------------------------------------------- checkpoints
    def checkpoint(self, stage: str, data: Any, status: str = "done") -> None:
        (self.dir / "stages").mkdir(exist_ok=True)
        (self.dir / "stages" / f"{stage}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str),
                                                            encoding="utf-8")
        def f(d: dict) -> None:
            d["stages"][stage] = {"status": status, "at": time.time()}
        self.update(f)
        self.emit("stage", {"stage": stage, "status": status})

    def stage_data(self, stage: str, default: Any = None) -> Any:
        f = self.dir / "stages" / f"{stage}.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else default

    def decide(self, what: str, why: str, alternatives: list | None = None) -> None:
        self.update(lambda d: d["decisions"].append({"at": time.time(), "what": what, "why": why,
                                                       "alternatives": alternatives or []}))

    # ---------------------------------------------------------------- events
    def emit(self, kind: str, payload: dict) -> None:
        ev = {"at": time.time(), "kind": kind, **payload}
        def f(d: dict) -> None:
            d["events"] = (d.get("events", []) + [ev])[-400:]
        self.update(f)
        for fn in _listeners:
            try:
                fn(self.id, ev)
            except Exception:  # noqa: BLE001
                pass

    def set_status(self, status: str, stage: str | None = None) -> None:
        def f(d: dict) -> None:
            d["status"] = status
            if stage is not None:
                d["stage"] = stage
        self.update(f)
        self.emit("status", {"status": status, "stage": stage})

    # ---------------------------------------------------------------- approval gates
    def gate(self, name: str, summary: dict, *, timeout: float | None = None, auto: bool = False) -> dict:
        """Pause until a human approves/rejects on the board (or CLI). Returns the decision record."""
        if auto:
            rec = {"status": "approved", "by": "auto", "at": time.time(), "note": "", "summary": summary}
            self.update(lambda d: d["gates"].__setitem__(name, rec))
            self.emit("gate", {"gate": name, "status": "approved", "auto": True})
            return rec
        cur = self.load()["gates"].get(name, {})
        if cur.get("status") in ("approved", "rejected") and cur.get("consumed") is False:
            # decided while no runner was waiting (e.g. the board restarted): use that decision once
            self.update(lambda d: d["gates"][name].__setitem__("consumed", True))
            self.set_status("running", name)
            return {**cur, "consumed": True}
        ev = threading.Event()
        self._gate_events[name] = ev
        GATE_WAITERS[(self.id, name)] = ev
        self.update(lambda d: d["gates"].__setitem__(name, {"status": "awaiting", "at": time.time(), "summary": summary}))
        self.set_status("awaiting_approval", name)
        self.emit("gate", {"gate": name, "status": "awaiting"})
        while not ev.wait(timeout=1.0):
            rec = self.load()["gates"].get(name, {})
            if rec.get("status") in ("approved", "rejected"):   # decided via another process (CLI)
                break
        GATE_WAITERS.pop((self.id, name), None)
        self.update(lambda d: d["gates"][name].__setitem__("consumed", True))
        rec = self.load()["gates"][name]
        self.set_status("running", name)
        return rec

    def decide_gate(self, name: str, approved: bool, note: str = "", edits: dict | None = None, by: str = "user") -> None:
        def f(d: dict) -> None:
            g = d["gates"].setdefault(name, {})
            g.update(status="approved" if approved else "rejected", note=note, by=by, decided_at=time.time(), consumed=False)
            g.pop("edits", None)
            if edits:
                g["edits"] = edits
        self.update(f)
        self.emit("gate", {"gate": name, "status": "approved" if approved else "rejected", "note": note})
        ev = GATE_WAITERS.get((self.id, name))
        if ev:
            ev.set()


GATE_WAITERS: dict[tuple[str, str], threading.Event] = {}


def list_projects() -> list[dict]:
    out = []
    for f in sorted(settings().workspace.glob("*/project.json"), reverse=True):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append({k: d.get(k) for k in ("id", "created", "pipeline", "status", "stage")} |
                       {"title": d.get("brief", {}).get("prompt", "")[:80], "cost": d.get("cost", {})})
        except Exception:  # noqa: BLE001
            continue
    return out
