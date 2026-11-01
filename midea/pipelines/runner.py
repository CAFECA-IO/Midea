"""Stage runner: executes a pipeline manifest with checkpoints, approval gates, cost control and QA.

Stage order for generative pipelines:
  proposal ▸ script ▸ scene_plan ▸ voice ▸ assets ▸ music_sfx ▸ edit ▸ compose ▸ qa ▸ publish
Narration is synthesised *before* picture so every shot is cut to the real voice length
(and SVG characters can lip-sync to it). Gates pause on the storyboard until a human
approves; rejections loop back into the same stage with the reviewer's notes.
"""
from __future__ import annotations

import json
import math
import zlib
import shutil
import threading
import traceback
from pathlib import Path
from typing import Any, Callable

import yaml

from .. import cost as costmod
from .. import prompts, qa
from ..config import settings
from ..gpu import scheduler
from ..log import get_logger
from ..media import ff
from ..project import Project
from ..providers import audio as A
from ..providers import reference as R
from ..providers import stock as S
from ..providers.asr import transcribe
from ..providers.llm import llm
from ..providers.video_h3 import h3
from ..schemas import Brief, Proposal, ReferenceAnalysis, ScenePlan, Script
from ..tools import audio as au
from ..tools import motion_engine as me
from ..tools import subtitles as sub
from ..tools import video as vt

log = get_logger("runner")
DEFS = settings().root / "pipeline_defs"
MAX_REVISIONS = 4


def load_defs() -> dict[str, dict]:
    return {p.stem: yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(DEFS.glob("*.yaml"))}


def route(brief: dict) -> str:
    """Pick a pipeline for pipeline='auto'."""
    p = (brief.get("prompt") or "").lower()
    if brief.get("reference_url"):
        return "reference-remix"
    if brief.get("user_media"):
        return "localization-dub" if any(k in p for k in ("配音", "翻譯", "dub", "translate")) else "clip-factory"
    if brief.get("real_only"):
        return "archival-history" if any(k in p for k in ("歷史", "history", "archival", "二戰", "年代")) else "documentary-montage"
    if any(k in p for k in ("3d", "產品", "product", "轉台")):
        return "product-3d"
    if any(k in p for k in ("角色", "character", "人物動畫")):
        return "character-animation"
    if any(k in p for k in ("動態文字", "文字排版", "typography", "motion graphic")):
        return "motion-graphics"
    if brief.get("aspect") == "9:16" or any(k in p for k in ("shorts", "reels", "tiktok", "短影音")):
        return "shorts-factory"
    if any(k in p for k in ("電影", "cinematic", "短片故事")):
        return "cinematic"
    if any(k in p for k in ("解釋", "科普", "explain", "教學", "動畫")):
        return "animated-explainer"
    return "hybrid"


def dims(aspect: str) -> tuple[int, int]:
    base = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350), "21:9": (1920, 822)}
    w, h = base.get(aspect, (1920, 1080))
    if settings().mode == "mock" and settings().get("render.mock_half_res", True):
        w, h = w // 2 // 2 * 2, h // 2 // 2 * 2
    return w, h


