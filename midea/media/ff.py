"""Thin, safe wrappers around ffmpeg / ffprobe."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from ..log import get_logger

log = get_logger("ff")
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


class FFError(RuntimeError):
    pass


def run(args: Sequence[str | Path], *, quiet: bool = True, timeout: float | None = None) -> str:
    cmd = [FFMPEG, "-hide_banner", "-y", *(["-loglevel", "error"] if quiet else []), *map(str, args)]
    log.debug("ffmpeg %s", " ".join(cmd[1:]))
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise FFError(f"ffmpeg failed ({p.returncode}): {p.stderr.strip()[-2000:]}\ncmd: {' '.join(cmd)}")
    return p.stderr


def run_capture(args: Sequence[str | Path], timeout: float | None = None) -> str:
    """Run ffmpeg and return stderr (for filters that report via log, e.g. ebur128, blackdetect)."""
    cmd = [FFMPEG, "-hide_banner", "-nostats", *map(str, args)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise FFError(p.stderr[-2000:])
    return p.stderr


def probe(path: str | Path) -> dict:
    p = subprocess.run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise FFError(f"ffprobe failed for {path}: {p.stderr.strip()}")
    return json.loads(p.stdout)


def duration(path: str | Path) -> float:
    info = probe(path)
    d = info.get("format", {}).get("duration")
    if d is None:
        ds = [float(s["duration"]) for s in info.get("streams", []) if s.get("duration")]
        return max(ds) if ds else 0.0
    return float(d)


def has_audio(path: str | Path) -> bool:
    return any(s.get("codec_type") == "audio" for s in probe(path).get("streams", []))


def video_stream(path: str | Path) -> dict | None:
    return next((s for s in probe(path).get("streams", []) if s.get("codec_type") == "video"), None)


def audio_stream(path: str | Path) -> dict | None:
    return next((s for s in probe(path).get("streams", []) if s.get("codec_type") == "audio"), None)


def esc_filter_path(p: str | Path) -> str:
    """Escape a path for use inside an ffmpeg filter argument (subtitles=, movie=...)."""
    s = str(Path(p).resolve())
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")


def esc_text(t: str) -> str:
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%").replace(",", "\\,")
