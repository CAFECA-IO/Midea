"""Data contracts passed between stages (validated with pydantic)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VisualKind = Literal["h3_t2v", "h3_i2v", "h3_r2v", "stock_video", "stock_image", "motion", "title_card", "user_media"]


class _M(BaseModel):
    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, v):        # LLMs emit null for "not applicable" — let field defaults apply instead
        return {k: x for k, x in v.items() if x is not None} if isinstance(v, dict) else v


class Brief(_M):
    prompt: str
    pipeline: str = "auto"
    duration_s: float = 60
    aspect: str = "16:9"
    language: str = "zh-TW"
    real_only: bool = False                 # 只用真實素材（紀錄片模式）
    reference_url: Optional[str] = None     # Shorts / Reels / TikTok 參考影片
    style: Optional[str] = None
    voice: Optional[str] = None             # VoxCPM2 聲音設計描述，或 reference wav 路徑
    music: bool = True
    subtitles: bool = True
    burn_subtitles: bool = True
    user_media: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)   # 虛擬演員 id（由 @handle 解析）


class Proposal(_M):
    title: str
    logline: str
    audience: str = "general"
    tone: str = "informative"
    style: str = "clean"
    duration_s: float = 60
    aspect: str = "16:9"
    language: str = "zh-TW"
    renderer: Literal["h3", "stock", "motion", "hybrid"] = "hybrid"
    music_mood: str = "uplifting ambient"
    outline: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    @field_validator("renderer", mode="before")
    @classmethod
    def _renderer(cls, v):
        v = str(v or "").lower()
        for k in ("stock", "motion", "h3", "hybrid"):
            if k in v:
                return k
        return "hybrid"

    @field_validator("outline", "risks", mode="before")
    @classmethod
    def _flatten(cls, v):          # LLMs sometimes return [{beat, visual, ...}] instead of strings
        if isinstance(v, str):
            return [v]
        out = []
        for x in v or []:
            if isinstance(x, dict):
                head = x.get("beat") or x.get("title") or x.get("name") or ""
                rest = "；".join(str(val) for k, val in x.items() if k not in ("beat", "title", "name") and isinstance(val, (str, int, float)))
                out.append(f"{head}：{rest}" if head and rest else head or rest)
            else:
                out.append(str(x))
        return out


class ScriptSection(_M):
    id: str
    heading: str = ""
    narration: str
    on_screen_text: str = ""
    est_duration_s: float = 8
    speaker: str = ""                       # "@handle" = 該演員以自己的聲音說這段；空 / narrator = 旁白


class Script(_M):
    title: str
    language: str = "zh-TW"
    hook: str = ""
    sections: list[ScriptSection]
    cta: str = ""


class Visual(_M):
    kind: VisualKind = "h3_t2v"

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, v):
        v = str(v or "").lower().strip()
        alias = {"h3": "h3_t2v", "t2v": "h3_t2v", "i2v": "h3_i2v", "r2v": "h3_r2v", "stock": "stock_video",
                 "archival": "stock_video", "photo": "stock_image", "image": "stock_image", "title": "title_card",
                 "motion_graphics": "motion", "animation": "motion"}
        valid = ("h3_t2v", "h3_i2v", "h3_r2v", "stock_video", "stock_image", "motion", "title_card", "user_media")
        return v if v in valid else alias.get(v, "motion")

    prompt: str = ""
    query: str = ""                         # 素材庫搜尋字串
    sources: list[str] = Field(default_factory=list)
    template: str = ""                      # motion 範本名稱
    params: dict = Field(default_factory=dict)
    camera: str = ""


class SFX(_M):
    prompt: str
    at: float = 0.0
    duration: float = 1.5
    gain_db: float = -8


class Scene(_M):
    id: str
    section_id: str = ""
    duration_s: float
    narration: str = ""
    on_screen_text: str = ""
    visual: Visual
    transition: dict = Field(default_factory=lambda: {"type": "fade", "duration": 0.4})
    sfx: list[SFX] = Field(default_factory=list)
    foley: bool = False
    music_cue: str = ""
    actors: list[str] = Field(default_factory=list)   # 畫面中出現的演員（@handle → 由 runner 轉為 id）
    speaker: str = ""                                  # 誰說這段 narration（@handle 或 narrator）
    lipsync: bool = False                              # 實驗：演員在畫面中親口說台詞（H3 以台詞音訊為 <Audio 1> 參考對嘴）

    @field_validator("actors", mode="before")
    @classmethod
    def _actors(cls, v):
        if isinstance(v, str):
            return [x for x in v.replace("，", ",").split(",") if x.strip()]
        return [str(x.get("handle") or x.get("name") or "") if isinstance(x, dict) else str(x) for x in (v or [])]

    @field_validator("foley", mode="before")
    @classmethod
    def _foley(cls, v):             # accept a description string as "yes, add foley"
        if isinstance(v, str):
            return v.strip().lower() not in ("", "false", "no", "none", "0")
        return bool(v)


class ScenePlan(_M):
    scenes: list[Scene]
    music: dict = Field(default_factory=dict)   # {"prompt": ..., "bpm": ..., "instrumental": true}
    voice: dict = Field(default_factory=dict)


class ReferenceAnalysis(_M):
    source_url: str = ""
    duration_s: float
    aspect: str
    shot_count: int
    avg_shot_s: float
    cuts: list[float]
    pacing: str
    hook: str = ""
    structure: list[dict] = Field(default_factory=list)   # [{beat, start, end, purpose, visual_style, text_style}]
    style_notes: list[str] = Field(default_factory=list)
    transcript: str = ""
    music: str = ""
    caption_style: str = ""