class Runner:
    def __init__(self, project: Project, *, auto_approve: bool = False):
        self.p = project
        d = project.load()
        self.brief = Brief(**d["brief"]).model_dump()
        self.pipe_name = d["pipeline"] if d["pipeline"] != "auto" else route(self.brief)
        if d["pipeline"] == "auto":
            project.update(lambda x: x.__setitem__("pipeline", self.pipe_name))
            project.decide(f"pipeline = {self.pipe_name}", "auto-routed from brief")
        self.pipe = load_defs()[self.pipe_name]
        self.df: dict = self.pipe.get("defaults", {})
        if self.df.get("real_only"):
            self.brief["real_only"] = True
        aspect = self.brief.get("aspect") or self.df.get("aspect", "16:9")
        if aspect == "16:9" and self.df.get("aspect") not in (None, "keep", "16:9") and not d["brief"].get("aspect_locked"):
            aspect = self.df["aspect"]
        self.aspect = aspect
        self.w, self.h = dims(aspect)
        self.fps = 30 if aspect == "9:16" else int(settings().get("render.fps", 24))
        self.auto = auto_approve
        scheduler().on_usage = self._bill

    # ------------------------------------------------------------------ infra
    def _bill(self, service: str, seconds: float) -> None:
        c = costmod.money_for_gpu_seconds(seconds)
        def f(d: dict) -> None:
            d["cost"]["actual"] = round(d["cost"].get("actual", 0) + c, 4)
            d["cost"]["lines"].append({"service": service, "gpu_s": round(seconds, 1), "cost": c})
        self.p.update(f)

    def ctx(self) -> dict:
        return {"brief": self.brief, "pipeline": self.pipe_name, "defaults": self.df,
                "proposal": self.p.stage_data("proposal"), "script": self.p.stage_data("script"),
                "reference": self.p.stage_data("reference_analysis")}

    def ask(self, task: str, system: str, payload: dict, feedback: str = "", **kw) -> Any:
        user = json.dumps(payload, ensure_ascii=False, indent=1)
        if feedback:
            user += f"\n\nREVIEWER FEEDBACK — revise accordingly:\n{feedback}"
        return llm().json(task, system, user, context={**self.ctx(), **payload}, **kw)

    def run(self) -> None:
        try:
            self.p.set_status("running")
            for stage in self.pipe["stages"]:
                if self.p.load()["stages"].get(stage, {}).get("status") == "done":
                    continue
                self._run_stage(stage)
            self.p.set_status("done")
        except RuntimeError as e:
            if self.p.load().get("status") == "qa_failed":
                self.p.emit("error", {"message": str(e)})
                return
            log.error("pipeline failed: %s", e)
            self.p.emit("error", {"message": str(e), "trace": traceback.format_exc()[-3000:]})
            self.p.set_status("failed")
            raise
        except Exception as e:  # noqa: BLE001
            log.error("pipeline failed: %s", e)
            self.p.emit("error", {"message": str(e), "trace": traceback.format_exc()[-3000:]})
            self.p.set_status("failed")
            raise

    def _run_stage(self, stage: str) -> None:
        fn: Callable[[str], Any] = getattr(self, f"st_{stage}")
        feedback = ""
        for rev in range(MAX_REVISIONS + 1):
            self.p.set_status("running", stage)
            self.p.emit("log", {"stage": stage, "message": f"開始 {stage}" + (f"（第 {rev+1} 版）" if rev else "")})
            data = fn(feedback)
            self.p.checkpoint(stage, data, status="review" if stage in self.pipe.get("gates", []) else "done")
            if stage not in self.pipe.get("gates", []) or stage in (settings().get("gates_disabled") or []):
                self.p.checkpoint(stage, data)
                return
            if stage == "publish" and (self.p.stage_data("qa") or {}).get("status") == "fail" and self.auto:
                self.p.checkpoint(stage, data, status="blocked")
                self.p.set_status("qa_failed", stage)
                raise RuntimeError("QA failed — the video was not published. See the QA report on the board.")
            cheap = stage == "scene_plan" and isinstance(data, dict) and \
                (data.get("_estimate") or {}).get("total_cost", 1e9) < float(settings().get("auto_approve_below", 0) or 0)
            rec = self.p.gate(stage, self._summary(stage, data), auto=self.auto or cheap)
            if rec.get("edits"):
                data = self._apply_edits(stage, data, rec["edits"])
            if rec["status"] == "approved":
                self.p.checkpoint(stage, data)
                return
            feedback = rec.get("note", "") or "請重新製作，提升品質。"
            if stage == "assets" and rec.get("edits", {}).get("regenerate"):
                feedback = ""            # targeted regeneration handled in _apply_edits
        raise RuntimeError(f"{stage} rejected {MAX_REVISIONS + 1} times; stopping")

    def _apply_edits(self, stage: str, data: Any, edits: dict) -> Any:
        if stage == "assets" and "regenerate" in edits:
            plan = self.p.stage_data("scene_plan")
            for sid, change in edits["regenerate"].items():
                sc = next(s for s in plan["scenes"] if s["id"] == sid)
                sc["visual"].update(change or {})
                data["scenes"][sid] = self._make_visual(sc, plan, force=True, seed_bump=True)
            self.p.checkpoint("scene_plan", plan)
            return data
        if "data" in edits and isinstance(edits["data"], (dict, list)):     # full JSON edit from the board
            return edits["data"]
        return data

    def _summary(self, stage: str, data: Any) -> dict:
        if stage == "scene_plan":
            return {"scenes": len(data.get("scenes", [])), "estimate": data.get("_estimate"),
                    "budget": data.get("_budget")}
        if stage == "assets":
            return {"scenes": {k: {"thumb": v.get("thumb"), "kind": v.get("kind")} for k, v in data.get("scenes", {}).items()},
                    "estimate": self.p.stage_data("scene_plan", {}).get("_estimate")}
        if stage == "publish":
            return {"qa": self.p.stage_data("qa", {}).get("status"), "file": data.get("final")}
        return {"keys": list(data)[:12] if isinstance(data, dict) else len(data)}

    # ------------------------------------------------------------------ planning stages
    def st_proposal(self, feedback: str) -> dict:
        payload = {"brief": self.brief, "pipeline": self.pipe_name, "pipeline_description": self.pipe.get("description"),
                   "style_defaults": self.df}
        if self.p.stage_data("reference_analysis"):
            payload["reference"] = {k: v for k, v in self.p.stage_data("reference_analysis").items() if k != "keyframes"}
        out = Proposal(**self.ask("proposal", prompts.PROPOSAL, payload, feedback)).model_dump()
        if self.brief.get("real_only"):
            out["renderer"] = "stock"
        out["duration_s"] = self.brief.get("duration_s", out.get("duration_s", 60))
        out["aspect"] = self.aspect
        out.setdefault("music_mood", self.df.get("music_mood"))
        return out

    def st_script(self, feedback: str) -> dict:
        prop = self.p.stage_data("proposal")
        s = Script(**self.ask("script", prompts.SCRIPT, {"brief": self.brief, "proposal": prop}, feedback)).model_dump()
        for sec in s["sections"]:                       # re-estimate from real speech rate
            sec["est_duration_s"] = round(max(sec.get("est_duration_s", 0), A.estimate_speech_seconds(sec["narration"]) + 0.6), 2)
        return s

    def st_reference_analysis(self, feedback: str) -> dict:
        url = self.brief.get("reference_url")
        if not url:
            raise ValueError("reference-remix needs brief.reference_url")
        ref = R.analyze(url, self.p.dir / "reference")
        ReferenceAnalysis(**ref)       # validate
        ref["keyframes"] = [self.p.rel(k) for k in ref.get("keyframes", [])]
        ref["video"] = self.p.rel(ref["video"])
        self.brief["duration_s"] = ref["duration_s"]
        self.p.update(lambda d: d["brief"].__setitem__("duration_s", ref["duration_s"]))
        if ref.get("aspect") and not self.brief.get("aspect_locked"):
            self.aspect = ref["aspect"]
            self.w, self.h = dims(self.aspect)
            self.fps = 30 if self.aspect == "9:16" else self.fps
        return ref

    def st_scene_plan(self, feedback: str) -> dict:
        kinds = self.df.get("visual_kinds", ["h3_t2v", "stock_video", "motion"])
        payload = {"brief": self.brief, "proposal": self.p.stage_data("proposal"), "script": self.p.stage_data("script"),
                   "allowed_visual_kinds": kinds, "pacing_seconds": self.df.get("pacing", [3, 8]),
                   "motion_templates": self.df.get("motion_templates"), "real_only": bool(self.brief.get("real_only"))}
        if self.pipe_name == "reference-remix":
            payload["reference"] = {k: v for k, v in self.p.stage_data("reference_analysis").items() if k != "keyframes"}
            raw = self.ask("adapt", prompts.ADAPT, payload, feedback)
        else:
            raw = self.ask("scene_plan", prompts.SCENE_PLAN, payload, feedback)
        plan = ScenePlan(**raw).model_dump()
        plan["scenes"] = [self._sanitize_scene(sc, kinds) for sc in plan["scenes"]]
        est = costmod.estimate_plan(plan, self.brief)
        spent = self.p.load()["cost"].get("actual", 0)
        budget = costmod.check_budget(est["total_cost"], spent)
        plan["_estimate"], plan["_budget"] = est, budget
        self.p.update(lambda d: d["cost"].__setitem__("estimated", est["total_cost"]))
        if budget["blocked"]:
            raise RuntimeError(budget["message"])
        return plan

    def _sanitize_scene(self, sc: dict, kinds: list[str]) -> dict:
        v = sc["visual"]
        if v["kind"] not in kinds and v["kind"] != "title_card":
            fallback = next((k for k in kinds if k.startswith("stock")), None) if self.brief.get("real_only") else kinds[0]
            self.p.decide(f"{sc['id']}: {v['kind']} → {fallback}", "visual kind not allowed by pipeline")
            v["kind"] = fallback
            if fallback.startswith("stock") and not v.get("query"):
                v["query"] = " ".join(v.get("prompt", sc.get("on_screen_text", "")).split()[:5])
        if v["kind"].startswith("h3"):          # H3 renders 4–15 s; shorter beats are trimmed after generation
            sc["duration_s"] = float(min(15.0, sc["duration_s"]))
        sc["duration_s"] = max(1.5, float(sc["duration_s"]))
        return sc

    # ------------------------------------------------------------------ voice
    def st_voice(self, feedback: str) -> dict:
        plan = self.p.stage_data("scene_plan")
        if self.pipe_name == "localization-dub":
            return self._dub_voice()
        voice = self.brief.get("voice") or plan.get("voice", {}).get("description") or \
            settings().get("services.voxcpm.defaults.voice")
        ref_wav = voice if voice and Path(str(voice)).suffix.lower() in (".wav", ".flac", ".mp3") else None
        out = {}
        for sc in plan["scenes"]:
            if not sc.get("narration", "").strip():
                continue
            f = self.p.path("scenes", sc["id"], "voice.wav")
            if not f.exists() or feedback:
                A.tts(sc["narration"], f, voice=None if ref_wav else voice, reference_wav=ref_wav)
            d = ff.duration(f)
            room = sc["duration_s"] - 0.35
            if self.df.get("lock_timing") and d > room > 0:      # keep the reference's beat timing: speed up ≤1.3×
                g = f.with_name("voice_fit.wav")
                ff.run(["-i", f, "-af", f"atempo={min(1.3, d / room):.3f}", g])
                f, d = g, ff.duration(g)
            out[sc["id"]] = {"file": self.p.rel(f), "duration": round(d, 3)}
            need = d + (0.35 if self.df.get("lock_timing") else 0.6)
            if need > sc["duration_s"]:
                self.p.decide(f"{sc['id']}: duration {sc['duration_s']} → {need:.2f}s", "narration is longer than planned")
                sc["duration_s"] = round(need, 2)
            self.p.emit("progress", {"stage": "voice", "scene": sc["id"]})
        self.p.checkpoint("scene_plan", plan)
        return {"clips": out, "voice": voice}

    # ------------------------------------------------------------------ assets
    def st_assets(self, feedback: str) -> dict:
        if self.pipe_name == "clip-factory":
            return self._clip_assets()
        plan = self.p.stage_data("scene_plan")
        scenes: dict[str, dict] = {}
        for i, sc in enumerate(plan["scenes"]):
            scenes[sc["id"]] = self._make_visual(sc, plan, force=bool(feedback), index=i)
            self.p.emit("progress", {"stage": "assets", "scene": sc["id"], "done": i + 1, "total": len(plan["scenes"])})
            self.p.checkpoint("assets", {"scenes": scenes}, status="running")
        return {"scenes": scenes, "credits": self._credits(scenes)}

    def _credits(self, scenes: dict) -> list[str]:
        out = []
        for s in scenes.values():
            c = s.get("credit")
            if c and c not in out:
                out.append(c)
        return out

    def _make_visual(self, sc: dict, plan: dict, *, force: bool = False, index: int = 0, seed_bump: bool = False) -> dict:
        v, sid, dur = sc["visual"], sc["id"], float(sc["duration_s"])
        d = self.p.path("scenes", sid, "x").parent
        final = d / "visual.mp4"
        if final.exists() and not force:
            return json.loads((d / "visual.json").read_text(encoding="utf-8"))
        kind = v["kind"]
        meta: dict = {"kind": kind}
        raw = d / "raw.mp4"
        if kind.startswith("h3"):
            gen_s = int(min(15, max(4, math.ceil(dur))))
            seed = (zlib.crc32(sid.encode()) % 10_000) + (int(Path(d / "seed").read_text()) + 1 if seed_bump and (d / "seed").exists() else 0)
            (d / "seed").write_text(str(seed))
            prompt = ", ".join(x for x in [v.get("prompt", ""), v.get("camera", ""), self.p.stage_data("proposal", {}).get("style", "")] if x)
            prev = self._prev_h3_scene(plan, index)
            if kind == "h3_i2v" or (self.df.get("continuity") and prev):
                ff_img = d / "first_frame.png"
                src = v.get("params", {}).get("first_frame") or (prev and vt.last_frame(str(self.p.dir / "scenes" / prev / "visual.mp4"), str(ff_img)))
                if src:
                    h3().generate(prompt, raw, seconds=gen_s, aspect=self.aspect, mode="i2v", first_frame=str(src), seed=seed)
                else:
                    h3().generate(prompt, raw, seconds=gen_s, aspect=self.aspect, mode="t2v", seed=seed)
            elif kind == "h3_r2v":
                h3().generate(prompt, raw, seconds=gen_s, aspect=self.aspect, mode="r2v",
                              ref_images=v.get("sources") or self.brief.get("user_media"), seed=seed)
            else:
                h3().generate(prompt, raw, seconds=gen_s, aspect=self.aspect, mode="t2v", seed=seed)
            meta.update(prompt=prompt, seed=seed)
            vt.normalize(str(raw), str(final), self.w, self.h, self.fps, dur, fit="cover", keep_audio=True)
        elif kind.startswith("stock"):
            meta.update(self._stock(sc, d, raw, final, dur))
        elif kind in ("motion", "title_card"):
            tpl = "title_card" if kind == "title_card" else (v.get("template") or "kinetic_text")
            if tpl not in me.TEMPLATES:
                tpl = "kinetic_text"
            params = {"text": sc.get("on_screen_text") or sc.get("narration", "")[:40], "title": sc.get("on_screen_text", ""),
                      **(v.get("params") or {})}
            audio = None
            if tpl == "svg_character" and self.df.get("lipsync"):
                vo = self.p.dir / "scenes" / sid / "voice.wav"
                if vo.exists():
                    env = me.audio_envelope(str(vo), self.fps)
                    params["mouth"] = [0.0] * int(0.25 * self.fps) + env       # voice starts 0.25 s in
            me.render(tpl, raw, seconds=dur, w=self.w, h=self.h, fps=self.fps, params=params,
                      palette=self.df.get("palette", "slate"), audio=audio)
            shutil.copy(raw, final)
            meta.update(template=tpl)
        elif kind == "user_media":
            src = v.get("sources", [None])[0] or self.brief["user_media"][0]
            vt.normalize(src, str(final), self.w, self.h, self.fps, dur, fit=self.df.get("fit", "blur"),
                         start=float(v.get("params", {}).get("start", 0)))
        # finishing per pipeline
        if self.df.get("deinterlace") and kind.startswith("stock"):
            tmp = d / "tmp.mp4"
            from ..tools.registry import call
            call("video.deinterlace", src=str(final), out=str(tmp)); tmp.replace(final)
        if self.df.get("old_film") and kind.startswith("stock"):
            from ..tools.registry import call
            tmp = d / "tmp.mp4"; call("video.old_film", src=str(final), out=str(tmp)); tmp.replace(final)
        thumb = d / "thumb.jpg"
        vt.thumbnail(str(final), str(thumb), at=min(dur / 2, ff.duration(final) / 2))
        meta.update(file=self.p.rel(final), thumb=self.p.rel(thumb), duration=round(ff.duration(final), 3))
        (d / "visual.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        return meta

    def _prev_h3_scene(self, plan: dict, index: int) -> str | None:
        if index <= 0:
            return None
        prev = plan["scenes"][index - 1]
        if prev["visual"]["kind"].startswith("h3") and (self.p.dir / "scenes" / prev["id"] / "visual.mp4").exists():
            return prev["id"]
        return None

    def _stock(self, sc: dict, d: Path, raw: Path, final: Path, dur: float) -> dict:
        v = sc["visual"]
        kind = "image" if v["kind"] == "stock_image" else "video"
        query = v.get("query") or sc.get("on_screen_text") or "archive footage"
        cands = S.search(query, kind, self.df.get("sources"))
        if not cands and kind == "video":
            cands = S.search(query, "image", self.df.get("sources"))
            kind = "image"
        if not cands:
            raise RuntimeError(f"{sc['id']}: no licensed real footage found for '{query}' — edit the query on the board")
        if len(cands) > 1:
            rank = llm().json("stock_rank", prompts.STOCK_RANK, json.dumps(
                {"scene": {"narration": sc.get("narration"), "query": query},
                 "candidates": [{k: c.to_dict()[k] for k in ("id", "title", "description", "source", "license", "width", "height", "duration")} for c in cands[:12]]},
                ensure_ascii=False), context={"candidates": [c.to_dict() for c in cands]})
            order = {cid: i for i, cid in enumerate(rank.get("ranking", []))}
            cands.sort(key=lambda c: order.get(c.id, 999))
        pick = v.get("params", {}).get("pick")
        chosen = next((c for c in cands if c.id == pick), cands[0])
        path = S.download(chosen, settings().root / settings().get("stock.cache_dir", ".cache/stock"))
        if chosen.kind == "image" or Path(path).suffix.lower() in vt.IMG_EXT:
            vt.ken_burns(str(path), str(final), dur, self.w, self.h, self.fps,
                         direction=["in", "out", "left", "right"][zlib.crc32(sc["id"].encode()) % 4])
        else:
            src_d = ff.duration(path)
            start = max(0.0, (src_d - dur) / 3) if src_d > dur else 0.0       # skip slates/leaders at the head
            vt.normalize(str(path), str(final), self.w, self.h, self.fps, dur, fit="cover", keep_audio=True, start=start)
        return {"source": chosen.to_dict(), "credit": chosen.credit, "query": query,
                "alternatives": [c.to_dict() for c in cands[:6]]}

    # ------------------------------------------------------------------ music & sfx
    def st_music_sfx(self, feedback: str) -> dict:
        plan = self.p.stage_data("scene_plan")
        total = self._timeline(plan)["total"]
        out: dict = {"sfx": [], "foley": {}}
        if self.brief.get("music", True) and self.df.get("music", True):
            m = plan.get("music", {})
            prompt = m.get("prompt") or self.p.stage_data("proposal", {}).get("music_mood") or self.df.get("music_mood", "ambient")
            f = self.p.path("audio", "music.wav")
            A.music(prompt, total + 1, f, bpm=m.get("bpm"), instrumental=m.get("instrumental", True))
            out["music"] = {"file": self.p.rel(f), "prompt": prompt, "bpm": m.get("bpm")}
        tl = self._timeline(plan)
        assets = self.p.stage_data("assets", {}).get("scenes", {})
        for sc in plan["scenes"]:
            start = tl["starts"][sc["id"]]
            for j, fx in enumerate(sc.get("sfx", [])):
                f = self.p.path("scenes", sc["id"], f"sfx_{j}.wav")
                A.sfx(fx["prompt"], fx.get("duration", 1.5), f)
                out["sfx"].append({"path": str(f), "at": start + float(fx.get("at", 0)), "gain_db": fx.get("gain_db", -8)})
            want_foley = (sc.get("foley") or self.df.get("foley")) and sc["visual"]["kind"] in ("stock_video", "user_media")
            if want_foley and sc["id"] in assets:
                f = self.p.path("scenes", sc["id"], "foley.wav")
                A.foley(self.p.dir / assets[sc["id"]]["file"], sc.get("visual", {}).get("query", ""), f)
                out["foley"][sc["id"]] = str(f)
                out["sfx"].append({"path": str(f), "at": start, "gain_db": -14})
        return out

    # ------------------------------------------------------------------ edit
    def _timeline(self, plan: dict) -> dict:
        starts, t = {}, 0.0
        trans = []
        for i, sc in enumerate(plan["scenes"]):
            tr = sc.get("transition") or {}
            if i == 0:
                d = 0.0
            else:
                d = 0.0 if tr.get("type") == "cut" or float(tr.get("duration", 0.4)) < 2.0 / self.fps else float(tr.get("duration", 0.4))
                d = min(d, float(sc["duration_s"]) / 2, float(plan["scenes"][i - 1]["duration_s"]) / 2)
            t -= d
            starts[sc["id"]] = round(t, 3)
            t += float(sc["duration_s"])
            trans.append(tr)
        return {"starts": starts, "total": round(t, 3), "transitions": trans[1:]}

    def st_edit(self, feedback: str) -> dict:
        if self.pipe_name == "clip-factory":
            return self._clip_edit()
        plan = self.p.stage_data("scene_plan")
        assets = self.p.stage_data("assets")["scenes"]
        voice = (self.p.stage_data("voice") or {}).get("clips", {})
        clips, trans = [], []
        # re-conform visuals whose scene grew after narration timing
        for sc in plan["scenes"]:
            f = self.p.dir / assets[sc["id"]]["file"]
            if ff.duration(f) + 0.05 < sc["duration_s"]:
                g = f.with_name("visual_fit.mp4")
                vt.normalize(str(f), str(g), self.w, self.h, self.fps, sc["duration_s"])
                f = g
            clips.append(str(f))
        tl = self._timeline(plan)
        credits_s = 0.0
        credits = (self.p.stage_data("assets") or {}).get("credits") or []
        if self.df.get("credits") and credits:
            cf = self.p.path("edit", "credits.mp4")
            vt.scroll_credits(["影像來源 / Footage credits", ""] + credits, str(cf), seconds=min(12, 4 + len(credits)),
                              w=self.w, h=self.h)
            clips.append(str(cf))
            credits_s = ff.duration(cf) - 0.5
            plan["scenes"].append({"id": "credits", "duration_s": ff.duration(cf), "transition": {"type": "fade", "duration": 0.5}})
            tl = self._timeline(plan)
            plan["scenes"].pop()
        picture = self.p.path("edit", "picture.mp4")
        vt.xfade_chain(clips, str(picture), tl["transitions"], fps=self.fps)
        total = ff.duration(picture)
        # narration stem + subtitle spans
        vclips, spans = [], []
        for sc in plan["scenes"]:
            if sc["id"] in voice:
                at = tl["starts"][sc["id"]] + 0.25
                vclips.append({"path": str(self.p.dir / voice[sc["id"]]["file"]), "at": at, "gain_db": 0})
                spans.append({"start": at, "end": at + voice[sc["id"]]["duration"], "text": sc["narration"], "scene": sc["id"]})
        vo = self.p.path("audio", "voice_stem.wav")
        au.place(vclips, str(vo), total)
        return {"picture": self.p.rel(picture), "voice_stem": self.p.rel(vo), "spans": spans, "total": total,
                "starts": tl["starts"], "credits_s": round(credits_s, 3)}

    # ------------------------------------------------------------------ compose
    def st_compose(self, feedback: str) -> dict:
        if self.pipe_name == "localization-dub":
            return self._dub_compose()
        if self.pipe_name == "clip-factory":
            return self._clip_compose()
        ed = self.p.stage_data("edit")
        ms = self.p.stage_data("music_sfx") or {}
        picture = self.p.dir / ed["picture"]
        total = ed["total"]
        # ambience: native H3 audio / stock sound from the picture, kept low under narration
        amb = self.p.path("audio", "ambience.wav")
        vt.extract_audio(str(picture), str(amb))
        fx = self.p.path("audio", "fx_stem.wav")
        au.place([{"path": str(amb), "at": 0, "gain_db": -16}] + ms.get("sfx", []), str(fx), total)
        music = self.p.dir / ms["music"]["file"] if ms.get("music") else None
        mix = self.p.path("audio", "mix.wav")
        voice = self.p.dir / ed["voice_stem"]
        if music:
            au.duck_mix(str(voice), str(music), str(mix), sfx=str(fx), music_db=-8, total=total)
        else:
            au.place([{"path": str(voice), "at": 0}, {"path": str(fx), "at": 0}], str(mix), total)
        return self._finish(picture, mix, ed["spans"], total)

    def _finish(self, picture: Path, mix: Path, spans: list[dict], total: float) -> dict:
        # loudness → mux → grade → subtitles → delivery encode
        target = float(settings().get("qa.loudness_lufs", -14))
        mixn = self.p.path("audio", "mix_norm.wav")
        au.loudnorm(str(mix), str(mixn), target_lufs=target, true_peak=float(settings().get("qa.true_peak_db", -1.0)) - 0.5)
        av = self.p.path("compose", "av.mp4")
        vt.replace_audio(str(picture), str(mixn), str(av))
        graded = self.p.path("compose", "graded.mp4")
        vt.color_grade(str(av), str(graded), self.df.get("grade", "neutral"))
        cues = sub.cues_from_spans(spans) if self.brief.get("subtitles", True) else []
        words = []
        if cues and settings().mode != "mock":
            words = [w for s in transcribe(mixn, self.brief.get("language"))["segments"] for w in s["words"]]
            cues = sub.align_to_words(cues, words)
        srt = self.p.path("compose", "subtitles.srt")
        ass = self.p.path("compose", "subtitles.ass")
        out = graded
        if cues:
            sub.write_srt(cues, str(srt))
            sub.write_vtt(cues, str(srt.with_suffix(".vtt")))
            sub.write_ass(cues, str(ass), self.w, self.h, style=self.df.get("subtitle_style", "clean"),
                          karaoke=bool(self.df.get("karaoke")))
            if self.brief.get("burn_subtitles", True):
                burned = self.p.path("compose", "subbed.mp4")
                sub.burn(str(graded), str(ass), str(burned))
                out = burned
        final = self.p.path("compose", "master.mp4")
        ff.run(["-i", out, "-c:v", "libx264", "-crf", str(settings().get("render.crf", 18)), "-preset",
                settings().get("render.preset", "medium"), "-profile:v", "high", "-pix_fmt", "yuv420p",
                "-r", str(self.fps), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart", final])
        return {"master": self.p.rel(final), "srt": self.p.rel(srt) if cues else None, "ass": self.p.rel(ass) if cues else None,
                "cues": cues, "spans": spans, "words": words[:5000], "loudness_target": target}

    # ------------------------------------------------------------------ QA & publish
    def st_qa(self, feedback: str) -> dict:
        comp = self.p.stage_data("compose")
        outs = comp.get("outputs") or [comp]
        reports = []
        for c in outs:
            master = str(self.p.dir / c["master"])
            vision = None
            if settings().mode != "mock":
                plan = self.p.stage_data("scene_plan") or {}
                def vision(frames: list[str], plan=plan) -> dict:
                    r = llm().json("review_frames", prompts.REVIEW_FRAMES,
                                   json.dumps({"scenes": [{k: s.get(k) for k in ("id", "narration", "visual")} for s in plan.get("scenes", [])]},
                                              ensure_ascii=False), images=frames)
                    bad = [s for s in r.get("scenes", []) if not s.get("pass", True)]
                    return {"check": "vision", "status": "warn" if bad else "pass",
                            "message": "; ".join(f"{s['id']}: {', '.join(s.get('issues', []))}" for s in bad) or "frames match the plan",
                            "evidence": r}
            w, h = (self.w, self.h) if not c.get("size") else c["size"]
            ref = self.p.stage_data("reference_analysis") or {}
            target = c.get("promised_duration") or (ref.get("duration_s") if ref else None) or \
                (self.brief.get("duration_s") if self.pipe_name not in ("clip-factory", "localization-dub") else None)
            promise = {"duration_s": target, "extra_s": (self.p.stage_data("edit") or {}).get("credits_s", 0),
                       "aspect": c.get("aspect", self.aspect if self.aspect != "keep" else None),
                       "subtitles": bool(self.brief.get("subtitles", True)) and bool(c.get("spans"))}
            rep = qa.run_all(master, promise=promise, w=w, h=h, fps=c.get("fps", self.fps),
                             workdir=self.p.dir / "qa" / Path(c["master"]).stem,
                             cues=c.get("cues") or None, narration_spans=c.get("spans"), words=c.get("words"), vision=vision)
            # one automatic repair pass for audio level problems
            if any(r["check"] == "loudness" and r["status"] == "fail" for r in rep["results"]):
                fixed = Path(master).with_name("master_fixed.mp4")
                au.loudnorm(master, str(fixed), target_lufs=float(settings().get("qa.loudness_lufs", -14)), video=True)
                fixed.replace(master)
                rep = qa.run_all(master, promise=promise, w=w, h=h, fps=c.get("fps", self.fps),
                                 workdir=self.p.dir / "qa" / Path(c["master"]).stem, cues=c.get("cues") or None,
                                 narration_spans=c.get("spans"), words=c.get("words"))
                rep["auto_fixed"] = ["loudness"]
            for r in rep["results"]:
                for k in ("frames",):
                    if k in r.get("evidence", {}):
                        r["evidence"][k] = [self.p.rel(x) for x in r["evidence"][k]]
                r["evidence"].pop("probe", None) if r["check"] != "container" else None
            rep["file"] = self.p.rel(master)
            reports.append(rep)
        status = "fail" if any(r["status"] == "fail" for r in reports) else "warn" if any(r["status"] == "warn" for r in reports) else "pass"
        if status == "fail":
            self.p.emit("log", {"stage": "qa", "message": "QA 未通過：成片不會標記為完成，請在看板查看報告"})
        return {"status": status, "reports": reports}

    def st_publish(self, feedback: str) -> dict:
        qa_rep = self.p.stage_data("qa")
        if qa_rep["status"] == "fail" and not feedback:
            self.p.emit("log", {"stage": "publish", "message": "QA fail — 需在看板上明確覆核才能發佈"})
        comp = self.p.stage_data("compose")
        outs = comp.get("outputs") or [comp]
        title = (self.p.stage_data("proposal") or {}).get("title") or self.p.id
        safe = "".join(ch for ch in title if ch.isalnum() or ch in " -_（）()").strip()[:60] or "midea"
        deliver = []
        for i, c in enumerate(outs):
            name = f"{safe}{'' if len(outs) == 1 else f'_{i+1}'}"
            dst = self.p.path("final", f"{name}.mp4")
            shutil.copy(self.p.dir / c["master"], dst)
            item = {"video": self.p.rel(dst)}
            for k in ("srt", "ass"):
                if c.get(k):
                    t = self.p.path("final", f"{name}.{k}")
                    shutil.copy(self.p.dir / c[k], t)
                    item[k] = self.p.rel(t)
            th = self.p.path("final", f"{name}.jpg")
            vt.thumbnail(str(dst), str(th))
            item["thumbnail"] = self.p.rel(th)
            deliver.append(item)
        credits = (self.p.stage_data("assets") or {}).get("credits") or []
        d = self.p.load()
        md = [f"# {title}", "", (self.p.stage_data("proposal") or {}).get("logline", ""), "",
              f"- Pipeline: {self.pipe_name}", f"- QA: {qa_rep['status']}",
              f"- 預估成本: {d['cost'].get('estimated', 0):.2f} / 實際: {d['cost'].get('actual', 0):.2f} {settings().get('gpu.currency')}",
              "", "## Credits", *[f"- {c}" for c in credits],
              "", "## Models", "- Qwen3.8-Flash-Next · MiniMax H3 · VoxCPM2 · ACE-Step 1.5 · HunyuanVideo-Foley · Stable Audio Open"]
        if any(s["visual"]["kind"].startswith("h3") for s in (self.p.stage_data("scene_plan") or {}).get("scenes", [])):
            md.append("- 本片含 MiniMax H3 生成畫面：依 MiniMax H3 Community License 標示來源。")
        self.p.path("final", "README.md").write_text("\n".join(md), encoding="utf-8")
        self.p.update(lambda x: x.__setitem__("deliverables", {"items": deliver, "readme": "final/README.md"}))
        return {"final": deliver[0]["video"] if deliver else None, "items": deliver}

    # ------------------------------------------------------------------ repurpose pipelines
    def st_ingest(self, feedback: str) -> dict:
        media = self.brief.get("user_media") or []
        if not media:
            raise ValueError("this pipeline needs brief.user_media (a video file path)")
        src = Path(media[0]).expanduser()
        dst = self.p.path("ingest", "source" + src.suffix.lower())
        if not dst.exists():
            shutil.copy(src, dst)
        from ..tools.analysis import probe
        info = probe(str(dst))
        if self.aspect == "keep" and info.get("video"):
            self.w, self.h = info["video"]["width"] // 2 * 2, info["video"]["height"] // 2 * 2
        return {"file": self.p.rel(dst), "probe": info}

    def st_transcribe(self, feedback: str) -> dict:
        src = self.p.dir / self.p.stage_data("ingest")["file"]
        tr = transcribe(src, None)
        if settings().mode == "mock" and not tr["segments"]:
            d = ff.duration(src)
            tr["segments"] = [{"start": t, "end": min(d, t + 4.5), "text": f"（示範字幕 {i+1}）這是一段測試語音內容。",
                               "words": []} for i, t in enumerate(range(0, int(d), 5))]
            tr["text"] = " ".join(s["text"] for s in tr["segments"])
        return tr

    def st_highlights(self, feedback: str) -> dict:
        tr = self.p.stage_data("transcribe")
        lo, hi = self.df.get("pacing", [15, 60])
        segs = [{"i": i, "start": round(s["start"], 2), "end": round(s["end"], 2), "text": s["text"]} for i, s in enumerate(tr["segments"])]
        if settings().mode == "mock":
            end = segs[-1]["end"] if segs else 20
            return {"clips": [{"start": 0.0, "end": min(end, float(hi)), "title": "精華 1", "hook": segs[0]["text"] if segs else ""}]}
        r = llm().json("highlights", prompts.DIRECTOR + f"""
Task: pick the 1–5 most shareable self-contained moments for vertical shorts, each {lo}–{hi} s,
starting on a strong hook and ending on a complete thought. JSON {{clips:[{{start,end,title,hook,reason}}]}}.""",
                       json.dumps({"segments": segs, "feedback": feedback}, ensure_ascii=False))
        return r

    def _clip_assets(self) -> dict:
        src = self.p.dir / self.p.stage_data("ingest")["file"]
        scenes = {}
        for i, c in enumerate(self.p.stage_data("highlights")["clips"]):
            sid = f"clip{i+1:02d}"
            out = self.p.path("scenes", sid, "visual.mp4")
            vt.normalize(str(src), str(out), self.w, self.h, self.fps, float(c["end"]) - float(c["start"]), fit="blur",
                         start=float(c["start"]))
            th = self.p.path("scenes", sid, "thumb.jpg")
            vt.thumbnail(str(out), str(th), at=1.0)
            scenes[sid] = {"kind": "user_media", "file": self.p.rel(out), "thumb": self.p.rel(th), **c}
        return {"scenes": scenes}

    def _clip_edit(self) -> dict:
        tr = self.p.stage_data("transcribe")
        out = []
        for sid, s in self.p.stage_data("assets")["scenes"].items():
            spans = [{"start": max(0, seg["start"] - s["start"]), "end": min(s["end"], seg["end"]) - s["start"], "text": seg["text"]}
                     for seg in tr["segments"] if seg["end"] > s["start"] and seg["start"] < s["end"]]
            out.append({"id": sid, "file": s["file"], "spans": spans, "duration": float(s["end"]) - float(s["start"])})
        return {"clips": out}

    def _clip_compose(self) -> dict:
        outputs = []
        for c in self.p.stage_data("edit")["clips"]:
            pic = self.p.dir / c["file"]
            mix = self.p.path("audio", f"{c['id']}_mix.wav")
            vt.extract_audio(str(pic), str(mix))
            sub_dir = self.p.dir / "compose"
            r = self._finish(pic, mix, c["spans"], c["duration"])
            for k in ("master", "srt", "ass"):
                if r.get(k):
                    src = self.p.dir / r[k]
                    dst = sub_dir / f"{c['id']}_{Path(r[k]).name}"
                    shutil.move(src, dst)
                    r[k] = self.p.rel(dst)
            r["promised_duration"] = c["duration"]
            outputs.append(r)
        return {"outputs": outputs}

    def st_translate(self, feedback: str) -> dict:
        tr = self.p.stage_data("transcribe")
        lang = self.brief.get("language", "zh-TW")
        segs = [{"i": i, "start": s["start"], "end": s["end"], "text": s["text"]} for i, s in enumerate(tr["segments"])]
        if settings().mode == "mock":
            return {"language": lang, "segments": [{**s, "translation": f"[{lang}] {s['text']}"} for s in segs]}
        r = llm().json("translate", f"""You are a professional dubbing translator. Translate each segment into {lang}.
Each translation must be speakable within the segment's duration (≈4.2 CJK chars/s or 2.5 words/s); shorten
wording rather than run long. Keep names and terms consistent. JSON {{segments:[{{i, translation}}]}}.""",
                       json.dumps({"segments": segs, "feedback": feedback}, ensure_ascii=False))
        by_i = {s["i"]: s["translation"] for s in r.get("segments", [])}
        return {"language": lang, "segments": [{**s, "translation": by_i.get(s["i"], s["text"])} for s in segs]}

    def _dub_voice(self) -> dict:
        src = self.p.dir / self.p.stage_data("ingest")["file"]
        segs = self.p.stage_data("translate")["segments"]
        ref = self.p.path("audio", "speaker_ref.wav")
        if not ref.exists() and segs:                     # 12 s reference from the first speech for voice cloning
            s0 = segs[0]["start"]
            ff.run(["-ss", f"{s0:.2f}", "-t", "12", "-i", src, "-vn", "-ac", "1", "-ar", "48000", ref])
        clips = {}
        for s in segs:
            f = self.p.path("dub", f"seg_{s['i']:04d}.wav")
            A.tts(s["translation"], f, reference_wav=str(ref) if self.df.get("voice_clone") else None)
            room = s["end"] - s["start"]
            d = ff.duration(f)
            if d > room + 0.15:                            # time-fit with atempo (max 1.35×) to keep sync
                g = f.with_name(f.stem + "_fit.wav")
                ff.run(["-i", f, "-af", f"atempo={min(1.35, d / room):.3f}", g])
                f = g
            clips[str(s["i"])] = {"file": self.p.rel(f), "start": s["start"], "end": s["end"], "duration": ff.duration(f)}
        return {"clips": clips}

    def _dub_compose(self) -> dict:
        src = self.p.dir / self.p.stage_data("ingest")["file"]
        total = ff.duration(src)
        clips = self.p.stage_data("voice")["clips"]
        segs = self.p.stage_data("translate")["segments"]
        vo = self.p.path("audio", "dub_stem.wav")
        au.place([{"path": str(self.p.dir / c["file"]), "at": c["start"]} for c in clips.values()], str(vo), total)
        orig = self.p.path("audio", "orig.wav")
        vt.extract_audio(str(src), str(orig))
        mix = self.p.path("audio", "mix.wav")
        au.duck_mix(str(vo), str(orig), str(mix), music_db=-12, duck_ratio=20, total=total)
        pic = self.p.path("compose", "picture.mp4")
        info = ff.video_stream(src) or {}
        self.w, self.h = int(info.get("width", self.w)) // 2 * 2, int(info.get("height", self.h)) // 2 * 2
        n, dd = (info.get("avg_frame_rate") or "24/1").split("/")
        self.fps = round(float(n) / float(dd)) if float(dd) else 24
        vt.normalize(str(src), str(pic), self.w, self.h, self.fps, total, keep_audio=False)
        spans = [{"start": s["start"], "end": s["end"], "text": s["translation"]} for s in segs]
        r = self._finish(pic, mix, spans, total)
        r.update(size=(self.w, self.h), fps=self.fps, aspect=None, promised_duration=total)
        return r


def run_async(project: Project, auto_approve: bool = False) -> threading.Thread:
    t = threading.Thread(target=lambda: Runner(project, auto_approve=auto_approve).run(), daemon=True,
                         name=f"run-{project.id}")
    t.start()
    return t
