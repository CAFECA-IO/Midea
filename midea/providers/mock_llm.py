"""Deterministic offline planner used when mode == "mock" (no GPU / CI / demos).

It produces structurally valid proposals, scripts and scene plans so every
pipeline can be exercised end-to-end without Qwen running.
"""
from __future__ import annotations

import math
import re
from typing import Any

_TEMPLATES = ["kinetic_text", "neural_net", "bar_chart", "gauge", "timeline", "kpi_board", "line_chart"]


def _topic(prompt: str) -> str:
    m = re.search(r"(?:解釋|介紹|關於|說明|explain(?:ing)?|about)\s*([^，。,.!?！？]+)", prompt, re.I)
    t = (m.group(1) if m else prompt).strip()
    t = re.sub(r"^(一支|一部|一段|的)", "", t)
    t = re.sub(r"(的)?(動畫|影片|短片|紀錄片|video|animation)$", "", t).strip()
    return t[:40] or "主題"


def _is_cjk(s: str) -> bool:
    return bool(re.search(r"[一-鿿]", s))


def answer(task: str, user: str, ctx: dict) -> Any:
    brief = ctx.get("brief", {})
    fn = globals().get(f"_t_{task}")
    if fn is None:
        return {}
    return fn(brief, ctx)


def _t_proposal(brief: dict, ctx: dict) -> dict:
    topic = _topic(brief.get("prompt", ""))
    real = brief.get("real_only")
    renderer = "stock" if real else ("motion" if brief.get("pipeline") in ("animated-explainer", "motion-graphics",
                                                                            "character-animation", "product-3d") else "hybrid")
    return {"title": topic, "logline": f"用 {int(brief.get('duration_s', 60))} 秒講清楚「{topic}」。",
            "audience": "一般大眾", "tone": "清楚、好奇、節奏明快", "style": "flat-modern" if not real else "archival",
            "duration_s": brief.get("duration_s", 60), "aspect": brief.get("aspect", "16:9"),
            "language": brief.get("language", "zh-TW"), "renderer": renderer,
            "music_mood": "documentary piano, warm strings" if real else "uplifting electronic, light pulse",
            "outline": ["開場鉤子", f"{topic}是什麼", "核心原理", "實際例子", "常見誤解", "總結與行動呼籲"],
            "risks": ["(mock) 未經真實模型審稿"]}


