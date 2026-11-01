"""Data contracts passed between stages (validated with pydantic)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

VisualKind = Literal["h3_t2v", "h3_i2v", "h3_r2v", "stock_video", "stock_image", "motion", "title_card", "user_media"]


class _M(BaseModel):
    model_config = ConfigDict(extra="allow")


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


class ScriptSection(_M):
    id: str
    heading: str = ""
    narration: str
    on_screen_text: str = ""
    est_duration_s: float = 8


class Script(_M):
    title: str
    language: str = "zh-TW"
    hook: str = ""
    sections: list[ScriptSection]
    cta: str = ""


class Visual(_M):
    kind: VisualKind = "h3_t2v"
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
