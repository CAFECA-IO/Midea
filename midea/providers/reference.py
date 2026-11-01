"""Reference-video analysis for YouTube Shorts / Instagram Reels / TikTok links.

Pipeline: yt-dlp download → shot-cut detection → keyframe sampling → ASR →
loudness/tempo stats → Qwen (vision) describes the *template* (beats, pacing,
caption style) so it can be re-applied to a new topic.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from ..config import settings
from ..log import get_logger
from ..media import ff
from .. import prompts
from . import asr
from .llm import llm

log = get_logger("reference")
SUPPORTED = re.compile(r"(youtube\.com/shorts|youtu\.be|youtube\.com/watch|instagram\.com/(reel|p)|tiktok\.com)", re.I)


def download(url: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / "reference.mp4"
    if out.exists():
        return out
    if settings().mode == "mock" or url.startswith("mock://"):
        srcs = ["testsrc2", "smptehdbars", "rgbtestsrc", "testsrc2", "smptebars", "rgbtestsrc"]      # 6 shots → 5 cuts
        durs = [2.0, 2.5, 3.0, 2.0, 2.5, 3.0]
        ins: list = []
        for s_, d_ in zip(srcs, durs):
            ins += ["-f", "lavfi", "-i", f"{s_}=s=720x1280:r=30:d={d_}"]
        ins += ["-f", "lavfi", "-i", "sine=f=330:d=15:sample_rate=48000"]
        fc = "".join(f"[{i}:v]setsar=1,hue=h={i*60}[v{i}];" for i in range(6)) + "".join(f"[v{i}]" for i in range(6)) + "concat=n=6:v=1:a=0[v]"
        ff.run([*ins, "-filter_complex", fc, "-map", "[v]", "-map", "6:a", "-shortest", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", "-preset", "ultrafast", out])
        return out
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        raise RuntimeError("yt-dlp is required for reference links: pip install yt-dlp")
    subprocess.run([ytdlp, "-f", "bv*[height<=1920]+ba/b", "--merge-output-format", "mp4", "-o", str(out), url],
                   check=True)
    return out


def detect_cuts(video: Path, threshold: float = 0.32) -> list[float]:
    log_ = ff.run_capture(["-i", video, "-vf", f"select='gt(scene,{threshold})',showinfo", "-an", "-f", "null", "-"])
    cuts = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", log_)]
    merged: list[float] = []
    for c in cuts:                       # drop cuts closer than 0.25 s (flashes)
        if not merged or c - merged[-1] > 0.25:
            merged.append(round(c, 3))
    return merged


def sample_keyframes(video: Path, times: list[float], dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, t in enumerate(times):
        p = dest / f"kf_{i:02d}.jpg"
        ff.run(["-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-vf", "scale=512:-2", "-q:v", "3", p])
        paths.append(p)
    return paths


def analyze(url: str, workdir: Path) -> dict:
    video = download(url, workdir)
    info = ff.video_stream(video) or {}
    w, h = int(info.get("width", 0)), int(info.get("height", 0))
    dur = ff.duration(video)
    aspect = "9:16" if h > w else ("1:1" if h == w else "16:9")
    cuts = detect_cuts(video)
    edges = [0.0, *cuts, dur]
    mids = [(edges[i] + edges[i + 1]) / 2 for i in range(len(edges) - 1)][:16]
    frames = sample_keyframes(video, mids, workdir / "keyframes")
    transcript = asr.transcribe(video)
    shots = len(edges) - 1
    stats = {"duration_s": round(dur, 2), "aspect": aspect, "shot_count": shots, "cuts": cuts,
             "avg_shot_s": round(dur / max(1, shots), 2), "transcript": transcript["text"]}
    user = (f"Shot cut times (s): {cuts}\nDuration: {dur:.2f}s, aspect {aspect}, {shots} shots, "
            f"average shot {stats['avg_shot_s']}s.\nTranscript: {transcript['text'][:4000]}\n"
            f"Keyframes are attached in shot order.")
    llm_out = llm().json("reference", prompts.REFERENCE, user, images=frames, context=stats)
    return {"source_url": url, **stats, **llm_out, "keyframes": [str(p) for p in frames], "video": str(video)}