def _t_script(brief: dict, ctx: dict) -> dict:
    prop = ctx.get("proposal", {})
    topic = prop.get("title") or _topic(brief.get("prompt", ""))
    total = float(prop.get("duration_s") or brief.get("duration_s", 60))
    outline = prop.get("outline") or ["開場", "主體", "結尾"]
    per = total / len(outline)
    rate = 4.2
    secs = []
    for i, beat in enumerate(outline):
        n = max(8, int(per * rate) - 2)
        base = f"{beat}：讓我們用簡單的方式理解{topic}，一步一步看懂它如何運作。"
        narration = (base * 3)[:n].rstrip("，、") + "。"
        secs.append({"id": f"s{i+1}", "heading": beat, "narration": narration,
                     "on_screen_text": beat, "est_duration_s": round(per, 2)})
    cast = ctx.get("cast") or []
    for i, sec in enumerate(secs):                     # cast members take every other section in their own voice
        if cast and i % 2 == 1:
            sec["speaker"] = cast[(i // 2) % len(cast)]["handle"]
        else:
            sec["speaker"] = "narrator"
    return {"title": topic, "language": brief.get("language", "zh-TW"), "hook": secs[0]["narration"],
            "sections": secs, "cta": "追蹤我們，看更多一分鐘科普。"}


def _t_scene_plan(brief: dict, ctx: dict) -> dict:
    script = ctx.get("script", {})
    prop = ctx.get("proposal", {})
    real = brief.get("real_only") or prop.get("renderer") == "stock"
    motion_only = prop.get("renderer") == "motion"
    scenes = []
    k = 0
    for sec in script.get("sections", []):
        dur = float(sec.get("est_duration_s", 8))
        n = max(1, math.ceil(dur / 7))
        for j in range(n):
            k += 1
            d = round(dur / n, 2)
            text = sec.get("narration", "")
            chunk = text[j * len(text) // n:(j + 1) * len(text) // n]
            if real:
                visual = {"kind": "stock_video" if k % 3 else "stock_image",
                          "query": ["archival science lab", "space telescope", "old film city",
                                    "computer history", "earth from orbit"][k % 5]}
            elif motion_only or k % 3 == 1:
                tpl = _TEMPLATES[k % len(_TEMPLATES)]
                visual = {"kind": "motion", "template": tpl,
                          "params": {"title": sec.get("heading", ""), "text": sec.get("on_screen_text", ""),
                                     "values": [3, 5, 2, 7, 4], "labels": ["A", "B", "C", "D", "E"]}}
            else:
                visual = {"kind": "h3_t2v", "camera": "slow dolly-in",
                          "prompt": f"Cinematic shot illustrating {sec.get('heading','')}, soft volumetric light, "
                                    f"clean modern aesthetic, shallow depth of field"}
            cast = ctx.get("cast") or []
            actors = []
            if cast and not real and not motion_only and visual["kind"].startswith("h3"):
                lead = cast[k % len(cast)]["handle"]
                actors = [lead]
                visual = {"kind": "h3_r2v", "camera": "slow tracking shot",
                          "prompt": f"{lead} walks through a sunlit modern office, glancing at a glowing screen, medium shot"}
            elif cast and motion_only and k % 4 == 2:
                actors = [cast[0]["handle"]]
            if visual["kind"].startswith("h3"):
                d = float(max(4, min(15, round(d))))
            scenes.append({"id": f"sc{k:02d}", "section_id": sec.get("id"), "duration_s": d,
                           "narration": chunk, "on_screen_text": sec.get("on_screen_text", "") if j == 0 else "",
                           "visual": visual,
                           "transition": {"type": "dissolve" if k > 1 else "fade", "duration": 0.4},
                           "sfx": [{"prompt": "soft whoosh transition", "at": 0.0, "duration": 1.0, "gain_db": -12}]
                           if j == 0 and k > 1 else [],
                           "foley": visual["kind"] == "stock_video", "music_cue": "",
                           "actors": actors, "speaker": sec.get("speaker", "")})
    return {"scenes": scenes,
            "music": {"prompt": prop.get("music_mood", "ambient"), "bpm": 96, "instrumental": True},
            "voice": {"description": "(warm, clear documentary narrator)"}}


def _t_adapt(brief: dict, ctx: dict) -> dict:
    ref = ctx.get("reference", {})
    beats = ref.get("structure") or [{"start": 0, "end": 3, "beat": "hook"}, {"start": 3, "end": 10, "beat": "body"}]
    topic = _topic(brief.get("prompt", ""))
    scenes = []
    for i, b in enumerate(beats, 1):
        d = max(1.0, float(b.get("end", 0)) - float(b.get("start", 0)))
        scenes.append({"id": f"sc{i:02d}", "duration_s": round(d, 2),
                       "narration": (f"{topic}，{b.get('beat', '')}")[:max(4, int(d * 3.5))],
                       "on_screen_text": b.get("beat", ""),
                       "visual": {"kind": "motion", "template": "kinetic_text",
                                  "params": {"text": f"{topic} · {b.get('beat', '')}"}} if i % 2 else
                                 {"kind": "h3_t2v", "prompt": f"Vertical close-up, {topic}, {b.get('visual_style', '')}, punchy"},
                       "transition": {"type": "cut", "duration": 0}})
    return {"scenes": scenes, "music": {"prompt": ref.get("music") or "punchy short-form beat", "bpm": 120,
                                        "instrumental": True}, "voice": {}}


def _t_reference(brief: dict, ctx: dict) -> dict:
    cuts = ctx.get("cuts", [])
    dur = ctx.get("duration_s", 30)
    edges = [0.0, *cuts, dur]
    structure = []
    names = ["hook", "setup", "reveal", "proof", "payoff", "cta"]
    for i in range(len(edges) - 1):
        structure.append({"beat": names[min(i, len(names) - 1)], "start": edges[i], "end": edges[i + 1],
                          "purpose": "", "visual_style": "close-up", "text_style": "bold centered captions"})
    pacing = "fast" if (dur / max(1, len(structure))) < 2.5 else "medium"
    return {"pacing": pacing, "hook": "question in first 2s", "structure": structure,
            "style_notes": ["high contrast", "punch-in zooms"], "music": "trending upbeat",
            "caption_style": "word-by-word bold, centered lower third"}


def _t_stock_rank(brief: dict, ctx: dict) -> dict:
    return {"ranking": [c["id"] for c in ctx.get("candidates", [])], "reason": "mock: keep source order"}


def _t_review_frames(brief: dict, ctx: dict) -> dict:
    return {"scenes": [{"id": s, "pass": True, "score_0_10": 8, "issues": []} for s in ctx.get("scene_ids", [])]}
