"""Speech recognition with word timestamps (faster-whisper, in-process)."""
from __future__ import annotations

from pathlib import Path

from ..config import settings
from ..gpu import scheduler
from ..log import get_logger

log = get_logger("asr")
_model = None


def transcribe(path: str | Path, language: str | None = None) -> dict:
    """Return {"text", "language", "segments":[{start,end,text,words:[{start,end,word}]}]}."""
    if settings().mode == "mock":
        return {"text": "", "language": language or "zh", "segments": []}
    global _model
    with scheduler().lease("whisper"):
        if _model is None:
            from faster_whisper import WhisperModel
            name = settings().get("services.whisper.model", "large-v3")
            _model = WhisperModel(name, device="cuda", compute_type="float16")
        lang = (language or "").split("-")[0] or None
        segs, info = _model.transcribe(str(path), language=lang, word_timestamps=True, vad_filter=True)
        out = []
        for s in segs:
            out.append({"start": s.start, "end": s.end, "text": s.text.strip(),
                        "words": [{"start": w.start, "end": w.end, "word": w.word} for w in (s.words or [])]})
    return {"text": " ".join(s["text"] for s in out), "language": info.language, "segments": out}
