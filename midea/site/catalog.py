"""Read-only catalog of what the public site may show: published projects and passed actor intros.

A *work* is one published project; each deliverable version (60 s / 15 s × 16:9 / 9:16 / 1:1) is a *video*.
Video ids are stable hashes of (project, file) so reactions and views survive restarts and re-scans.
Nothing outside `final/` (and an actor's headshot and passed intro) is ever served.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..config import settings

KIND = {"ad-60": "廣告", "ad": "廣告", "cinematic": "短片", "animated-explainer": "動畫", "actor-intro": "演員自我介紹"}


@dataclass
class Video:
    id: str
    work: str                      # project id, or "actor:<handle>"
    title: str
    subtitle: str = ""
    kind: str = "短片"
    duration: float = 0.0
    aspect: str = "16:9"
    length: str = ""               # "60s" | "15s" | ""
    file: str = ""                 # absolute path (never sent to clients)
    thumb: str = ""                # absolute path
    srt: str = ""
    actors: list[str] = field(default_factory=list)     # handles
    created: float = 0.0
    description: str = ""
    primary: bool = False          # the version shown on tiles (16:9, longest)

    def public(self, actor_names: dict[str, str] | None = None) -> dict:
        d = {k: v for k, v in asdict(self).items() if k not in ("file", "thumb", "srt")}
        d["src"] = f"/media/v/{self.id}.mp4"
        d["image"] = f"/media/t/{self.id}.jpg"
        d["captions"] = f"/media/c/{self.id}.vtt" if self.srt else None
        d["duration_label"] = fmt_dur(self.duration)
        if actor_names is not None:
            d["cast"] = [{"handle": h, "name": actor_names.get(h, h)} for h in self.actors]
        return d


@dataclass
class Actor:
    id: str
    handle: str
    name: str
    role: str = ""
    age: int | None = None
    headshot: str = ""             # absolute path
    intro_video: str | None = None  # video id of the passed intro

    def public(self) -> dict:
        return {"handle": self.handle, "name": self.name, "role": self.role, "age": self.age,
                "image": f"/media/a/{self.handle}.jpg", "intro": self.intro_video}


def fmt_dur(s: float) -> str:
    s = int(round(s or 0))
    return f"{s // 60}:{s % 60:02d}"


def _vid(work: str, rel: str) -> str:
    return hashlib.sha1(f"{work}|{rel}".encode()).hexdigest()[:12]


def _probe(path: Path, cache: dict) -> float:
    key = f"{path}|{path.stat().st_mtime_ns}"
    if key in cache:
        return cache[key]
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        d = float(out or 0)
    except Exception:  # noqa: BLE001
        d = 0.0
    cache[key] = d
    return d


_SUFFIX = re.compile(r"_(60|15)s_(16x9|9x16|1x1)$")


class Catalog:
    """Re-scanned at most every `ttl` seconds; cheap enough for a handful of projects per week."""

    def __init__(self, ttl: float = 120):
        self.ttl = ttl
        self._at = 0.0
        self._lock = threading.Lock()
        self.videos: dict[str, Video] = {}
        self.actors: dict[str, Actor] = {}
        self._dur_cache: dict[str, float] = {}
        # set by the site: creators' works and actors appear only after the publish review
        self.project_ok = lambda d: True
        self.actor_ok = lambda d: True

    def refresh(self, force: bool = False) -> "Catalog":
        with self._lock:
            if not force and time.time() - self._at < self.ttl:
                return self
            ws = settings().workspace
            actors = self._scan_actors(ws / "_actors")
            by_id = {a.id: a for a in actors.values()}
            videos: dict[str, Video] = {}
            for pj in sorted(ws.glob("*/project.json")):
                try:
                    for v in self._scan_project(pj, by_id):
                        videos[v.id] = v
                except Exception:  # noqa: BLE001
                    continue
            for a in actors.values():
                v = self._intro_video(ws / "_actors" / a.id, a)
                if v:
                    videos[v.id] = v
                    a.intro_video = v.id
            self.videos, self.actors, self._at = videos, actors, time.time()
            return self

    # ---------------------------------------------------------------- scanning
    def _scan_actors(self, root: Path) -> dict[str, Actor]:
        out: dict[str, Actor] = {}
        for f in sorted(root.glob("*/actor.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if not d.get("handle") or not self.actor_ok(d):
                continue
            head = ""
            for p in d.get("portraits") or []:
                if p.get("view") == "headshot" and (f.parent / p.get("file", "")).exists():
                    head = str(f.parent / p["file"])
            if not head:
                continue                         # no approved look yet → not on the public site
            out[d["handle"]] = Actor(id=d.get("id", f.parent.name), handle=d["handle"], name=d.get("name") or d["handle"],
                                     role=d.get("occupation") or "", age=d.get("age"), headshot=head)
        return out

    def _intro_video(self, adir: Path, a: Actor) -> Video | None:
        try:
            d = json.loads((adir / "actor.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
        intro = d.get("intro") or {}
        if intro.get("status") != "pass" or intro.get("mock") or not intro.get("file"):
            return None
        f = adir / intro["file"]
        if not f.exists():
            return None
        poster = adir / intro.get("poster", "")
        return Video(id=_vid(f"actor:{a.handle}", intro["file"]), work=f"actor:{a.handle}", title=f"{a.name} 自我介紹",
                     subtitle=f"@{a.handle} · {a.role}", kind=KIND["actor-intro"], duration=_probe(f, self._dur_cache),
                     aspect="4:5", file=str(f), thumb=str(poster if poster.is_file() else a.headshot),
                     actors=[a.handle], created=float(intro.get("at") or 0), description=intro.get("text", ""), primary=True)

    def _scan_project(self, pj: Path, actors_by_id: dict[str, Actor]) -> list[Video]:
        d = json.loads(pj.read_text(encoding="utf-8"))
        if d.get("status") != "done" or not (pj.parent / "stages" / "publish.json").exists() or not self.project_ok(d):
            return []
        items = (d.get("deliverables") or {}).get("items") or []
        if not items:
            return []
        root = pj.parent
        brief = d.get("brief") or {}
        handles = [actors_by_id[a].handle for a in brief.get("actors") or [] if a in actors_by_id]
        title, desc = self._title(root, d)
        kind = KIND.get(d.get("pipeline", ""), "短片")
        brand = ""
        copy = _json(root / "stages" / "copy.json")
        if copy.get("headline"):
            title = copy["headline"]
            brand = (copy.get("cta") or "").strip()
        out: list[Video] = []
        for it in items:
            rel = it.get("video")
            if not rel or not (root / rel).is_file():
                continue
            stem = Path(rel).stem
            m = _SUFFIX.search(stem)
            length = (m.group(1) + "s") if m else ""
            aspect = m.group(2).replace("x", ":") if m else (brief.get("aspect") or "16:9")
            thumb = root / (it.get("thumbnail") or "")
            sub = " · ".join(x for x in [kind, brand] if x)
            out.append(Video(id=_vid(d["id"], rel), work=d["id"], title=title, subtitle=sub, kind=kind,
                             duration=_probe(root / rel, self._dur_cache), aspect=aspect, length=length,
                             file=str(root / rel), thumb=str(thumb) if thumb.is_file() else "",
                             srt=str(root / it["srt"]) if it.get("srt") and (root / it["srt"]).is_file() else "",
                             actors=handles, created=float(d.get("created") or 0), description=desc))
        if out:
            best = sorted(out, key=lambda v: (v.aspect != "16:9", -v.duration))[0]
            best.primary = True
        return out

    @staticmethod
    def _title(root: Path, d: dict) -> tuple[str, str]:
        readme = root / "final" / "README.md"
        title, desc = "", ""
        if readme.exists():
            lines = [x.strip() for x in readme.read_text(encoding="utf-8").splitlines()]
            for i, x in enumerate(lines):
                if x.startswith("# "):
                    title = x[2:].strip()
                    for y in lines[i + 1:]:
                        if y and not y.startswith(("-", "#")):
                            desc = y
                            break
                        if y.startswith(("-", "#")):
                            break
                    break
        return title or (d.get("brief") or {}).get("prompt", "")[:40] or d["id"], desc

    # ---------------------------------------------------------------- queries
    def get(self, vid: str) -> Video | None:
        return self.refresh().videos.get(vid)

    def works(self) -> list[Video]:
        """One primary video per work, newest first (actor intros last)."""
        vs = [v for v in self.refresh().videos.values() if v.primary]
        return sorted(vs, key=lambda v: (v.work.startswith("actor:"), -v.created))

    def versions(self, work: str) -> list[Video]:
        return sorted([v for v in self.refresh().videos.values() if v.work == work],
                      key=lambda v: (v.length != "60s", v.aspect != "16:9", v.aspect))

    def verticals(self) -> list[Video]:
        return sorted([v for v in self.refresh().videos.values() if v.aspect == "9:16"],
                      key=lambda v: (v.length != "15s", -v.created))

    def names(self) -> dict[str, str]:
        return {h: a.name for h, a in self.refresh().actors.items()}


def _json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


_catalog: Catalog | None = None


def catalog() -> Catalog:
    global _catalog
    if _catalog is None:
        _catalog = Catalog(float(settings().get("site.catalog_ttl_s", 120)))
    return _catalog
