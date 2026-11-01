"""Generative-model tools (local GPU) and real-footage tools, exposed through the registry."""
from __future__ import annotations

from pathlib import Path

from ..providers import audio as A
from ..providers import reference as R
from ..providers import stock as S
from ..providers.asr import transcribe
from ..providers.llm import llm
from ..providers.video_h3 import h3
from .registry import tool


def _h3_secs(seconds: float = 6, **_) -> float:          # rough wall-clock per H3 shot on one 48 GB card
    return 90 + 40 * float(seconds)


@tool("gen.h3_t2v", "generate", service="h3", est_seconds=_h3_secs)
def h3_t2v(prompt: str, out: str, seconds: int = 6, aspect: str = "16:9", seed: int | None = None) -> str:
    """MiniMax H3 text→video (4–15 s, 24 fps, native audio)."""
    return str(h3().generate(prompt, Path(out), seconds=seconds, aspect=aspect, mode="t2v", seed=seed))


@tool("gen.h3_i2v", "generate", service="h3", est_seconds=_h3_secs)
def h3_i2v(prompt: str, first_frame: str, out: str, seconds: int = 6, aspect: str = "16:9",
           last_frame: str | None = None, seed: int | None = None) -> str:
    """MiniMax H3 image→video with optional last-frame target (shot continuity)."""
    return str(h3().generate(prompt, Path(out), seconds=seconds, aspect=aspect, mode="i2v",
                             first_frame=first_frame, last_frame=last_frame, seed=seed))


@tool("gen.h3_r2v", "generate", service="h3", est_seconds=_h3_secs)
def h3_r2v(prompt: str, refs: list[str], out: str, seconds: int = 6, aspect: str = "16:9", seed: int | None = None) -> str:
    """MiniMax H3 reference→video (≤9 reference images: character / product consistency)."""
    return str(h3().generate(prompt, Path(out), seconds=seconds, aspect=aspect, mode="r2v", ref_images=refs, seed=seed))


@tool("gen.tts", "generate", service="voxcpm", est_seconds=lambda text="", **_: 2 + A.estimate_speech_seconds(text) * 0.5)
def tts(text: str, out: str, voice: str | None = None) -> str:
    """VoxCPM2 narration (48 kHz)."""
    return str(A.tts(text, Path(out), voice=voice))


@tool("gen.voice_design", "generate", service="voxcpm")
def voice_design(text: str, description: str, out: str) -> str:
    """VoxCPM2 voice design from a natural-language description, e.g. '(young woman, bright, fast)'."""
    return str(A.tts(text, Path(out), voice=description))


@tool("gen.voice_clone", "generate", service="voxcpm")
def voice_clone(text: str, reference_wav: str, out: str, style: str | None = None) -> str:
    """VoxCPM2 voice cloning from a 5–15 s clean reference recording (with consent)."""
    return str(A.tts(text, Path(out), voice=style, reference_wav=reference_wav))


@tool("gen.music", "generate", service="acestep", est_seconds=lambda seconds=60, **_: 10 + float(seconds) * 0.15)
def music(prompt: str, seconds: float, out: str, bpm: int | None = None, instrumental: bool = True,
          lyrics: str = "") -> str:
    """ACE-Step 1.5 music bed or song (10 s – 10 min)."""
    return str(A.music(prompt, seconds, Path(out), bpm=bpm, instrumental=instrumental, lyrics=lyrics))


@tool("gen.sfx", "generate", service="sfx", est_seconds=lambda **_: 15)
def sfx(prompt: str, seconds: float, out: str) -> str:
    """Stable Audio Open text→sound effect (whooshes, ambiences, UI sounds)."""
    return str(A.sfx(prompt, seconds, Path(out)))


@tool("gen.foley", "generate", service="foley", est_seconds=lambda **_: 120)
def foley(video: str, out: str, prompt: str = "") -> str:
    """HunyuanVideo-Foley: synchronised Foley/ambience generated from the picture."""
    return str(A.foley(Path(video), prompt, Path(out)))


@tool("llm.json", "plan", service="qwen")
def llm_json(task: str, system: str, user: str) -> dict:
    """Ask Qwen3.8-Flash-Next for structured JSON."""
    return llm().json(task, system, user)


@tool("asr.transcribe", "analysis", service="whisper")
def asr(src: str, language: str | None = None) -> dict:
    """faster-whisper transcription with word timestamps."""
    return transcribe(src, language)


def _stock_tool(src: str):
    def fn(query: str, kind: str = "video", limit: int = 6) -> list[dict]:
        return [c.to_dict() for c in S.SOURCES[src](query, kind, limit)]
    fn.__doc__ = f"Search {src.replace('_', '.')} for real footage/photos (licence + attribution included)."
    fn.__name__ = f"search_{src}"
    tool(f"stock.{src}", "stock")(fn)


for _s in S.SOURCES:
    _stock_tool(_s)


@tool("stock.search", "stock")
def stock_search(query: str, kind: str = "video", sources: list[str] | None = None, limit: int = 6) -> list[dict]:
    """Federated search across all enabled open/free libraries with licence filtering."""
    return [c.to_dict() for c in S.search(query, kind, sources, limit)]


@tool("stock.download", "stock")
def stock_download(candidate: dict, dest_dir: str) -> str:
    """Download a stock candidate into the project cache."""
    return str(S.download(S.Candidate(**candidate), Path(dest_dir)))


@tool("reference.download", "reference")
def ref_download(url: str, dest_dir: str) -> str:
    """Download a Shorts/Reels/TikTok reference with yt-dlp."""
    return str(R.download(url, Path(dest_dir)))


@tool("reference.analyze", "reference")
def ref_analyze(url: str, workdir: str) -> dict:
    """Reverse-engineer a reference's pacing, beats, shot list and caption style."""
    return R.analyze(url, Path(workdir))


@tool("reference.cuts", "reference")
def ref_cuts(src: str, threshold: float = 0.32) -> list[float]:
    """Shot cut times of a reference video."""
    return R.detect_cuts(Path(src), threshold)
