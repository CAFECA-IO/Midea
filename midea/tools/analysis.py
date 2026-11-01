"""Analysis tools: probing, shot detection, black/freeze detection, motion & slideshow risk."""
from __future__ import annotations

import re
from pathlib import Path

from ..media import ff
from .registry import tool


@tool("analysis.probe", "analysis", tags=["qa"])
def probe(src: str) -> dict:
    """ffprobe summary: container, duration, video/audio codecs, resolution, fps, bitrate."""
    info = ff.probe(src)
    fmt = info.get("format", {})
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    def fps(s: dict | None) -> float:
        if not s:
            return 0.0
        n, d = (s.get("avg_frame_rate") or "0/1").split("/")
        return round(float(n) / float(d), 3) if float(d) else 0.0
    return {
        "format": fmt.get("format_name"), "duration": float(fmt.get("duration", 0) or 0),
        "size_bytes": int(fmt.get("size", 0) or 0), "bit_rate": int(fmt.get("bit_rate", 0) or 0),
        "video": v and {"codec": v.get("codec_name"), "profile": v.get("profile"), "width": v.get("width"),
                        "height": v.get("height"), "fps": fps(v), "pix_fmt": v.get("pix_fmt"),
                        "duration": float(v.get("duration", 0) or 0), "sar": v.get("sample_aspect_ratio")},
        "audio": a and {"codec": a.get("codec_name"), "sample_rate": int(a.get("sample_rate", 0)),
                        "channels": a.get("channels"), "duration": float(a.get("duration", 0) or 0)},
        "subtitle_streams": sum(1 for s in info["streams"] if s["codec_type"] == "subtitle"),
    }


@tool("analysis.scenes", "analysis")
def scenes(src: str, threshold: float = 0.32) -> list[float]:
    """Shot-cut timestamps via scene-change score."""
    err = ff.run_capture(["-i", src, "-vf", f"select='gt(scene,{threshold})',showinfo", "-an", "-f", "null", "-"])
    return [round(float(x), 3) for x in re.findall(r"pts_time:([0-9.]+)", err)]


@tool("analysis.black_frames", "analysis", tags=["qa"])
def black_frames(src: str, min_d: float = 0.1, pix_th: float = 0.10) -> list[dict]:
    """Spans of black picture (blackdetect)."""
    err = ff.run_capture(["-i", src, "-vf", f"blackdetect=d={min_d}:pix_th={pix_th}", "-an", "-f", "null", "-"])
    return [{"start": float(a), "end": float(b), "duration": float(c)}
            for a, b, c in re.findall(r"black_start:([0-9.]+) black_end:([0-9.]+) black_duration:([0-9.]+)", err)]


@tool("analysis.freezes", "analysis", tags=["qa"])
def freezes(src: str, min_d: float = 2.0, noise: float = 0.003) -> list[dict]:
    """Frozen-picture spans (freezedetect) — catches stalled renders and 'slideshow' stills."""
    err = ff.run_capture(["-i", src, "-vf", f"freezedetect=n={noise}:d={min_d}", "-an", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"freeze_start: ([0-9.]+)", err)]
    durs = [float(x) for x in re.findall(r"freeze_duration: ([0-9.]+)", err)]
    return [{"start": s, "duration": d} for s, d in zip(starts, durs)]


@tool("analysis.motion_profile", "analysis", tags=["qa"])
def motion_profile(src: str, sample_fps: float = 4) -> dict:
    """Mean inter-frame difference over time (low ⇒ static / slideshow risk)."""
    err = ff.run_capture(["-i", src, "-vf", f"fps={sample_fps},scale=320:-2,format=gray,"
                          "tblend=all_mode=difference,signalstats,metadata=print:key=lavfi.signalstats.YAVG",
                          "-an", "-f", "null", "-"])
    vals = [float(x) for x in re.findall(r"lavfi\.signalstats\.YAVG=([0-9.]+)", err)]
    if not vals:
        return {"mean": 0.0, "static_ratio": 1.0, "samples": 0}
    static = sum(1 for v in vals if v < 0.6) / len(vals)
    return {"mean": round(sum(vals) / len(vals), 3), "static_ratio": round(static, 3), "samples": len(vals)}


@tool("analysis.frame_stats", "analysis", tags=["qa"])
def frame_stats(image: str) -> dict:
    """Brightness, saturation and sharpness proxy for a single frame."""
    err = ff.run_capture(["-i", image, "-vf", "signalstats,metadata=print", "-f", "null", "-"])
    def g(k: str) -> float:
        m = re.search(rf"lavfi\.signalstats\.{k}=([0-9.]+)", err)
        return float(m.group(1)) if m else 0.0
    edge = ff.run_capture(["-i", image, "-vf", "format=gray,edgedetect=low=0.1:high=0.3,signalstats,metadata=print",
                           "-f", "null", "-"])
    m = re.search(r"lavfi\.signalstats\.YAVG=([0-9.]+)", edge)
    return {"luma": g("YAVG"), "luma_min": g("YMIN"), "luma_max": g("YMAX"), "saturation": g("SATAVG"),
            "edge_density": float(m.group(1)) if m else 0.0}


@tool("analysis.sample_frames", "analysis", tags=["qa"])
def sample_frames(src: str, out_dir: str, positions: tuple[float, ...] = (0.05, 0.35, 0.65, 0.95)) -> list[str]:
    """Extract frames at relative positions (default 4 positions, as in post-render review)."""
    d = ff.duration(src)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out = []
    for i, p in enumerate(positions):
        f = Path(out_dir) / f"qa_{i}_{int(p*100):02d}.jpg"
        ff.run(["-ss", f"{max(0, d * p - 0.02):.3f}", "-i", src, "-frames:v", "1", "-q:v", "3", f])
        out.append(str(f))
    return out


@tool("analysis.aspect", "analysis")
def aspect(src: str) -> str:
    """Classify aspect as 16:9, 9:16, 1:1, 4:5 or WxH."""
    v = ff.video_stream(src) or {}
    w, h = int(v.get("width", 0)), int(v.get("height", 0))
    if not w or not h:
        return "unknown"
    r = w / h
    for name, val in {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1, "4:5": 0.8, "21:9": 21 / 9}.items():
        if abs(r - val) < 0.03:
            return name
    return f"{w}x{h}"


@tool("analysis.dominant_colors", "analysis")
def dominant_colors(image: str, n: int = 5) -> list[str]:
    """Approximate dominant colours (palette extraction for style matching)."""
    import subprocess
    raw = subprocess.run([ff.FFMPEG, "-v", "error", "-i", image, "-vf", "scale=32:32", "-f", "rawvideo", "-pix_fmt",
                          "rgb24", "-"], capture_output=True).stdout
    buckets: dict[tuple, int] = {}
    for i in range(0, len(raw) - 2, 3):
        k = (raw[i] // 32 * 32, raw[i + 1] // 32 * 32, raw[i + 2] // 32 * 32)
        buckets[k] = buckets.get(k, 0) + 1
    top = sorted(buckets.items(), key=lambda kv: -kv[1])[:n]
    return ["#%02x%02x%02x" % k for k, _ in top]
