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
    if settings().mocked("whisper"):
        return {"text": "", "language": language or "zh", "segments": []}
    global _model
    with scheduler().lease("whisper"):
        if _model is None:
            from faster_whisper import WhisperModel
            name = settings().get("services.whisper.model", "large-v3")
            _model = WhisperModel(name, device="cuda", compute_type="float16")
        lang = (language or "").split("-")[0] or None
        # decode with ffmpeg ourselves (16 kHz mono float32) — avoids PyAV API drift inside faster-whisper
        import numpy as np
        import subprocess
        from ..media import ff
        pcm = subprocess.run([ff.FFMPEG, "-v", "error", "-i", str(path), "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                             capture_output=True, check=True).stdout
        audio = np.frombuffer(pcm, dtype=np.float32)
        hint = {"zh-TW": "以下是繁體中文的句子。", "zh-HK": "以下是繁體中文的句子。", "zh-CN": "以下是简体中文的句子。"}
        segs, info = _model.transcribe(audio, language=lang, word_timestamps=True, vad_filter=False, condition_on_previous_text=False,
                                       initial_prompt=hint.get(language or ""))
        out = []
        for s in segs:
            out.append({"start": s.start, "end": s.end, "text": s.text.strip(),
                        "words": [{"start": w.start, "end": w.end, "word": w.word} for w in (s.words or [])]})
    return {"text": " ".join(s["text"] for s in out), "language": info.language, "segments": out}
