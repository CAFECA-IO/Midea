"""Subtitle building, ASR alignment, styling and burn-in."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from ..config import settings
from ..media import ff
from .registry import tool

CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
PUNCT_BREAK = re.compile(r"(?<=[。！？!?；;])|(?<=[，、,:：])")


def is_cjk(text: str) -> bool:
    return len(CJK.findall(text)) > len(text) * 0.3


def _fmt(t: float, sep: str = ",") -> str:
    t = max(0.0, t)
    h, rem = divmod(int(round(t * 1000)), 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _units(text: str) -> int:
    return len(CJK.findall(text)) + len(re.findall(r"[A-Za-z0-9']+", text)) * (1 if is_cjk(text) else 5)


def limits(text: str) -> tuple[int, float]:
    q = settings().get("qa", {}) or {}
    if is_cjk(text):
        return int(q.get("subtitle_max_chars_line_cjk", 18)), float(q.get("subtitle_max_cps_cjk", 9))
    return int(q.get("subtitle_max_chars_line", 42)), float(q.get("subtitle_max_cps", 17))


@tool("subtitle.split", "subtitle")
def split_text(text: str, max_chars: int | None = None) -> list[str]:
    """Split narration into cue-sized chunks at punctuation, respecting max chars per line."""
    max_chars = max_chars or limits(text)[0]
    pieces: list[str] = []
    for p in (x.strip() for x in PUNCT_BREAK.split(text)):
        if not p:
            continue
        if pieces and not re.search(r"[\w\u3400-\u9fff]", p):     # punctuation-only → glue to previous
            pieces[-1] += p
        else:
            pieces.append(p)
    chunks: list[str] = []
    cur = ""
    for p in pieces:
        sep = "" if (not cur or is_cjk(cur + p)) else " "            # latin pieces keep their word space
        if len(cur + sep + p) <= max_chars:
            cur += sep + p
            continue
        if cur:
            chunks.append(cur)
        while len(p) > max_chars:
            if is_cjk(p):
                chunks.append(p[:max_chars]); p = p[max_chars:]
            else:
                cut = p.rfind(" ", 0, max_chars)
                cut = cut if cut > 0 else max_chars
                chunks.append(p[:cut].strip()); p = p[cut:].strip()
        cur = p
    if cur:
        chunks.append(cur)
    # strip trailing soft punctuation in CJK cues (house style)
    chunks = [re.sub(r"[，、。]+$", "", c) if is_cjk(c) else c for c in chunks]
    return [c for c in chunks if re.search(r"[\w\u3400-\u9fff]", c)]


@tool("subtitle.cues_from_spans", "subtitle")
def cues_from_spans(spans: Sequence[dict]) -> list[dict]:
    """spans=[{start,end,text}] (one per narration clip) → timed cues, time split by character weight."""
    cues = []
    for sp in spans:
        parts = split_text(sp["text"])
        if not parts:
            continue
        total = sum(max(1, _units(p)) for p in parts)
        t = float(sp["start"])
        span = float(sp["end"]) - t
        for p in parts:
            d = span * max(1, _units(p)) / total
            cues.append({"start": round(t, 3), "end": round(t + d - 0.04, 3), "text": p})
            t += d
    for a, b in zip(cues, cues[1:]):     # guarantee no overlap between consecutive cues
        if a["end"] > b["start"] - 0.04:
            a["end"] = round(max(a["start"] + 0.3, b["start"] - 0.04), 3)
    # merge cues too short to read into their neighbour (same span only)
    merged: list[dict] = []
    for c in cues:
        if merged and (c["end"] - c["start"] < 0.8 or merged[-1]["end"] - merged[-1]["start"] < 0.8) \
                and c["start"] - merged[-1]["end"] < 0.1 and len(merged[-1]["text"] + c["text"]) <= 2 * limits(c["text"])[0]:
            merged[-1] = {**merged[-1], "end": c["end"], "text": merged[-1]["text"] + ("" if is_cjk(c["text"]) else " ") + c["text"]}
        else:
            merged.append(c)
    return merged


@tool("subtitle.align_to_words", "subtitle", tags=["asr"])
def align_to_words(cues: Sequence[dict], words: Sequence[dict]) -> list[dict]:
    """Snap cue boundaries to ASR word timestamps.

    Global character alignment (difflib) between the script text and the ASR stream, so a few
    mis-heard words never derail the cues that follow. zh-TW/zh-CN are compared in one script.
    """
    import difflib
    if not words:
        return list(cues)
    try:                                   # Whisper often answers zh-TW audio in Simplified: compare in one script
        from opencc import OpenCC
        _cc = OpenCC("t2s").convert
    except Exception:  # noqa: BLE001
        _cc = lambda s: s  # noqa: E731
    strip = re.compile(r"[\s，。！？、,.!?;:：；\"'「」『』（）()…—\-]")
    norm = lambda s: _cc(strip.sub("", s).lower())  # noqa: E731
    asr_chars, asr_t = [], []
    for w in words:
        tok = norm(w["word"])
        n = max(1, len(tok))
        for k, ch in enumerate(tok):                       # spread a word's span over its characters
            t0 = w["start"] + (w["end"] - w["start"]) * k / n
            asr_chars.append(ch)
            asr_t.append((t0, w["start"] + (w["end"] - w["start"]) * (k + 1) / n))
    cue_chars, owner = [], []
    for ci, c in enumerate(cues):
        for ch in norm(c["text"]):
            cue_chars.append(ch)
            owner.append(ci)
    sm = difflib.SequenceMatcher(None, "".join(cue_chars), "".join(asr_chars), autojunk=False)
    hits: dict[int, list[tuple[float, float]]] = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            hits.setdefault(owner[blk.a + k], []).append(asr_t[blk.b + k])
    out = []
    for ci, c in enumerate(cues):
        n = max(1, len(norm(c["text"])))
        h = hits.get(ci, [])
        if len(h) >= 0.4 * n:
            out.append({**c, "start": round(h[0][0], 3), "end": round(h[-1][1], 3), "aligned": True})
        else:
            out.append({**c, "aligned": False})
    for i in range(len(out) - 1):                          # monotonic, non-overlapping, readable
        a, b = out[i], out[i + 1]
        if b["start"] < a["start"] + 0.3:
            b["start"] = round(a["start"] + 0.3, 3)
        if a["end"] > b["start"] - 0.04:
            a["end"] = round(b["start"] - 0.04, 3)
    for i, c in enumerate(out):                            # hold each cue long enough to read (into the gap after it)
        max_line, max_cps = limits(c["text"])
        units = len(strip.sub("", c["text"]))
        want = c["start"] + max(1.0, units / max_cps)
        limit = out[i + 1]["start"] - 0.04 if i + 1 < len(out) else want
        if c["end"] < want:
            c["end"] = round(max(c["end"], min(want, limit), c["start"] + 0.7), 3)
    for i in range(len(out) - 1):
        if out[i]["end"] > out[i + 1]["start"] - 0.04:
            out[i + 1]["start"] = round(out[i]["end"] + 0.04, 3)
            out[i + 1]["end"] = max(out[i + 1]["end"], round(out[i + 1]["start"] + 0.6, 3))
    return out


@tool("subtitle.write_srt", "subtitle")
def write_srt(cues: Sequence[dict], out: str) -> str:
    """Write SubRip (.srt)."""
    lines = []
    for n, c in enumerate(cues, 1):
        lines += [str(n), f"{_fmt(c['start'])} --> {_fmt(c['end'])}", c["text"], ""]
    Path(out).write_text("\n".join(lines), encoding="utf-8")
    return out


@tool("subtitle.write_vtt", "subtitle")
def write_vtt(cues: Sequence[dict], out: str) -> str:
    """Write WebVTT (.vtt)."""
    lines = ["WEBVTT", ""]
    for c in cues:
        lines += [f"{_fmt(c['start'], '.')} --> {_fmt(c['end'], '.')}", c["text"], ""]
    Path(out).write_text("\n".join(lines), encoding="utf-8")
    return out


@tool("subtitle.read_srt", "subtitle")
def read_srt(path: str) -> list[dict]:
    """Parse an .srt file."""
    def t(s: str) -> float:
        h, m, rest = s.strip().replace(".", ",").split(":")
        sec, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000
    cues = []
    for block in re.split(r"\n\s*\n", Path(path).read_text(encoding="utf-8").strip()):
        ls = block.strip().splitlines()
        if len(ls) >= 3 and "-->" in ls[1]:
            a, b = ls[1].split("-->")
            cues.append({"start": t(a), "end": t(b), "text": "\n".join(ls[2:])})
    return cues


ASS_STYLES = {
    "clean": dict(size=0.05, primary="&H00FFFFFF", outline="&H00000000", back="&H64000000", bold=0, border=1, ol=3, sh=0, mv=0.08),
    "boxed": dict(size=0.045, primary="&H00FFFFFF", outline="&H96000000", back="&H96000000", bold=0, border=3, ol=8, sh=0, mv=0.08),
    "shorts": dict(size=0.06, primary="&H00FFFFFF", outline="&H00000000", back="&H00000000", bold=1, border=1, ol=6, sh=2, mv=0.30),
    "documentary": dict(size=0.042, primary="&H00F0F0F0", outline="&H00101010", back="&H50000000", bold=0, border=1, ol=2, sh=1, mv=0.06),
}


@tool("subtitle.write_ass", "subtitle", tags=["styling"])
def write_ass(cues: Sequence[dict], out: str, w: int = 1920, h: int = 1080, style: str = "clean",
              font: str | None = None, karaoke: bool = False, extra: Sequence[str] | None = None) -> str:
    """Styled ASS subtitles (clean / boxed / shorts / documentary); karaoke=True highlights word-by-word."""
    from .motion_engine import default_font_name
    s = ASS_STYLES.get(style, ASS_STYLES["clean"])
    fs = int(h * s["size"])
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font or default_font_name()},{fs},{s['primary']},&H0000D7FF,{s['outline']},{s['back']},{s['bold']},0,0,0,100,100,0,0,{s['border']},{s['ol']},{s['sh']},2,{int(w*0.06)},{int(w*0.06)},{int(h*s['mv'])},1
Style: Super,{font or default_font_name()},{int(min(w, h) * 0.062)},&H00FFFFFF,&H0000D7FF,&H00101010,&H64000000,1,0,0,0,100,100,1,0,1,{max(2, int(min(w, h) * 0.003))},2,8,{int(w*0.07)},{int(w*0.07)},{int(h*0.08)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for c in cues:
        txt = c["text"].replace("\n", "\\N")
        if karaoke:
            toks = list(txt) if is_cjk(txt) else txt.split(" ")
            dur_cs = max(1, int((c["end"] - c["start"]) * 100 / max(1, len(toks))))
            txt = ("" if is_cjk(txt) else " ").join(f"{{\\kf{dur_cs}}}{t}" for t in toks)
        ev.append(f"Dialogue: 0,{_fmt(c['start'], '.')[:-1]},{_fmt(c['end'], '.')[:-1]},Default,,0,0,0,,{txt}")
    ev += list(extra or [])                       # e.g. on-screen supers (Style: Super, top centre)
    Path(out).write_text(header + "\n".join(ev) + "\n", encoding="utf-8")
    return out


@tool("subtitle.burn", "subtitle", tags=["finishing"])
def burn(src: str, subs: str, out: str, fonts_dir: str | None = None) -> str:
    """Hard-burn .srt/.ass subtitles into the picture (libass)."""
    from .motion_engine import fonts_dir as fd
    fdir = fonts_dir or fd()
    flt = f"subtitles='{ff.esc_filter_path(subs)}'" + (f":fontsdir='{ff.esc_filter_path(fdir)}'" if fdir else "")
    ff.run(["-i", src, "-vf", flt, "-map", "0:v", "-map", "0:a?", "-c:v", "libx264", "-crf",
            str(settings().get("render.crf", 18)), "-preset", settings().get("render.preset", "medium"),
            "-pix_fmt", "yuv420p", "-c:a", "copy", out])
    return out


@tool("subtitle.mux_soft", "subtitle")
def mux_soft(src: str, subs: str, out: str, lang: str = "chi") -> str:
    """Add a selectable (soft) subtitle track to MP4 (mov_text)."""
    ff.run(["-i", src, "-i", subs, "-map", "0", "-map", "1", "-c", "copy", "-c:s", "mov_text",
            "-metadata:s:s:0", f"language={lang}", out])
    return out


@tool("subtitle.shift", "subtitle")
def shift(cues: Sequence[dict], seconds: float) -> list[dict]:
    """Shift all cues by N seconds."""
    return [{**c, "start": max(0, c["start"] + seconds), "end": max(0, c["end"] + seconds)} for c in cues]
