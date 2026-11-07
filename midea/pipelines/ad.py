"""60-second ad pipeline (`ad-60`): actors + a product URL → strategy, copy, storyboard and six deliverables.

  product ◆ ▸ tryon ◆ ▸ concepts ◆ ▸ copy ◆ ▸ storyboard ◆ ▸ voice ▸ assets ◆ ▸ music_sfx ▸ edit ▸ compose
          ▸ versions ▸ qa ▸ publish ◆

* product    — page → JSON-LD / OG / text → grounded fact table (each fact quotes the page), cut-outs, colours.
               Demo / not-for-sale prices are never used.
* tryon      — wearable products: Qwen-Image-Edit dresses the lead actor in the product (front / side / headshot);
               these photos replace the actor's default look for the whole ad.
* concepts   — three creative directions (idea, slogan, keywords, 5-colour palette, lighting, music, 4 mood images)
               each with a 10-second motion preview (two H3 shots + an ACE-Step sketch). The reviewer picks one.
* copy       — headline, sub, CTA, supers, lines per beat, social posts; every claim must cite a fact id
               (claims check: unknown facts, numbers not on the page, prices, therapeutic wording).
* storyboard — shot list with camera language + one keyframe per shot (Qwen-Image-Edit composite of the actors and
               the product). Approved keyframes become the first frame of each H3 shot (what you see is what you get).
* versions   — 60 s and 15 s cut-downs in 16:9 / 9:16 / 1:1. 9:16 is "hybrid": a shot is cropped from 16:9 only when
               the crop keeps the people and has enough pixels, otherwise it is redrawn and regenerated at 9:16.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import zlib
from pathlib import Path
from typing import Any

from .. import actors as AC
from .. import qa
from ..config import settings
from ..log import get_logger
from ..media import ff
from ..providers import audio as A
from ..providers import product as PR
from ..providers.llm import llm
from ..tools import motion_engine as me
from ..tools import video as vt
from .runner import Runner, cast_prompt, dims

log = get_logger("ad")

BEATS = ["hook", "problem", "reveal", "demo", "emotion", "cta"]
BEAT_ZH = {"hook": "鉤子", "problem": "痛點", "reveal": "商品登場", "demo": "賣點示範", "emotion": "情感", "cta": "CTA"}
RISKY = re.compile(r"(cure|cures|treat|heal|prevent[s]? disease|anti[- ]?inflamm|clinically|medical|guarantee[d]?|"
                   r"100%|best in the world|#1|治療|治癒|根治|療效|消炎|抗發炎|醫療級|保證|第一名|最有效|永久)", re.I)
ASPECTS = ["16:9", "9:16", "1:1"]

# Ad styles. "standard" is the default commercial grammar; "fashion" is the luxury fashion-film grammar
# (grand unrelated landscape, unhurried people, symbolic inserts, late product reveal, sparse low narration).
MUSIC_GENRES = {
    "classical": "slow classical — solo cello, strings or piano, 60–76 bpm, sparse, reverent",
    "country": "slow acoustic country / folk — fingerpicked guitar, fiddle or pedal steel, 66–80 bpm, warm and unhurried",
}
STYLES: dict[str, dict] = {
    "standard": {"label": "標準商業廣告"},
    "fashion": {
        "label": "時尚大片",
        "dialogue": False,                 # nobody speaks on camera; only a narrator
        "max_lines": 6, "max_words": 9,    # sparse narration
        "music": ["classical", "country"],
        "voice": "(a deep, low, calm mature male narrator, speaking slowly and softly, with long pauses)",
        "shot_min": 1.4, "shot_max": 6.0, "min_shots": 15,
        "product_min": 0.25,               # the product appears late on purpose
        "df": {"grade": "fashion_film", "subtitle_style": "clean", "ambience_db": -24, "music_db": -3,
               "voice_pitch": 0.94},           # narrator: asetrate one semitone lower and 6 % slower
        "endcard": "minimal",
        "concepts": """STYLE — luxury fashion film. All three directions use this grammar but differ in place and symbol:
- a grand, quiet landscape that has nothing to do with the product's everyday use (steppe, salt flat, dunes, sea cliffs,
  misty lake, alpine meadow …) — the place lends the product its price;
- people are unhurried: they stand, pause, turn back, look away; never selling, never smiling at the camera;
- one symbolic animal or object that suggests heritage or freedom (no real brand marks or logos);
- the product appears late, then is treated like jewellery (macro, backlight, shallow focus, an unexpected placement);
- low-saturation palette where the costume colour is complementary to the landscape; overcast soft light or golden-hour backlight;
- "music": {music} — instrumental, slow, sparse, no drums;
- "slogan": a two-part parallel phrase (e.g. "Travel light. Arrive lighter.") — poetic, not a sales line.""",
        "copy": """You are the copywriter of a luxury fashion film. Write the copy and beat outline for a {length:.0f}-second
