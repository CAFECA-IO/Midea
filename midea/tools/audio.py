"""Audio post-production tools (FFmpeg)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Sequence

from ..media import ff
from .registry import tool

A = ["-ar", "48000", "-ac", "2"]


def _af_tool(name: str, summary: str, af: str, **defaults):
    def fn(src: str, out: str, **kw) -> str:
        ff.run(["-i", src, "-af", af.format(**{**defaults, **kw}), *A, out])
        return out
    fn.__doc__ = summary
    fn.__name__ = name.split(".")[-1]
    tool(name, "audio")(fn)
    return fn


_af_tool("audio.denoise", "Broadband noise reduction (afftdn).", "afftdn=nr={nr}:nf=-30", nr=12)
_af_tool("audio.highpass", "High-pass filter (remove rumble).", "highpass=f={f}", f=80)
_af_tool("audio.lowpass", "Low-pass filter.", "lowpass=f={f}", f=12000)
_af_tool("audio.de_ess", "Tame sibilance.", "deesser=i={i}", i=0.4)
_af_tool("audio.compress", "Dynamic range compression for voice.", "acompressor=threshold={th}dB:ratio={ratio}:attack=5:release=120:makeup=2", th=-20, ratio=3)
_af_tool("audio.voice_eq", "Broadcast voice EQ (clarity + warmth).",
         "highpass=f=70,equalizer=f=200:t=q:w=1:g=-2,equalizer=f=3000:t=q:w=1.2:g=3,equalizer=f=10000:t=q:w=1:g=1.5")
_af_tool("audio.tempo", "Change tempo without pitch (atempo 0.5–2).", "atempo={factor}", factor=1.1)
_af_tool("audio.pitch", "Shift pitch by semitones.", "asetrate=48000*pow(2\\,{semi}/12),aresample=48000,atempo=1/pow(2\\,{semi}/12)", semi=2)
_af_tool("audio.reverb", "Simple room reverb.", "aecho=0.8:0.85:{ms}:0.35", ms=60)
_af_tool("audio.fade", "Fade in/out.", "afade=t=in:d={d_in},afade=t=out:st={out_start}:d={d_out}", d_in=0.5, d_out=1.0, out_start=0)
_af_tool("audio.normalize_peak", "Peak-normalise.", "dynaudnorm=p={peak}", peak=0.9)
_af_tool("audio.silence_trim", "Trim leading/trailing silence.",
         "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse")
_af_tool("audio.limiter", "Brick-wall limiter.", "alimiter=limit={limit}", limit=0.89)
_af_tool("audio.mono", "Downmix to mono (dual-mono stereo out).", "pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1")
_af_tool("audio.radio", "Telephone/radio effect.", "highpass=f=400,lowpass=f=3200,acrusher=bits=10:mix=0.2")


@tool("audio.trim", "audio")
def trim(src: str, out: str, start: float, end: float) -> str:
    """Trim audio."""
    ff.run(["-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", src, *A, out])
    return out


@tool("audio.pad_to", "audio")
def pad_to(src: str, out: str, seconds: float) -> str:
    """Pad (or trim) audio to an exact duration with silence."""
    ff.run(["-i", src, "-af", f"apad=whole_dur={seconds:.3f}", "-t", f"{seconds:.3f}", *A, out])
    return out


@tool("audio.concat", "audio")
def concat(parts: Sequence[str], out: str, gap: float = 0.0) -> str:
    """Concatenate audio files with an optional silence gap."""
    ins: list[str] = []
    for p in parts:
        ins += ["-i", p]
    pre = ";".join(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,apad=pad_dur={gap}[p{i}]" for i in range(len(parts)))
    fc = pre + ";" + "".join(f"[p{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[a]"
    ff.run([*ins, "-filter_complex", fc, "-map", "[a]", *A, out])
    return out


@tool("audio.place", "audio", tags=["mix"])
def place(clips: Sequence[dict], out: str, total: float) -> str:
    """Lay clips on a timeline: clips=[{path, at, gain_db}] → one stem of length `total`."""
    if not clips:
        ff.run(["-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo", "-t", f"{total:.3f}", *A, out])
        return out
    ins: list[str] = []
    parts = []
    for i, c in enumerate(clips):
        ins += ["-i", c["path"]]
        ms = int(max(0.0, float(c.get("at", 0))) * 1000)
        parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,volume={c.get('gain_db', 0)}dB,"
                     f"adelay={ms}|{ms}[c{i}]")
    mix = "".join(f"[c{i}]" for i in range(len(clips)))
    fc = ";".join(parts) + f";{mix}amix=inputs={len(clips)}:normalize=0:dropout_transition=0,apad,atrim=0:{total:.3f}[a]"
    ff.run([*ins, "-filter_complex", fc, "-map", "[a]", *A, out])
    return out


@tool("audio.duck_mix", "audio", tags=["mix"])
def duck_mix(voice: str, music: str, out: str, sfx: str | None = None, music_db: float = -6.0,
             duck_ratio: float = 8.0, sfx_db: float = 0.0, total: float | None = None) -> str:
    """Mix voice + music (+ sfx) with sidechain ducking so narration stays intelligible."""
    ins = ["-i", voice, "-stream_loop", "-1", "-i", music] + (["-i", sfx] if sfx else [])
    fc = ("[0:a]aresample=48000,aformat=channel_layouts=stereo,asplit=2[v][vsc];"
          f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={music_db}dB[m];"
          f"[m][vsc]sidechaincompress=threshold=0.03:ratio={duck_ratio}:attack=20:release=400:makeup=1[md];")
    if sfx:
        fc += f"[2:a]aresample=48000,aformat=channel_layouts=stereo,volume={sfx_db}dB[s];[v][md][s]amix=inputs=3:normalize=0:duration=first[a]"
    else:
        fc += "[v][md]amix=inputs=2:normalize=0:duration=first[a]"
    ff.run([*ins, "-filter_complex", fc, "-map", "[a]", *(["-t", f"{total:.3f}"] if total else []), *A, out])
    return out


@tool("audio.measure_loudness", "audio", tags=["qa"])
def measure_loudness(src: str) -> dict:
    """EBU R128 integrated loudness, LRA and true peak (loudnorm analysis pass)."""
    err = ff.run_capture(["-i", src, "-af", "loudnorm=print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", err, re.S)
    if not m:
        return {}
    d = json.loads(m.group(0))
    return {"integrated_lufs": float(d["input_i"]), "lra": float(d["input_lra"]),
            "true_peak_db": float(d["input_tp"]), "threshold": float(d["input_thresh"]), "_raw": d}


@tool("audio.loudnorm", "audio", tags=["finishing"])
def loudnorm(src: str, out: str, target_lufs: float = -14.0, true_peak: float = -1.0, lra: float = 11.0,
             video: bool = False) -> str:
    """Two-pass EBU R128 loudness normalisation (accurate, linear when possible)."""
    m = measure_loudness(src)["_raw"]
    af = (f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={lra}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    if video:
        ff.run(["-i", src, "-af", af, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", *A, out])
    else:
        ff.run(["-i", src, "-af", af, *A, out])
    return out


@tool("audio.detect_silence", "audio", tags=["qa"])
def detect_silence(src: str, noise_db: float = -45, min_s: float = 1.0) -> list[dict]:
    """List silent spans (dead air)."""
    err = ff.run_capture(["-i", src, "-af", f"silencedetect=n={noise_db}dB:d={min_s}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", err)]
    ends = [(float(a), float(b)) for a, b in re.findall(r"silence_end: ([0-9.]+) \| silence_duration: ([0-9.]+)", err)]
    return [{"start": s, "end": e[0], "duration": e[1]} for s, e in zip(starts, ends)]


@tool("audio.clipping", "audio", tags=["qa"])
def clipping(src: str) -> dict:
    """Peak level and count of full-scale (clipped) samples (volumedetect histogram)."""
    err = ff.run_capture(["-i", src, "-af", "volumedetect", "-f", "null", "-"])
    peak = re.search(r"max_volume: (-?[0-9.]+) dB", err)
    zero = re.search(r"histogram_0db: ([0-9]+)", err)
    return {"peak_db": float(peak.group(1)) if peak else -120.0, "clipped_samples": int(zero.group(1)) if zero else 0}


@tool("audio.waveform", "audio")
def waveform(src: str, out: str, w: int = 1600, h: int = 200) -> str:
    """Render a waveform PNG (board preview)."""
    ff.run(["-i", src, "-filter_complex", f"showwavespic=s={w}x{h}:colors=#7aa2ff", "-frames:v", "1", out])
    return out


@tool("audio.crossfade", "audio")
def crossfade(a: str, b: str, out: str, d: float = 1.0) -> str:
    """Crossfade two audio files."""
    ff.run(["-i", a, "-i", b, "-filter_complex", f"[0:a][1:a]acrossfade=d={d}[a]", "-map", "[a]", *A, out])
    return out


@tool("audio.beat_grid", "audio")
def beat_grid(bpm: float, seconds: float, beats_per_bar: int = 4) -> dict:
    """Beat and bar times for cutting on the beat."""
    step = 60.0 / bpm
    beats = [round(i * step, 3) for i in range(int(seconds / step) + 1)]
    return {"beats": beats, "bars": beats[::beats_per_bar]}


@tool("audio.snap_to_beats", "audio")
def snap_to_beats(cuts: Sequence[float], beats: Sequence[float], max_shift: float = 0.25) -> list[float]:
    """Move cut points to the nearest beat when within `max_shift` seconds."""
    out = []
    for c in cuts:
        nb = min(beats, key=lambda b: abs(b - c)) if beats else c
        out.append(nb if abs(nb - c) <= max_shift else c)
    return out
