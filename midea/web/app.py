"""Storyboard board (Approval Gates) — FastAPI + Server-Sent Events."""
from __future__ import annotations

import asyncio
import json
import queue
import shutil
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from ..config import settings
from ..gpu import scheduler
from ..pipelines import load_defs, route, run_async
from ..project import Project, list_projects, on_event
from ..tools import catalog

app = FastAPI(title="Midea Studio")
STATIC = Path(__file__).parent / "static"
_subs: dict[str, list[queue.Queue]] = {}
_runs: dict[str, threading.Thread] = {}


def _fanout(pid: str, ev: dict) -> None:
    for q in _subs.get(pid, []) + _subs.get("*", []):
        q.put({"project": pid, **ev})


on_event(_fanout)


def _janitor() -> None:
    while True:
        time.sleep(60)
        try:
            scheduler().unload_idle()
        except Exception:  # noqa: BLE001
            pass


threading.Thread(target=_janitor, daemon=True).start()


class NewProject(BaseModel):
    prompt: str
    pipeline: str = "auto"
    duration_s: float = 60
    aspect: str | None = None
    language: str = "zh-TW"
    real_only: bool = False
    reference_url: str | None = None
    user_media: list[str] = []
    voice: str | None = None
    music: bool = True
    subtitles: bool = True
    auto_approve: bool = False


class GateDecision(BaseModel):
    approved: bool
    note: str = ""
    edits: dict | None = None


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/meta")
def meta() -> dict:
    return {"mode": settings().mode, "pipelines": load_defs(), "currency": settings().get("gpu.currency"),
            "budget": settings().get("budget"), "tools": len(catalog())}


@app.get("/api/tools")
def tools() -> list[dict]:
    return catalog()


@app.get("/api/gpu")
def gpu() -> dict:
    return scheduler().status()


@app.post("/api/services/{name}/{action}")
def service(name: str, action: str) -> dict:
    s = scheduler()
    if name not in s.services:
        raise HTTPException(404)
    if action == "stop":
        s.services[name].stop()
    elif action == "start":
        def up() -> None:
            with s.lease(name):
                pass
        threading.Thread(target=up, daemon=True).start()
    return s.status()


@app.get("/api/projects")
def projects() -> list[dict]:
    return list_projects()


@app.post("/api/projects")
def create(req: NewProject) -> dict:
    brief = req.model_dump(exclude={"auto_approve"})
    if req.aspect:
        brief["aspect_locked"] = True
    else:
        brief.pop("aspect")
    pipe = req.pipeline if req.pipeline != "auto" else route(brief)
    p = Project.create(brief, pipe)
    _runs[p.id] = run_async(p, auto_approve=req.auto_approve)
    return {"id": p.id, "pipeline": pipe}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    d = settings().workspace / "_uploads"
    d.mkdir(exist_ok=True)
    dst = d / f"{uuid.uuid4().hex[:8]}_{Path(file.filename or 'media').name}"
    with open(dst, "wb") as fh:
        shutil.copyfileobj(file.file, fh)
    return {"path": str(dst)}


def _proj(pid: str) -> Project:
    if not (settings().workspace / pid / "project.json").exists():
        raise HTTPException(404, "project not found")
    return Project(pid)


@app.get("/api/projects/{pid}")
def project(pid: str) -> dict:
    p = _proj(pid)
    d = p.load()
    d["data"] = {s: p.stage_data(s) for s in ("reference_analysis", "proposal", "script", "scene_plan", "voice", "assets",
                                              "music_sfx", "highlights", "translate", "compose", "qa", "publish")}
    comp = d["data"].get("compose") or {}
    comp.pop("words", None)
    for o in comp.get("outputs", []):
        o.pop("words", None)
    d["running"] = pid in _runs and _runs[pid].is_alive()
    d["stages_order"] = load_defs().get(d["pipeline"], {}).get("stages", [])
    d["gates_order"] = load_defs().get(d["pipeline"], {}).get("gates", [])
    return d


@app.post("/api/projects/{pid}/gates/{gate}")
def decide(pid: str, gate: str, dec: GateDecision) -> dict:
    p = _proj(pid)
    p.decide_gate(gate, dec.approved, dec.note, dec.edits, by="board")
    if not (pid in _runs and _runs[pid].is_alive()):      # server restarted: resume the run
        _runs[pid] = run_async(p)
    return {"ok": True}


@app.post("/api/projects/{pid}/resume")
def resume(pid: str, auto_approve: bool = False) -> dict:
    p = _proj(pid)
    if pid in _runs and _runs[pid].is_alive():
        return {"ok": True, "running": True}
    _runs[pid] = run_async(p, auto_approve=auto_approve)
    return {"ok": True}


@app.post("/api/projects/{pid}/rewind/{stage}")
def rewind(pid: str, stage: str) -> dict:
    """Mark `stage` and everything after it as not done, then resume (e.g. re-cut after editing the plan)."""
    p = _proj(pid)
    order = load_defs()[p.load()["pipeline"]]["stages"]
    if stage not in order:
        raise HTTPException(400, "unknown stage")
    later = order[order.index(stage):]
    def f(d: dict) -> None:
        for s in later:
            d["stages"].pop(s, None)
            d["gates"].pop(s, None)
    p.update(f)
    if not (pid in _runs and _runs[pid].is_alive()):
        _runs[pid] = run_async(p)
    return {"ok": True, "rewound": later}


@app.put("/api/projects/{pid}/stage/{stage}")
def edit_stage(pid: str, stage: str, body: dict) -> dict:
    p = _proj(pid)
    p.checkpoint(stage, body, status=p.load()["stages"].get(stage, {}).get("status", "done"))
    return {"ok": True}


@app.get("/files/{pid}/{path:path}")
def files(pid: str, path: str) -> FileResponse:
    base = (settings().workspace / pid).resolve()
    f = (base / path).resolve()
    if base not in f.parents or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)


@app.get("/api/events/{pid}")
async def events(pid: str) -> StreamingResponse:
    q: queue.Queue = queue.Queue()
    _subs.setdefault(pid, []).append(q)

    async def gen():
        try:
            yield "retry: 2000\n\n"
            last = time.time()
            while True:
                try:
                    ev = q.get_nowait()
                    yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"
                except queue.Empty:
                    await asyncio.sleep(0.3)
                    if time.time() - last > 15:
                        last = time.time()
                        yield ": ping\n\n"
        finally:
            _subs[pid].remove(q)
    return StreamingResponse(gen(), media_type="text/event-stream")