film in {lang}. NOBODY SPEAKS ON CAMERA: every line has speaker "narrator". The narration is SPARSE and SLOW: {max_lines}
lines at most in the whole film, each ≤ {max_words} words (English) / 14 characters (Chinese), aphoristic, calm, never a
sales pitch; leave whole beats silent (lines:[]) and at least 6 s between lines. RULES: every product claim must cite fact
ids from `facts` (claims:[{{"text","fact_ids"}}]); never mention materials, sizes, performance, prices, stock,
availability, sample/demo status or ordering unless a fact says so; no superlatives; obey banned_words.
Beats and timing: hook 0–8 s (the place, the person tiny in it); problem 8–20 s (the person: unhurried, pausing, turning
back — no problem is stated); reveal 20–27 s (the product's first close-up, around 40 % of the film); demo 27–44 s
(ritual: an unusual pose, the product somewhere unexpected, short nature inserts); emotion 44–53 s (the person small on a
vast horizon); cta 53–{length:.0f} s (product macro + slogan couplet, then the brand card).
"supers": 2–3 short parallel couplets shown as wide-spaced titles (the last one is the slogan); "headline" = the slogan;
"cta" = a quiet line such as the brand site name (no "buy now").
Return JSON {{"headline","sub","cta","url_label","supers":[{{"beat","text"}}],
 "outline":[{{"beat": one of {beats}, "start","end","purpose","lines":[{{"speaker":"narrator","text"}}]}}],
 "claims":[{{"text","fact_ids":[..]}}], "social":[3 post captions], "hashtags":[..]}}""",
        "board": """STYLE — luxury fashion film (follow strictly):
- 15–20 shots; durations 1.5–6 s; most shots static or a slow push-in; long-lens tracking for any walking/riding.
- Shot sizes are POLARISED: ECU/CU details or WS/EWS landscapes; at most 2 MS/MWS shots in the whole film.
- At least 3 "insert" shots of 1.5–2 s with NO people and NO product: water, wind in grass, clouds, an animal's eye,
  wind lifting a fabric edge — set "actors":[] and "product_visible": false.
- People never hurry: standing still, a pause mid-walk, turning back over the shoulder, back to camera, faces often cropped
  at the eyes; nobody talks (mouths closed), nobody smiles at the camera — except ONE sudden, unexplained look back.
- ONE low-angle wide-lens (16–24mm) forced-perspective shot with the product huge in the foreground.
- ONE surreal placement of the product (floating in the air, resting on the symbolic animal, on a rock in the water …).
- The product's first clear close-up is at ~40 % of the run time; before that it is only seen far away or partially.
- One EWS where the person is a tiny figure on the horizon (sky ≥ 2/3 of the frame).
- The last shot before the end card is a product macro: very shallow depth of field, backlight, rack focus to the landscape.
- Light: overcast soft light or golden-hour backlight; low saturation; costume colour complementary to the landscape.
- Transitions are cuts (one slow fade at most). The end card is 3–4 s.
- Lines (narration only, speaker "narrator") sit on wide or insert shots, never on a close-up of a face.""",
    },
}


def _j(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False)


class AdRunner(Runner):
    """Ad production on top of the generic stage runner (gates, checkpoints, voice, edit, compose, QA)."""

    def __init__(self, project, *, auto_approve: bool = False):
        super().__init__(project, auto_approve=auto_approve)
        self.df = {**self.df}
        self.lang = self.brief.get("language") or "en"
        self.sub_langs = self.brief.get("subtitle_languages") or [self.lang]
        self.formats = [a for a in (self.brief.get("formats") or ASPECTS) if a in ASPECTS]
        self.length = float(self.brief.get("duration_s") or 60)
        self.style_id = self.brief.get("style") if self.brief.get("style") in STYLES else "standard"
        self.style = STYLES[self.style_id]
        self.df.update(self.style.get("df") or {})
        chosen = self._concept()
        if chosen and chosen.get("palette_theme"):
            self.df["palette"] = chosen["palette_theme"]

    # ------------------------------------------------------------------ helpers
    def lead(self) -> AC.Actor | None:
        c = self.cast()
        return c[0] if c else None

    def _concept(self) -> dict | None:
        c = self.p.stage_data("concepts") or {}
        return next((x for x in c.get("concepts", []) if x.get("id") == c.get("chosen")), None)

    def _facts(self) -> dict:
        return (self.p.stage_data("product") or {}).get("fact_table") or {}

    def _creative_facts(self) -> list[dict]:
        """Facts the creative may use: page notices (sample / demo / not for sale) and unusable prices are left out."""
        price_ok = bool(((self.p.stage_data("product") or {}).get("price") or {}).get("display"))
        return [f for f in self._facts().get("facts", [])
                if not PR.NOT_FOR_SALE.search(f"{f.get('fact', '')} {f.get('source', '')}")
                and (f.get("kind") != "price" or price_ok)]

    def _product_img(self, cut: bool = True) -> Path | None:
        prod = self.p.stage_data("product") or {}
        for im in prod.get("images", []):
            f = im.get("cutout") if cut and im.get("cutout") else im.get("file")
            if f and (self.p.dir / "product" / f).exists():
                return self.p.dir / "product" / f
        return None

    def _tryon_refs(self, aid: str) -> list[str]:
        t = self.p.stage_data("tryon") or {}
        if t.get("actor") != aid:
            return []
        by = {v["view"]: self.p.dir / v["file"] for v in t.get("views", []) if (self.p.dir / v["file"]).exists()}
        return [str(by[k]) for k in ("headshot", "full_front", "full_side") if k in by]

    def _refs(self, a: AC.Actor) -> list[str]:
        return self._tryon_refs(a.id) or AC.ref_images(a)

    def _cast_text(self) -> list[dict]:
        out = []
        for i, a in enumerate(self.cast()):
            b = AC.bible(a)
            b["role"] = "lead" if i == 0 else "partner"
            out.append(b)
        return out

    def _music_rule(self) -> str:
        """Allowed music genres: brief.music_genre, else the style's list (A, B, C alternate between them)."""
        want = self.brief.get("music_genre")
        genres = [want] if want in MUSIC_GENRES else (self.style.get("music") or [])
        if not genres:
            return "genre, tempo, instruments"
        if len(genres) == 1:
            return MUSIC_GENRES[genres[0]]
        return "; ".join(f"direction {'ABC'[i]}: {MUSIC_GENRES[genres[i % len(genres)]]}" for i in range(3))

    def _music_prompt(self, concept: dict) -> str:
        m = str(concept.get("music") or "").strip()
        want = self.brief.get("music_genre")
        genres = [want] if want in MUSIC_GENRES else (self.style.get("music") or [])
        if genres and not any(g in m.lower() for g in genres):
            m = MUSIC_GENRES[genres["ABC".find(str(concept.get("id", "A"))[:1]) % len(genres)]] + (f"; {m}" if m else "")
        return (m or "uplifting instrumental") + (", instrumental, no vocals, no drums" if genres else "")

    # ------------------------------------------------------------------ 1. product
    def st_product(self, feedback: str) -> dict:
        url = self.brief.get("product_url")
        if not url:
            raise ValueError("ad-60 needs brief.product_url")
        d = self.p.dir / "product"
        data = PR.ingest(url, d)
        if not data.get("images"):
            raise RuntimeError("找不到商品圖片：請在看板上傳商品照片後重試")
        ft = data["fact_table"]
        ft["banned"] = self.brief.get("banned_words") or []
        data["summary"] = {"facts": len(ft.get("facts", [])), "verified": sum(1 for f in ft.get("facts", []) if f.get("verified")),
                           "type": ft.get("product_type"), "price_shown": data["price"]["display"]}
        if data["price"].get("reason"):
            self.p.decide("price is not used", data["price"]["reason"])
        return data

    # ------------------------------------------------------------------ 2. try-on (wearables)
    TRYON_VIEWS = {
        "full_front": ("full_front", "Full-length studio photo, standing facing the camera, head to shoes visible."),
        "headshot": ("headshot", "Head-and-shoulders studio portrait facing the camera, the garment collar and front visible."),
        "full_side": ("full_side", "Full-length strict side view facing left, head to shoes visible."),
    }

    def st_tryon(self, feedback: str) -> dict:
        ft = self._facts()
        lead = self.lead()
        if ft.get("product_type") != "wearable" or not lead:
            return {"skipped": True, "reason": "商品不是穿戴類，演員維持原本造型"}
        lead = AC.ensure_ready(lead, need_portraits=True)
        prod = self._product_img()
        if not prod:
            raise RuntimeError("no product image for the try-on")
        from .. import vision_check as VC
        from ..providers import image_edit as E
        slot = ft.get("wearable_slot") or "top"
        name = ft.get("name") or "the product"
        prev = self.p.stage_data("tryon") or {}
        redo = set((prev.get("_redo") or [])) if prev.get("actor") == lead.id else set()
        notes = (feedback or prev.get("notes") or "").strip()
        by = {AC.view_of(p): str(AC.adir(lead.id) / p.file) for p in lead.portraits}
        views = []
        for k, (src, shot) in self.TRYON_VIEWS.items():
            out = self.p.path("tryon", f"{k}.png")
            old = next((v for v in prev.get("views", []) if v["view"] == k), None)
            if old and out.exists() and not feedback and k not in redo:
                views.append(old)
                continue
            base = by.get(src) or by.get("full_front")
            imgs = [base, str(prod)] + ([by["headshot"]] if k != "headshot" and "headshot" in by else [])
            wear = {"top": "instead of their current top (keep any jacket off so the garment is fully visible)",
                    "outerwear": "over their current clothes", "bottom": "instead of their current trousers or skirt",
                    "dress": "instead of their current outfit", "shoes": "instead of their current shoes",
                    "accessory": "as an accessory"}.get(slot, "")
            prompt = (f"The person in image 1 now wears the {slot} from image 2 ({name}) {wear}. Reproduce the garment from "
                      f"image 2 exactly: the same colour, fabric texture, collar, buttons and stitching. Keep the person's face"
                      f"{' (see image 3)' if len(imgs) > 2 else ''}, hairstyle, body, trousers and shoes unchanged. {shot} "
                      f"Plain light grey seamless studio background, soft even light, photorealistic."
                      + (f" Styling notes: {notes}." if notes else ""))
            seed = zlib.crc32(f"{self.p.id}{k}".encode()) % 2_000_000_000
            best = None
            for attempt in range(int(settings().get("actors.view_attempts", 3))):
                E.edit(prompt, imgs, out, seed=seed + attempt * 7919, label=f"{lead.name} × {name}")
                q = VC.check(k, out)
                if q["issues"] == ["腳底貼齊或超出畫面下緣"] and VC.fix_floor_margin(out, q["metrics"].get("feet_bottom", 0)):
                    q = VC.check(k, out)
                if best is None or q["score"] > best[0]:
                    best = (q["score"], out.read_bytes(), q)
                if q["status"] in ("pass", "skip"):
                    break
            out.write_bytes(best[1])
            views.append({"view": k, "file": self.p.rel(out), "prompt": prompt, "qa": best[2]})
            self.p.emit("progress", {"stage": "tryon", "view": k})
        return {"actor": lead.id, "product": self.p.rel(prod), "slot": slot, "notes": notes, "views": views}

    # ------------------------------------------------------------------ 3. concepts
    CONCEPTS = """You are the creative director of a top ad agency. Write THREE clearly different creative directions for a
{length:.0f}-second online video ad. Use only the facts given (fact ids); never invent product features, materials,
numbers or prices, and never mention stock, availability, sample/demo status or ordering. Each direction must suit the cast (their personalities and look) and the brand tone.
Return JSON {{"concepts":[{{"id":"A"|"B"|"C","name","idea" (2 sentences),"slogan" (≤ 8 words, in {lang}),
 "tone","keywords":[5],"palette":[5 hex colours: background, deep, accent, light, neutral],"lighting","music" (genre,
 tempo, instruments — instrumental), "mood_prompts":[4 English image prompts: places, light, textures, objects —
 NO people, NO text, NO logos], "preview":[2 shots {{"prompt": English, cinematic, refer to cast ONLY as @handle and
 to the product as "the product", one camera move, ≤ 60 words}}]}}]}}"""

    def st_concepts(self, feedback: str) -> dict:
        ft = self._facts()
        prev = self.p.stage_data("concepts") or {}
        if prev.get("concepts") and not feedback and all(c.get("preview_file") for c in prev["concepts"]):
            return prev
        payload = {"product": {k: ft.get(k) for k in ("name", "brand", "category", "product_type")},
                   "facts": self._creative_facts(), "cast": self._cast_text(), "language": self.lang,
                   "brand_tone": self.brief.get("tone", ""), "audience": self.brief.get("audience", ""),
                   "banned_words": self.brief.get("banned_words") or []}
        sys_ = self.CONCEPTS.format(length=self.length, lang=self.lang)
        if self.style.get("concepts"):
            sys_ += "\n" + self.style["concepts"].format(music=self._music_rule())
        if settings().mocked("qwen"):
            raw = _mock_concepts(self.cast(), ft)
        else:
            raw = self.ask("ad_concepts", sys_, payload, feedback)
        concepts = (raw or {}).get("concepts", [])[:3]
        if len(concepts) < 3:
            raise ValueError("the planner returned fewer than three directions")
        from ..providers import image_zimage as Z
        prod = self._product_img()
        for c in concepts:
            cid = str(c.get("id") or "ABC"[concepts.index(c)])
            c["id"] = cid
            c["palette"] = [p if re.fullmatch(r"#[0-9a-fA-F]{6}", str(p)) else "#888888" for p in (c.get("palette") or [])][:5]
            while len(c["palette"]) < 5:
                c["palette"].append("#888888")
            c["palette_theme"] = _theme(c["palette"])
            c["mood"] = []
            for i, mp in enumerate((c.get("mood_prompts") or [])[:4]):
                f = self.p.path("concepts", cid, f"mood_{i}.png")
                Z.generate(f"{mp}. Editorial photography, {c.get('lighting', '')}, colour palette {' '.join(c['palette'])}, "
                           f"no people, no text, no logo", f, width=1024, height=768,
                           seed=zlib.crc32(f"{cid}{i}{mp}".encode()) % 2_000_000_000, label=f"{cid} mood {i + 1}")
                c["mood"].append(self.p.rel(f))
        # batch by model: every H3 shot first, then every music sketch (ComfyUI ↔ ACE-Step swaps cost minutes)
        for c in concepts:
            self._concept_shots(c, prod)
            self.p.emit("progress", {"stage": "concepts", "concept": c["id"], "step": "shots"})
        for c in concepts:
            c["preview_file"] = self._concept_preview(c)
            self.p.emit("progress", {"stage": "concepts", "concept": c["id"]})
        return {"concepts": concepts, "chosen": None}

    def _concept_shots(self, c: dict, prod: Path | None) -> None:
        """Two 5 s H3 reference-to-video shots for the 10-second preview."""
        from ..providers.video_h3 import h3
        cid = c["id"]
        clips: list[str] = []
        cast = self.cast()
        for i, shot in enumerate((c.get("preview") or [])[:2]):
            raw = self.p.path("concepts", cid, f"pv_{i}_raw.mp4")
            out = self.p.path("concepts", cid, f"pv_{i}.mp4")
            who = [a for a in cast if f"@{a.handle}".lower() in str(shot.get("prompt", "")).lower()] or cast[:1]
            body = str(shot.get("prompt", "")) + (" Nobody speaks; mouths closed." if self.style.get("dialogue") is False else "")
            refs_by = {a.id: self._refs(a)[:2] for a in who}
            prompt, refs = cast_prompt(body, who, 2, refs_for=lambda a: refs_by[a.id])
            if prod and "product" in body.lower() and len(refs) < 9:
                refs.append(str(prod))
                prompt = prompt.replace("the product", f"the product shown in <Picture {len(refs)}>", 1)
            h3().generate(prompt, raw, seconds=5, aspect="16:9", mode="r2v", ref_images=refs,
                          seed=zlib.crc32(f"{cid}{i}".encode()) % 10_000)
            vt.normalize(str(raw), str(out), 1280, 720, 24, 5.0, keep_audio=True)
            clips.append(self.p.rel(out))
        c["preview_shots"] = clips

    def _concept_preview(self, c: dict) -> str:
        """Join the two shots and add a music sketch."""
        cid = c["id"]
        clips = [str(self.p.dir / f) for f in c.get("preview_shots", [])]
        pic = self.p.path("concepts", cid, "preview_pic.mp4")
        vt.xfade_chain(clips, str(pic), [{"type": "dissolve", "duration": 0.4}], fps=24)
        total = ff.duration(pic)
        music = self.p.path("concepts", cid, "music.wav")
        A.music(self._music_prompt(c), total + 1, music, instrumental=True)
        amb = self.p.path("concepts", cid, "amb.wav")
        vt.extract_audio(str(pic), str(amb))
        from ..tools import audio as au
        mix = self.p.path("concepts", cid, "mix.wav")
        au.place([{"path": str(music), "at": 0, "gain_db": -4}, {"path": str(amb), "at": 0, "gain_db": -18}], str(mix), total)
        out = self.p.path("concepts", cid, "preview.mp4")
        vt.replace_audio(str(pic), str(mix), str(out))
        return self.p.rel(out)

    def _apply_edits(self, stage: str, data: Any, edits: dict) -> Any:
        if stage == "concepts" and edits.get("choose"):
            data["chosen"] = str(edits["choose"])
            data["chosen_note"] = edits.get("note", "")
            c = next((x for x in data["concepts"] if x["id"] == data["chosen"]), None)
            if c:
                self.df["palette"] = c["palette_theme"]
            return data
        if stage == "tryon" and edits.get("redo"):
            data["_redo"] = list(edits["redo"])
            data["notes"] = edits.get("notes", data.get("notes", ""))
            self.p.checkpoint("tryon", data, status="review")
            return data
        if stage == "storyboard" and edits.get("redraw"):
            for sid, ch in edits["redraw"].items():
                shot = next((s for s in data["shots"] if s["id"] == sid), None)
                if shot:
                    shot.update({k: v for k, v in (ch or {}).items() if k in ("prompt", "shot_size", "angle", "lighting")})
                    shot["keyframe"] = None
                    shot["_seed_bump"] = int(shot.get("_seed_bump", 0)) + 1
            self.p.checkpoint("storyboard", data, status="review")
            return data
        return super()._apply_edits(stage, data, edits)

    # ------------------------------------------------------------------ 4. copy + outline
    COPY = """You are a senior copywriter. Write the copy and the beat outline for a {length:.0f}-second ad in {lang}, for the
chosen creative direction. RULES: every product claim must cite fact ids from `facts` (claims:[{{"text","fact_ids"}}]);
do not mention anything the facts do not support (materials, sizes, performance, discounts, prices unless a price fact
exists); never mention stock, availability, sample/demo status or ordering; no superlatives or guarantees; obey banned_words. Lines are spoken by cast members (speaker = "@handle") or
"narrator"; keep each line ≤ 12 words (English) / 18 characters (Chinese) so it fits its shot.
Return JSON {{"headline","sub","cta","url_label","supers":[{{"beat","text"}}],
 "outline":[{{"beat": one of {beats}, "start","end","purpose","lines":[{{"speaker","text"}}]}}],
 "claims":[{{"text","fact_ids":[..]}}], "social":[3 post captions], "hashtags":[..]}}
The outline must cover 0–{length:.0f} s in order; the last beat is "cta" (≥ 4 s, product pack shot)."""

    def st_copy(self, feedback: str) -> dict:
        if not self._concept():                        # gate passed without a choice (auto mode): take direction A
            c = self.p.stage_data("concepts")
            c["chosen"] = c["concepts"][0]["id"]
            self.p.checkpoint("concepts", c)
            self.p.decide(f"concept {c['chosen']}", "no direction was chosen on the board — using the first one")
            self.df["palette"] = c["concepts"][0]["palette_theme"]
        concept = self._concept() or {}
        ft = self._facts()
        payload = {"concept": {k: concept.get(k) for k in ("name", "idea", "slogan", "tone", "keywords")},
                   "facts": self._creative_facts(), "cast": self._cast_text(), "product": ft.get("name"),
                   "brand": ft.get("brand"), "url": self.brief.get("product_url"),
                   "banned_words": self.brief.get("banned_words") or [], "audience": self.brief.get("audience", "")}
        tpl = self.style.get("copy") or self.COPY
        sys_ = tpl.format(length=self.length, lang=self.lang, beats=BEATS, max_lines=self.style.get("max_lines", 0),
                          max_words=self.style.get("max_words", 0))
        fb = feedback
        for attempt in range(2):                       # one automatic revision when the claims / style check fails
            raw = _mock_copy(self.cast(), ft, concept, self.length) if settings().mocked("qwen") else self.ask("ad_copy", sys_, payload, fb)
            copy = raw if isinstance(raw, dict) else {}
            flags = claims_check(copy, ft, self.brief.get("banned_words") or [], self.p.stage_data("product") or {})
            style_issues = narration_check(copy, self.style)
            if (not [f for f in flags if f["level"] == "error"] and not style_issues) or attempt:
                break
            fb = (feedback + "\n" if feedback else "") + "Fix these problems: " + "; ".join(
                [f["message"] for f in flags if f["level"] == "error"] + style_issues)
        enforce_narration(copy, self.style)
        copy["flags"] = flags + [{"level": "warn", "message": m} for m in narration_check(copy, self.style)]
        copy["translations"] = self._translate_lines(copy)
        return copy

    def _translate_lines(self, copy: dict) -> dict:
        """Subtitle translations for every line / super (second subtitle language)."""
        others = [l for l in self.sub_langs if l.split("-")[0] != self.lang.split("-")[0]]
        if not others:
            return {}
        texts = [ln["text"] for b in copy.get("outline", []) for ln in b.get("lines", [])]
        texts += [s["text"] for s in copy.get("supers", [])] + [copy.get("headline", ""), copy.get("sub", ""), copy.get("cta", "")]
        texts = [t for t in dict.fromkeys(texts) if t]
        target = others[0]
        if settings().mocked("qwen"):
            return {target: {t: f"（{target}）{t}" for t in texts}}
        r = llm().json("ad_translate", f"Translate each string into natural {target} for subtitles (short, idiomatic, "
                                       f"same meaning, no additions). JSON {{\"items\":[{{\"src\",\"dst\"}}]}}",
                       _j({"strings": texts}))
        m = {i.get("src"): i.get("dst") for i in (r or {}).get("items", []) if isinstance(i, dict)}
        return {target: {t: m.get(t) or t for t in texts}}

    # ------------------------------------------------------------------ 5. storyboard (camera language + keyframes)
    BOARD = """You are the director and DP. Turn the approved outline into a shot list for a {length:.0f}-second ad.
Each shot: {{"id":"s01".., "beat", "duration" (seconds, 2–7), "shot_size" (ECU|CU|MCU|MS|MWS|WS|EWS), "angle",
"movement" (static|push-in|pull-out|pan|tilt|dolly|handheld|orbit), "lens" (e.g. 35mm), "lighting", "color",
"transition" (cut|dissolve|fade), "actors":["@handle".. visible], "product_visible": bool, "line": {{"speaker","text"}} or null,
"super": on-screen text or "", "prompt": English description of the frame for an image/video model — refer to cast ONLY
by @handle and to the product as "the product"; describe action, setting, framing, light; ≤ 70 words}}.
Rules: total duration exactly {length:.0f} s including a final pack-shot shot {{"kind":"endcard","beat":"cta","duration":4–5}};
every line fits its shot (≈2.6 English words/s, 4 Chinese chars/s); the product is clearly visible for ≥ {share:.0%} of the run
time; vary shot sizes; at most 3 people per shot. Return JSON {{"shots":[..]}}."""

    def st_storyboard(self, feedback: str) -> dict:
        prev = self.p.stage_data("storyboard") or {}
        if prev.get("shots") and not feedback:
            board = prev
        else:
            copy = self.p.stage_data("copy") or {}
            payload = {"outline": copy.get("outline"), "supers": copy.get("supers"), "headline": copy.get("headline"),
                       "cta": copy.get("cta"), "concept": {k: (self._concept() or {}).get(k) for k in ("name", "idea", "lighting", "keywords")},
                       "cast": self._cast_text(), "product": self._facts().get("name"),
                       "product_type": self._facts().get("product_type")}
            t = self.p.stage_data("tryon") or {}
            if t.get("views") and not t.get("skipped"):
                lead = self.lead()
                payload["wardrobe_rule"] = (f"@{lead.handle} WEARS the product ({self._facts().get('name')}) in every shot they "
                                            f"appear in — no jacket or other top over it; describe it as 'wearing the product'.")
            sys_ = self.BOARD.format(length=self.length, share=float(self.style.get("product_min", 0.35))) \
                + ("\n" + self.style["board"] if self.style.get("board") else "")
            fb = feedback
            for attempt in range(2):                   # one automatic redo when the board breaks the style rules
                raw = _mock_board(self.cast(), copy, self.length) if settings().mocked("qwen") else \
                    self.ask("ad_storyboard", sys_, payload, fb, max_tokens=16384)
                shots = (raw or {}).get("shots", [])
                issues = board_check(shots, copy, self.style, self.length)
                if not issues or attempt:
                    break
                log.info("storyboard redo: %s", "; ".join(issues))
                fb = (feedback + "\n" if feedback else "") + "Fix these problems with the shot list: " + "; ".join(issues)
            if issues:
                self.p.decide("storyboard rules", "; ".join(issues))
            board = {"shots": [self._clean_shot(s, i) for i, s in enumerate(shots)]}
            _fit_total(board["shots"], self.length, min_dur=self.style.get("shot_min", 2.0),
                       end_range=(3.0, 4.0) if self.style.get("endcard") == "minimal" else (4.0, 5.0))
            board["style"] = self.style_id
        for s in board["shots"]:
            if s.get("kind") == "endcard" or (s.get("keyframe") and (self.p.dir / s["keyframe"]).exists()):
                continue
            s["keyframe"] = self.p.rel(self._keyframe(s, "16:9"))
            self.p.emit("progress", {"stage": "storyboard", "shot": s["id"]})
            self.p.checkpoint("storyboard", board, status="running")
        board["product_seconds"] = round(sum(s["duration"] for s in board["shots"] if s.get("product_visible")), 2)
        self._write_plan(board)
        return board

    def _clean_shot(self, s: dict, i: int) -> dict:
        s = dict(s or {})
        s["id"] = f"s{i + 1:02d}"
        s["beat"] = s.get("beat") if s.get("beat") in BEATS else BEATS[min(i * len(BEATS) // 12, 5)]
        s["duration"] = float(min(self.style.get("shot_max", 7), max(self.style.get("shot_min", 2), float(s.get("duration") or 4))))
        s["insert"] = s.get("kind") == "insert"
        s["kind"] = "endcard" if s.get("kind") == "endcard" else "shot"
        ids = []
        for r in s.get("actors") or []:
            aid = self._actor_id(r)
            if aid and aid not in ids:
                ids.append(aid)
        s["actors"] = ids[:3]
        ln = s.get("line") or {}
        if isinstance(ln, str):
            ln = {"speaker": "narrator", "text": ln}
        s["line"] = {"speaker": self._actor_id(ln.get("speaker", "")) or "", "text": str(ln.get("text", "")).strip()} if ln.get("text") else None
        if s["line"] and self.style.get("dialogue") is False:
            s["line"]["speaker"] = ""                   # narrator: nobody speaks on camera
        if s["insert"]:
            s["actors"], s["product_visible"] = [], False
        s["product_visible"] = bool(s.get("product_visible")) or s["kind"] == "endcard"
        return s

    def _keyframe(self, s: dict, aspect: str) -> Path:
        """Qwen-Image-Edit composite: the cast (try-on look for the lead) + the product → one film still."""
        from ..providers import image_edit as E
        cast = {a.id: a for a in self.cast()}
        imgs, roles = [], {}
        worn = bool(self._tryon_refs(next(iter(cast), "")))
        for aid in s.get("actors", []):
            a = cast.get(aid)
            if not a or len(imgs) >= 3:
                continue
            ref = (self._tryon_refs(aid)[1:2] or AC.ref_images(a, ["full_front"])[:1] or AC.ref_images(a)[:1])
            if ref:
                imgs.append(ref[0])
                roles[aid] = f"the {AC.person_en(a).split('-old ')[-1]} from image {len(imgs)}"
        prod = self._product_img()
        prod_role = None
        if s.get("product_visible") and prod and len(imgs) < 3:     # also when worn: the reference keeps the fabric true
            imgs.append(str(prod))
            prod_role = f"the product from image {len(imgs)}"
        body = str(s.get("prompt", ""))
        for aid, role in roles.items():
            a = cast[aid]
            body = re.sub(rf"@(?:{re.escape(a.handle)}|{re.escape(a.name)})(?![A-Za-z0-9_])", role, body, flags=re.I)
        if prod_role:
            body = re.sub(r"\bthe product\b", prod_role, body, count=1, flags=re.I)
        w, h = {"16:9": (1344, 768), "9:16": (768, 1344), "1:1": (1024, 1024)}[aspect]
        concept = self._concept() or {}
        n_people = len(roles)
        people = (f"Exactly {n_people} {'person' if n_people == 1 else 'people'} in the frame, each appearing once. "
                  if n_people else "")
        if self.style_id == "fashion":
            look = ("Luxury fashion film still, quiet and unhurried, low saturation, soft film grain" if n_people
                    else "Luxury landscape and still-life film frame with NO people, no person, no model, no figure anywhere, "
                         "low saturation, soft film grain")
        else:
            look = "Cinematic advertising film still"
        if not roles:
            body = re.sub(r"\b(no people|nobody)\b[^.,;]*[.,;]?", "", body, flags=re.I).strip()
        if self.style.get("dialogue") is False and n_people:
            people += "Mouths closed, nobody talks. "
        prompt = (f"{look}, {aspect} frame. {people}{body}. {s.get('shot_size', '')} shot, "
                  f"{s.get('angle', 'eye level')}, {s.get('lens', '35mm')} lens, {s.get('lighting') or concept.get('lighting', '')}, "
                  f"{s.get('color', '')} colour grade. "
                  + (f"Keep every person exactly as in their reference image (face, hair, clothes"
                     f"{', the garment they wear' if worn else ''}); " if roles else "")
                  + "keep the product's exact colour and details. Photorealistic, "
                  + ("natural skin, no text, no logo, no watermark." if roles else
                     "no text, no logo, no watermark. The frame contains no human being at all."))
        out = self.p.path("storyboard", f"{s['id']}_{aspect.replace(':', 'x')}.png")
        seed = (zlib.crc32(f"{self.p.id}{s['id']}".encode()) + 7919 * int(s.get("_seed_bump", 0))) % 2_000_000_000
        if not imgs:                                    # no people, no product: plain Z-Image still
            from ..providers import image_zimage as Z
            Z.generate(prompt, out, width=w, height=h, seed=seed, label=s["id"])
        else:
            E.edit(prompt, imgs, out, seed=seed, width=w, height=h, label=s["id"])
        return out

    def _write_plan(self, board: dict) -> None:
        """Storyboard → the generic scene plan (voice / assets / edit / compose reuse it unchanged)."""
        copy = self.p.stage_data("copy") or {}
        concept = self._concept() or {}
        ft = self._facts()
        prod = self._product_img()
        logo = (self.p.stage_data("product") or {}).get("logo_file")
        scenes = []
        for s in board["shots"]:
            line = s.get("line") or {}
            sc = {"id": s["id"], "section_id": s["beat"], "duration_s": s["duration"], "narration": line.get("text", ""),
                  "speaker": line.get("speaker", ""), "on_screen_text": s.get("super", ""), "actors": [],
                  "transition": {"type": s.get("transition") if s.get("transition") in ("cut", "dissolve", "fade") else "cut",
                                 "duration": 0.0 if s.get("transition") in (None, "cut") else 0.3},
                  "sfx": [], "foley": False, "music_cue": s["beat"]}
            if s.get("kind") == "endcard":
                sc["visual"] = {"kind": "motion", "template": "ad_endcard", "params": {
                    "product_img": prod.as_uri() if prod else "", "brand": ft.get("brand", ""),
                    "logo_img": (self.p.dir / "product" / logo).as_uri() if logo else "",
                    "headline": copy.get("headline") or concept.get("slogan", ""), "sub": copy.get("sub", ""),
                    "cta": copy.get("cta", "Shop now"), "url": copy.get("url_label") or _host(self.brief.get("product_url", "")),
                    "minimal": self.style.get("endcard") == "minimal"}}
            else:
                cam = f"{s.get('movement', 'static')} camera, {s.get('lens', '')} lens"
                body = re.sub(r"@\w+", "the person", str(s.get("prompt", "")))
                if self.style.get("dialogue") is False:
                    body += (" Slow, unhurried movement. Nobody speaks: mouths stay closed; natural ambient sound only."
                             if s.get("actors") else " Natural ambient sound only.")
                sc["visual"] = {"kind": "h3_i2v", "prompt": body, "camera": cam,
                                "params": {"first_frame": str(self.p.dir / s["keyframe"]) if s.get("keyframe") else ""}}
            scenes.append(sc)
        plan = {"scenes": scenes, "music": {"prompt": self._music_prompt(concept), "instrumental": True},
                "voice": {"description": self.style["voice"]} if self.style.get("voice") else {}}
        from .. import cost as costmod
        plan["_estimate"] = est = costmod.estimate_plan(plan, self.brief)
        self.p.update(lambda d: d["cost"].__setitem__("estimated", est["total_cost"]))
        self.p.checkpoint("scene_plan", plan)

    # ------------------------------------------------------------------ 6. voice: keep the run time exact
    def st_voice(self, feedback: str) -> dict:
        out = super().st_voice(feedback)
        plan = self.p.stage_data("scene_plan")
        total = self._timeline(plan)["total"]
        diff = round(total - self.length, 3)
        if abs(diff) > 0.02:
            if diff > 0:                                 # narration grew: take time from line-less shots (≥ 2 s each)
                for sc in sorted([x for x in plan["scenes"] if not x.get("narration")], key=lambda x: -x["duration_s"]):
                    floor = 3.0 if sc["visual"]["kind"] == "motion" else 2.0
                    d = min(diff, max(0.0, sc["duration_s"] - floor))
                    sc["duration_s"] = round(sc["duration_s"] - d, 3)
                    diff = round(diff - d, 3)
                    if diff <= 0.02:
                        break
            else:                                        # transitions / rounding made it short: hold the pack shot longer
                end = next((x for x in reversed(plan["scenes"]) if x["visual"]["kind"] == "motion"), plan["scenes"][-1])
                end["duration_s"] = round(end["duration_s"] - diff, 3)
                diff = 0.0
            if abs(diff) > 0.02:
                self.p.decide(f"run time off by {diff:+.2f}s", "narration longer than the shots allow — shorten lines on the copy gate")
            self.p.checkpoint("scene_plan", plan)
        return out

    # ------------------------------------------------------------------ subtitles: bilingual + supers
    def _post_cues(self, cues: list[dict], spans: list[dict]) -> list[dict]:
        tr = (self.p.stage_data("copy") or {}).get("translations") or {}
        if not tr:
            return cues
        table = next(iter(tr.values()))
        by_span: dict[int, list[dict]] = {}
        for c in cues:
            mid = (c["start"] + c["end"]) / 2
            j = min(range(len(spans)), key=lambda k: 0 if spans[k]["start"] <= mid <= spans[k]["end"] else
                    min(abs(spans[k]["start"] - mid), abs(spans[k]["end"] - mid))) if spans else -1
            by_span.setdefault(j, []).append(c)
        for j, group in by_span.items():
            src = spans[j]["text"] if j >= 0 else ""
            zh = table.get(src, "")
            parts = _split_like(zh, [g["text"] for g in group])
            for g, z in zip(group, parts):
                if z:
                    g["text"] = f"{g['text']}\n{z}"
                    g["bilingual"] = True
        return cues

    def _ass_extra(self, total: float) -> list[str]:
        from ..tools.subtitles import _fmt
        plan = self._sd("scene_plan") or {}
        tl = self._timeline(plan)
        ev = []
        tr = next(iter(((self.p.stage_data("copy") or {}).get("translations") or {}).values()), {})
        for sc in plan.get("scenes", []):
            txt = (sc.get("on_screen_text") or "").strip()
            if not txt or sc["visual"]["kind"] == "motion":
                continue
            st = tl["starts"][sc["id"]] + 0.2
            en = min(total, st + sc["duration_s"] - 0.4)
            shown = txt
            if self.style_id == "fashion" and self.w < self.h * 1.2:   # wide-spaced couplets: one sentence per line
                shown = re.sub(r"([.!?。！？])\s+(?=\S)", r"\1\\N", txt)
            body = shown + (f"\\N{{\\fs{int(min(self.w, self.h) * 0.04)}}}{tr[txt]}" if tr.get(txt) else "")
            if self.style_id == "fashion":              # wide-spaced, light, centred titles that fade slowly
                m = min(self.w, self.h)
                tags = f"{{\\an5\\b0\\fs{int(m * 0.045)}\\fsp{int(m * 0.014)}\\bord1\\shad0\\fad(700,700)}}"
            else:
                tags = "{\\fad(250,250)}"
            ev.append(f"Dialogue: 1,{_fmt(st, '.')[:-1]},{_fmt(en, '.')[:-1]},Super,,0,0,0,,{tags}{body}")
        return ev

    # ------------------------------------------------------------------ 7. versions: 60/15 × 16:9 / 9:16 / 1:1
    def st_versions(self, feedback: str) -> dict:
        plan = self.p.stage_data("scene_plan")
        assets = self.p.stage_data("assets")["scenes"]
        voice = (self.p.stage_data("voice") or {}).get("clips", {})
        board = {s["id"]: s for s in (self.p.stage_data("storyboard") or {}).get("shots", [])}
        comp = self.p.stage_data("compose")
        outs = []
        crops: dict = {}
        cuts = [("60", None)] + ([("15", self._cutdown(plan, voice, board))] if self.brief.get("cutdown_15", True) else [])
        for length, sel in cuts:
            for aspect in self.formats:
                tag = f"{length}s_{aspect.replace(':', 'x')}"
                if length == "60" and aspect == "16:9":
                    o = {k: comp.get(k) for k in ("master", "srt", "ass", "cues", "spans", "words")}
                else:
                    o = self._render_version(tag, aspect, plan, assets, voice, board, sel, crops)
                w, h = dims(aspect)
                o.update(aspect=aspect, size=(w, h), fps=self.fps, promised_duration=float(length), tolerance_s=0.3,
                         label=f"{length} 秒 · {aspect}", tag=tag)
                outs.append(o)
                self.p.emit("progress", {"stage": "versions", "version": tag})
        return {"outputs": outs, "crops": crops}

    def _cutdown(self, plan: dict, voice: dict, board: dict) -> dict:
        """15 s: hook → product reveal → strongest demo → pack shot. Lines are kept only when they fit whole."""
        scenes = plan["scenes"]
        pick, used = [], set()
        for beat, dur in (("hook", 3.0), ("reveal", 4.0), ("demo", 4.0)):
            cands = [sc for sc in scenes if sc["section_id"] == beat and sc["id"] not in used and sc["visual"]["kind"] != "motion"]
            cands.sort(key=lambda sc: (not board.get(sc["id"], {}).get("product_visible"), -sc["duration_s"]))
            if cands:
                pick.append((cands[0]["id"], dur))
                used.add(cands[0]["id"])
        end = next((sc for sc in scenes if sc["visual"]["kind"] == "motion"), None)
        rest = 15.0 - sum(d for _, d in pick)
        if end:
            pick.append((end["id"], rest))
        else:
            pick[-1] = (pick[-1][0], pick[-1][1] + rest)
        return {"scenes": pick}

    def _render_version(self, tag: str, aspect: str, plan: dict, assets: dict, voice: dict, board: dict,
                        sel: dict | None, crops: dict) -> dict:
        saved = (self.aspect, self.w, self.h, self.fps)
        self.aspect, (self.w, self.h) = aspect, dims(aspect)
        try:
            ids = [s for s, _ in sel["scenes"]] if sel else [sc["id"] for sc in plan["scenes"]]
            durs = dict(sel["scenes"]) if sel else {sc["id"]: sc["duration_s"] for sc in plan["scenes"]}
            vplan = {**plan, "scenes": []}
            vassets, vvoice = {}, {}
            for sid in ids:
                sc = json.loads(_j(next(s for s in plan["scenes"] if s["id"] == sid)))
                sc["duration_s"] = round(float(durs[sid]), 3)
                if sel:
                    sc["transition"] = {"type": "cut", "duration": 0.0}
                f = self._version_visual(sc, aspect, assets[sid], board.get(sid, {}), crops)
                vassets[sid] = {**assets[sid], "file": self.p.rel(f)}
                if sid in voice and voice[sid]["duration"] <= sc["duration_s"] - 0.3:
                    vvoice[sid] = voice[sid]
                elif sid in voice:
                    sc["narration"] = ""                 # the line does not fit the shortened shot
                vplan["scenes"].append(sc)
            ms = dict(self.p.stage_data("music_sfx") or {})
            if sel and ms.get("music"):
                f = self.p.path("audio", f"music_{tag}.wav")
                if not f.exists():
                    A.music(ms["music"]["prompt"], 16, f, instrumental=True)
                ms["music"] = {**ms["music"], "file": self.p.rel(f)}
            ms["sfx"] = []
            self._override = {"scene_plan": vplan, "assets": {"scenes": vassets}, "voice": {"clips": vvoice}, "music_sfx": ms}
            self._tag = tag
            ed = self.st_edit("")
            self._override["edit"] = ed
            return self.st_compose("")
        finally:
            self._override, self._tag = {}, ""
            self.aspect, self.w, self.h, self.fps = saved

    def _version_visual(self, sc: dict, aspect: str, asset: dict, shot: dict, crops: dict) -> Path:
        sid = sc["id"]
        d = self.p.dir / "scenes" / sid
        tag = aspect.replace(":", "x")
        out = d / f"visual_{tag}.mp4"
        if out.exists() and (d / f"visual_{tag}.json").exists():
            crops[f"{sid}@{aspect}"] = json.loads((d / f"visual_{tag}.json").read_text())
            return out
        src = self.p.dir / asset["file"]
        info: dict = {"shot": sid, "aspect": aspect}
        if sc["visual"]["kind"] == "motion":           # end card: re-render natively at the new size
            me.render(sc["visual"]["template"], out, seconds=max(sc["duration_s"], 3.0), w=self.w, h=self.h, fps=self.fps,
                      params=sc["visual"].get("params") or {}, palette=self.df.get("palette", "slate"))
            info["method"] = "rerender"
        else:
            box = _subject_box(src, self.p.dir / asset["file"])
            raw_p = self.p.dir / "scenes" / sid / "raw.mp4"
            raw_w = int((ff.video_stream(raw_p) or {}).get("width", 0) or 0) if raw_p.exists() else 1024
            a, b = (int(x) for x in aspect.split(":"))
            vs = ff.video_stream(src) or {}
            src_w, src_h = int(vs.get("width", 1920)), int(vs.get("height", 1080))
            cw = src_h * a / b                          # crop width on the 1920×1080 master
            native_px = cw * (raw_w or src_w) / src_w   # real pixels behind the crop (H3 renders below 1080p)
            min_px = float(settings().get("ads.min_crop_px", 480))
            fits = box is None or (box[2] - box[0]) * src_w <= cw * 0.92
            if aspect == "9:16" and (native_px < min_px or not fits):
                kf = self._keyframe({**shot, "prompt": shot.get("prompt", ""), "id": sid}, "9:16") if shot else None
                from ..providers.video_h3 import h3
                raw = d / f"raw_{tag}.mp4"
                h3().generate(sc["visual"].get("prompt", ""), raw, seconds=int(min(15, max(4, math.ceil(sc["duration_s"])))),
                              aspect="9:16", mode="i2v", first_frame=str(kf) if kf else None,
                              seed=zlib.crc32(f"{sid}{tag}".encode()) % 10_000)
                vt.normalize(str(raw), str(out), self.w, self.h, self.fps, sc["duration_s"], fit="cover", keep_audio=True)
                info.update(method="regenerate", reason="crop too small" if native_px < min_px else "subject does not fit",
                            crop_px=round(native_px), keyframe=self.p.rel(kf) if kf else None)
            else:
                cx = ((box[0] + box[2]) / 2 * src_w) if box else src_w / 2
                x = int(min(max(0, cx - cw / 2), src_w - cw))
                ff.run(["-i", src, "-vf", f"crop={int(cw)}:{src_h}:{x}:0,scale={self.w}:{self.h}:flags=lanczos,setsar=1",
                        "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "copy", out])
                info.update(method="crop", x=x, width=int(cw), crop_px=round(native_px),
                            subject=[round(v, 3) for v in box] if box else None)
        (d / f"visual_{tag}.json").write_text(_j(info), encoding="utf-8")
        crops[f"{sid}@{aspect}"] = info
        return out

    # ------------------------------------------------------------------ 8. QA + delivery
    def st_qa(self, feedback: str) -> dict:
        self.p.checkpoint("compose", {**(self.p.stage_data("compose") or {}),
                                       "outputs": (self.p.stage_data("versions") or {}).get("outputs") or []})
        rep = super().st_qa(feedback)
        board = self.p.stage_data("storyboard") or {}
        copy = self.p.stage_data("copy") or {}
        total = sum(s["duration"] for s in board.get("shots", [])) or 1
        prod_s = board.get("product_seconds", 0)
        for r, o in zip(rep["reports"], (self.p.stage_data("versions") or {}).get("outputs", [])):
            need = float(self.style.get("product_min", 0.35))
            extra = [qa._r("product_time", "pass" if prod_s / total >= need else "warn",
                           f"商品出現 {prod_s:.0f}s / {total:.0f}s（{prod_s / total:.0%}，目標 ≥ {need:.0%}）")]
            ass = self.p.dir / o["ass"] if o.get("ass") else None
            text = (ass.read_text(encoding="utf-8") if ass and ass.exists() else "").replace("\\N", " ")
            plan_supers = [s.get("super") for s in board.get("shots", [])      # the end card draws its own text
                           if s.get("super") and s.get("kind") != "endcard"]
            missing = [s for s in plan_supers if s not in text] if o.get("tag", "").startswith("60") else []
            extra.append(qa._r("supers", "fail" if missing else "pass",
                               f"缺少字卡：{'、'.join(missing)}" if missing else f"{len(plan_supers)} 張字卡與文案一致"))
            flags = [f for f in copy.get("flags", []) if f["level"] == "error"]
            extra.append(qa._r("claims", "fail" if flags else "pass",
                               "；".join(f["message"] for f in flags) or "所有宣稱都對得回商品事實表"))
            r["results"] += extra
            if any(x["status"] == "fail" for x in extra):
                r["status"] = "fail"
            elif r["status"] == "pass" and any(x["status"] == "warn" for x in extra):
                r["status"] = "warn"
        rep["status"] = "fail" if any(r["status"] == "fail" for r in rep["reports"]) else \
            "warn" if any(r["status"] == "warn" for r in rep["reports"]) else "pass"
        return rep

    def _title(self) -> str:
        h = ((self.p.stage_data("copy") or {}).get("headline") or "").strip().rstrip(".。!！")
        brand = ((self.p.stage_data("product") or {}).get("brand") or "").strip()
        return " ".join(x for x in (brand, h) if x) or super()._title()

    def _deliver(self) -> dict:
        out = super()._deliver()
        self._extras()
        return out

    def _extras(self) -> None:
        """Storyboard PDF, copy deck, mood board and sources next to the videos."""
        board = self.p.stage_data("storyboard") or {}
        copy = self.p.stage_data("copy") or {}
        concept = self._concept() or {}
        prod = self.p.stage_data("product") or {}
        rows = "".join(
            f"<tr><td><b>{s['id']}</b><br>{BEAT_ZH.get(s['beat'], s['beat'])}<br>{s['duration']:.1f}s</td>"
            f"<td>{_img(self.p.dir / s['keyframe']) if s.get('keyframe') else '片尾商品定格'}</td>"
            f"<td>{s.get('shot_size', '')} · {s.get('angle', '')} · {s.get('movement', '')} · {s.get('lens', '')}<br>"
            f"{s.get('lighting', '')} · {s.get('color', '')}<br>轉場：{s.get('transition', '')}</td>"
            f"<td>{_esc((s.get('line') or {}).get('text', ''))}<br><i>{_esc(s.get('super', ''))}</i></td></tr>"
            for s in board.get("shots", []))
        html = (f"<html><head><meta charset='utf-8'><style>body{{font-family:'Noto Sans CJK TC',sans-serif;font-size:11px}}"
                f"table{{border-collapse:collapse;width:100%}}td{{border:1px solid #ccc;padding:6px;vertical-align:top}}"
                f"img{{width:260px}}h1{{font-size:18px}}</style></head><body><h1>{_esc(copy.get('headline', ''))} — 分鏡表</h1>"
                f"<p>{_esc(concept.get('name', ''))}：{_esc(concept.get('idea', ''))}</p><table>"
                f"<tr><th>鏡</th><th>關鍵分鏡</th><th>鏡頭語言</th><th>台詞／字卡</th></tr>{rows}</table></body></html>")
        page = self.p.path("final", "storyboard.html")
        page.write_text(html, encoding="utf-8")
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                b = p.chromium.launch(args=["--allow-file-access-from-files"])
                pg = b.new_page()
                pg.goto(page.as_uri())
                pg.pdf(path=str(self.p.path("final", "storyboard.pdf")), format="A4", landscape=True, print_background=True)
                b.close()
            page.unlink()
        except Exception as e:  # noqa: BLE001
            log.warning("storyboard pdf failed: %s", e)
        md = [f"# {copy.get('headline', '')}", "", f"- 副標：{copy.get('sub', '')}", f"- CTA：{copy.get('cta', '')}", "",
              "## 腳本大綱"]
        for b in copy.get("outline", []):
            md.append(f"- **{BEAT_ZH.get(b.get('beat'), b.get('beat'))}**（{b.get('start')}–{b.get('end')}s）{b.get('purpose', '')}")
            md += [f"  - {ln.get('speaker')}: {ln.get('text')}" for ln in b.get("lines", [])]
        md += ["", "## 字卡", *[f"- {s.get('text')}" for s in copy.get("supers", [])], "", "## 社群貼文",
               *[f"- {t}" for t in copy.get("social", [])], "", "## 宣稱與出處"]
        facts = {f["id"]: f for f in (prod.get("fact_table") or {}).get("facts", [])}
        for c in copy.get("claims", []):
            md.append(f"- {c.get('text')} ← " + "；".join(f"{i}: “{facts.get(i, {}).get('source', '?')}”" for i in c.get("fact_ids", [])))
        md += ["", "## 資料來源", f"- 商品頁：{prod.get('url', '')}（擷取方式：{prod.get('fetched_with', '')}）",
               f"- 價格：{'未使用 — ' + prod['price']['reason'] if not prod.get('price', {}).get('display') else prod['price']['value']}"]
        self.p.path("final", "copy.md").write_text("\n".join(md), encoding="utf-8")
        tiles = [self.p.dir / m for m in concept.get("mood", []) if (self.p.dir / m).exists()]
        if tiles:
            ins = sum((["-i", str(t)] for t in tiles), [])
            n = len(tiles)
            ff.run([*ins, "-filter_complex", "".join(f"[{i}]scale=640:480[t{i}];" for i in range(n)) +
                    "".join(f"[t{i}]" for i in range(n)) + f"hstack={n}", "-frames:v", "1",
                    self.p.path("final", "moodboard.jpg")])


# ---------------------------------------------------------------- pure helpers
def claims_check(copy: dict, ft: dict, banned: list[str], product: dict) -> list[dict]:
    """Every claim cites real fact ids; no risky wording; numbers and prices must come from the facts."""
    facts = {f["id"]: f for f in ft.get("facts", [])}
    fact_text = " ".join(f"{f.get('fact', '')} {f.get('fact_zh', '')} {f.get('source', '')}" for f in facts.values()).lower()
    flags = []
    for c in copy.get("claims", []):
        bad = [i for i in c.get("fact_ids", []) if i not in facts]
        if not c.get("fact_ids") or bad:
            flags.append({"level": "error", "text": c.get("text"), "message": f"宣稱「{c.get('text')}」沒有對應的商品事實"})
    texts = [copy.get("headline", ""), copy.get("sub", ""), copy.get("cta", "")] + [s.get("text", "") for s in copy.get("supers", [])]
    texts += [ln.get("text", "") for b in copy.get("outline", []) for ln in b.get("lines", [])] + list(copy.get("social", []))
    for t in texts:
        if not t:
            continue
        if RISKY.search(t):
            flags.append({"level": "error", "text": t, "message": f"療效／絕對化用語：「{RISKY.search(t).group(0)}」（{t}）"})
        if PR.NOT_FOR_SALE.search(t):
            flags.append({"level": "error", "text": t, "message": f"文案提到樣品／不可訂購等頁面注意事項（{t}）"})
        for w in banned:
            if w and w.lower() in t.lower():
                flags.append({"level": "error", "text": t, "message": f"禁用詞「{w}」（{t}）"})
        for num in re.findall(r"\d{2,}(?:[.,]\d+)?\s*%?|\d+(?:[.,]\d+)?\s*%", t):
            n = num.strip()
            if len(n.rstrip("%")) and n.rstrip("%") not in fact_text and not re.fullmatch(r"(15|30|60)", n):
                flags.append({"level": "warn", "text": t, "message": f"數字「{n}」不在商品事實表中（{t}）"})
        if re.search(r"(HK\$|NT\$|US\$|\$|€|£|¥|元|塊)\s?\d", t) and not product.get("price", {}).get("display"):
            flags.append({"level": "error", "text": t, "message": f"文案出現價格，但頁面價格不可使用（{t}）"})
    return flags


def _lines(copy: dict) -> list[dict]:
    return [ln for b in copy.get("outline", []) or [] for ln in (b.get("lines") or []) if isinstance(ln, dict)]


def _words(text: str) -> int:
    t = str(text or "")
    return len(re.sub(r"\s|[，。、,.!?！？]", "", t)) // 2 if re.search(r"[\u4e00-\u9fff]", t) else len(t.split())


def narration_check(copy: dict, style: dict) -> list[str]:
    """Style rules for the spoken copy: no on-camera dialogue, few and short narrator lines."""
    out = []
    if style.get("dialogue") is False:
        talk = [ln for ln in _lines(copy) if str(ln.get("speaker", "narrator")).lower() not in ("narrator", "", "vo", "voice-over")]
        if talk:
            out.append(f"{len(talk)} lines are spoken by cast members — nobody speaks on camera, use the narrator only")
    n, mx = len(_lines(copy)), style.get("max_lines")
    if mx and n > mx:
        out.append(f"{n} narration lines — at most {mx}")
    mw = style.get("max_words")
    long_ = [ln["text"] for ln in _lines(copy) if mw and _words(ln.get("text", "")) > mw]
    if long_:
        out.append(f"lines longer than {mw} words: " + " | ".join(long_[:3]))
    return out


def enforce_narration(copy: dict, style: dict) -> None:
    """Last resort after the revision: narrator only, and drop the surplus lines (keep the first and the last)."""
    if style.get("dialogue") is False:
        for ln in _lines(copy):
            ln["speaker"] = "narrator"
    mx = style.get("max_lines")
    lines = _lines(copy)
    if mx and len(lines) > mx:
        keep = set(map(id, lines[:mx - 1] + lines[-1:]))
        for b in copy.get("outline", []):
            b["lines"] = [ln for ln in (b.get("lines") or []) if id(ln) in keep]


def board_check(shots: list[dict], copy: dict, style: dict, length: float) -> list[str]:
    """Structural problems in a planned shot list (before timing is fitted)."""
    out = []
    body = [s for s in shots if s.get("kind") != "endcard"]
    lo = style.get("min_shots") or 0
    if lo and len(body) < lo:
        out.append(f"only {len(body)} shots — this style needs {lo}–{lo + 5} shots of 1.5–6 s")
    mx = style.get("shot_max")
    long_ = [s.get("id", "?") for s in body if mx and float(s.get("duration") or 0) > mx + 0.01]
    if long_:
        out.append(f"shots longer than {mx:.0f} s: {', '.join(long_)}")
    beats = {b.get("beat") for b in copy.get("outline", []) or []}
    missing = [b for b in BEATS if b in beats and not any(s.get("beat") == b for s in shots)]
    if missing:
        out.append("no shots for the beats " + ", ".join(missing))
    said = " ".join(str((s.get("line") or {}).get("text", "") if isinstance(s.get("line"), dict) else s.get("line") or "")
                    for s in shots).lower()
    lost = [ln["text"] for ln in _lines(copy) if ln.get("text") and ln["text"].lower().rstrip(".") not in said]
    if lost:
        out.append("these narration lines are not placed on any shot: " + " | ".join(lost))
    want = [x.get("text") for x in copy.get("supers", []) or [] if x.get("text")]
    shown = " ".join(str(s.get("super") or "") for s in shots)
    if [w for w in want if w not in shown]:
        out.append("these supers are not placed on any shot: " + " | ".join(w for w in want if w not in shown))
    return out


def _fit_total(shots: list[dict], length: float, min_dur: float = 2.0, end_range: tuple = (4.0, 5.0)) -> None:
    """Scale shot lengths so they add up to `length` exactly (end card kept at 4–5 s)."""
    if not shots:
        return
    if shots[-1].get("kind") != "endcard":
        shots.append({"id": f"s{len(shots) + 1:02d}", "beat": "cta", "duration": 4.5, "kind": "endcard", "actors": [],
                      "product_visible": True, "line": None, "super": "", "prompt": ""})
    end = shots[-1]
    end["duration"] = min(end_range[1], max(end_range[0], end["duration"]))
    body = shots[:-1]
    want = length - end["duration"]
    have = sum(s["duration"] for s in body) or 1
    for s in body:
        s["duration"] = round(max(min_dur, s["duration"] * want / have), 2)
    end["duration"] = round(length - sum(s["duration"] for s in body), 2)


def _split_like(text: str, parts: list[str]) -> list[str]:
    """Split a translation into len(parts) pieces proportional to the source pieces (at punctuation when possible)."""
    if len(parts) <= 1 or not text:
        return [text] + [""] * (len(parts) - 1)
    total = sum(len(p) for p in parts) or 1
    out, rest = [], text
    for p in parts[:-1]:
        n = max(1, round(len(text) * len(p) / total))
        cut = max((rest.rfind(ch, 0, n + 3) for ch in "，。、,.;；！？!? "), default=-1)
        cut = cut + 1 if cut >= n // 2 else n
        out.append(rest[:cut].strip(" ，,"))
        rest = rest[cut:]
    out.append(rest.strip(" ，,"))
    return out


def _subject_box(src: Path, _unused: Path) -> tuple[float, float, float, float] | None:
    """Union box (normalised x0,y0,x1,y1) of the people in the middle frame of a shot (RTMW); None = nobody found."""
    from .. import vision_check as VC
    if settings().mode == "mock":
        return None
    tmp = src.with_suffix(".mid.jpg")
    try:
        ff.run(["-ss", f"{ff.duration(src) / 2:.2f}", "-i", src, "-frames:v", "1", tmp])
        a = VC.analyze(tmp)
    finally:
        tmp.unlink(missing_ok=True)
    if not a or not a["poses"]:
        return None
    xs = [k["x"] for p in a["poses"] for k in p[:23] if k["s"] > 0.4]
    ys = [k["y"] for p in a["poses"] for k in p[:23] if k["s"] > 0.4]
    if not xs:
        return None
    pad = 0.04
    return (max(0, min(xs) - pad), max(0, min(ys) - pad), min(1, max(xs) + pad), min(1, max(ys) + pad))


def _theme(pal: list[str]) -> dict:
    """Concept palette → motion-engine theme (dark background for legible end cards)."""
    def lum(h: str) -> float:
        r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    by = sorted(pal, key=lum)
    bg, deep, light = by[0], by[1], by[-1]
    accent = max(pal, key=lambda h: max(int(h[i:i + 2], 16) for i in (1, 3, 5)) - min(int(h[i:i + 2], 16) for i in (1, 3, 5)))
    return {"bg": bg, "bg2": deep, "fg": light if lum(light) > 170 else "#f4f4f2", "accent": accent, "accent2": by[2],
            "muted": "#a8adb8", "line": deep}


def _host(url: str) -> str:
    from urllib.parse import urlparse
    return (urlparse(url).hostname or "").removeprefix("www.")


def _img(path) -> str:
    return '<img src="' + Path(path).as_uri() + '">'


def _esc(s: Any) -> str:
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------- offline planner (mock mode / tests)
def _mock_concepts(cast: list, ft: dict) -> dict:
    h = [f"@{a.handle}" for a in cast] or ["@actor"]
    mk = lambda cid, name, pal: {"id": cid, "name": name, "idea": f"{name} idea", "slogan": f"{name}: made for busy days",  # noqa: E731
                                 "tone": "warm", "keywords": ["city", "travel", "calm", "light", "easy"], "palette": pal,
                                 "lighting": "soft morning light", "music": "light acoustic guitar, 96 bpm",
                                 "mood_prompts": ["empty tram at dawn", "linen texture close-up", "airport window light", "folded shirt on a bed"],
                                 "preview": [{"prompt": f"{h[0]} walks out of a hotel lobby wearing the product, tracking shot"},
                                             {"prompt": f"{h[-1]} smiles at {h[0]} in a sunny cafe, the product visible"}]}
    return {"concepts": [mk("A", "City Rhythm", ["#1d2433", "#2b3550", "#e8b04b", "#f4f1ea", "#8a93a6"]),
                         mk("B", "Carry-on Calm", ["#20302b", "#2f4a40", "#d98b5f", "#f2efe6", "#9aa59d"]),
                         mk("C", "Night to Morning", ["#151226", "#2a2346", "#ff8a5c", "#f6f0ff", "#8c86a8"])]}


def _mock_copy(cast: list, ft: dict, concept: dict, length: float) -> dict:
    h = [f"@{a.handle}" for a in cast] or ["narrator"]
    fid = [f["id"] for f in ft.get("facts", [])][:2] or ["f1"]
    edges = [0, 3, 12, 25, 45, 55, length]
    outline = [{"beat": b, "start": edges[i], "end": edges[i + 1], "purpose": BEAT_ZH[b],
                "lines": [{"speaker": h[i % len(h)], "text": f"Line for {b}."}]} for i, b in enumerate(BEATS)]
    return {"headline": concept.get("slogan") or "Made for busy days", "sub": ft.get("name", ""), "cta": "Shop now",
            "url_label": "", "supers": [{"beat": "reveal", "text": "Easy-care"}], "outline": outline,
            "claims": [{"text": "Easy-care", "fact_ids": fid}], "social": ["post 1", "post 2", "post 3"], "hashtags": []}


def _mock_board(cast: list, copy: dict, length: float) -> dict:
    h = [f"@{a.handle}" for a in cast] or []
    shots = []
    for i, b in enumerate(copy.get("outline", [])):
        if b["beat"] == "cta":
            continue
        for j in range(2):
            ln = (b.get("lines") or [None])[0] if j == 0 else None
            shots.append({"beat": b["beat"], "duration": (b["end"] - b["start"]) / 2, "shot_size": "MS", "angle": "eye level",
                          "movement": "push-in", "lens": "35mm", "lighting": "soft", "color": "warm", "transition": "cut",
                          "actors": h[: 1 + (i % 2)], "product_visible": b["beat"] in ("reveal", "demo"),
                          "line": ln, "super": "Easy-care" if b["beat"] == "reveal" and j == 0 else "",
                          "prompt": f"{' and '.join(h[: 1 + (i % 2)])} in a city street, the product visible"})
    shots.append({"kind": "endcard", "beat": "cta", "duration": 4.5})
    return {"shots": shots}
