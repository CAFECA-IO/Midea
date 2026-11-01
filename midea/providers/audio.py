"""Local audio models: VoxCPM2 (TTS), ACE-Step 1.5 (music), HunyuanVideo-Foley (video→SFX),
Stable Audio Open (text→SFX). Every function has an offline mock for mode == "mock"."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx

from ..config import settings
from ..gpu import scheduler
from ..log import get_logger
from ..media import ff

log = get_logger("audio")


def _svc(name: str) -> dict:
    return settings().services.get(name, {})


def estimate_speech_seconds(text: str) -> float:
    cjk = len(re.findall(r"[一-鿿぀-ヿ가-힯]", text))
    words = len(re.findall(r"[A-Za-z0-9']+", text))
    pauses = len(re.findall(r"[，。！？、；,.!?;]", text))
    return round(cjk / 4.2 + words / 2.5 + pauses * 0.18 + 0.3, 2)


# ---------------------------------------------------------------- VoxCPM2 TTS
def tts(text: str, out: Path, *, voice: str | None = None, reference_wav: str | None = None,
        cfg_value: float | None = None, steps: int | None = None) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cfg = _svc("voxcpm")
    d = cfg.get("defaults", {})
    if settings().mode == "mock":
        return _mock_voice(text, out)
    body = {"text": text, "voice": voice or d.get("voice", ""), "reference_wav": reference_wav,
            "cfg_value": cfg_value or d.get("cfg_value", 2.0), "inference_timesteps": steps or d.get("inference_timesteps", 10)}
    with scheduler().lease("voxcpm"):
        r = httpx.post(f"{cfg['base_url']}/tts", json=body, timeout=900)
        r.raise_for_status()
    out.write_bytes(r.content)
    return out


def _mock_voice(text: str, out: Path) -> Path:
    dur = estimate_speech_seconds(text)
    # syllable-like amplitude modulation so loudness/silence QA behaves like speech
    ff.run(["-f", "lavfi", "-i", f"sine=frequency=180:sample_rate=48000:duration={dur}",
            "-f", "lavfi", "-i", f"anoisesrc=color=pink:sample_rate=48000:duration={dur}:amplitude=0.3",
            "-filter_complex", "[0:a][1:a]amix=inputs=2:weights='1 0.4',tremolo=f=4.5:d=0.8,"
                               "lowpass=f=3400,volume=4[a]",
            "-map", "[a]", "-ac", "1", "-ar", "48000", out])
    return out


# ---------------------------------------------------------------- ACE-Step music
def music(prompt: str, seconds: float, out: Path, *, bpm: int | None = None, lyrics: str = "",
          instrumental: bool = True, key_scale: str = "", seed: int | None = None) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    seconds = max(10.0, min(600.0, float(seconds)))
    if settings().mode == "mock":
        return _mock_music(seconds, out, bpm or 96)
    cfg = _svc("acestep")
    base = cfg["base_url"]
    d = cfg.get("defaults", {})
    body = {"prompt": prompt + (", instrumental" if instrumental else ""), "lyrics": "" if instrumental else lyrics,
            "audio_duration": seconds, "audio_format": d.get("audio_format", "wav"),
            "inference_steps": d.get("inference_steps", 8), "batch_size": 1, "thinking": True}
    if bpm:
        body["bpm"] = int(bpm)
    if key_scale:
        body["key_scale"] = key_scale
    if seed is not None:
        body.update(use_random_seed=False, seed=seed)
    with scheduler().lease("acestep"), httpx.Client(timeout=120) as c:
        r = c.post(f"{base}/release_task", json=body)
        r.raise_for_status()
        task_id = r.json()["data"]["task_id"]
        t0 = time.time()
        while time.time() - t0 < 1800:
            q = c.post(f"{base}/query_result", json={"task_id_list": [task_id]}).json()["data"][0]
            if q["status"] == 1:
                results = json.loads(q["result"]) if isinstance(q["result"], str) else q["result"]
                a = c.get(f"{base}{results[0]['file']}")
                a.raise_for_status()
                out.write_bytes(a.content)
                return out
            if q["status"] == 2:
                raise RuntimeError(f"ACE-Step failed: {q}")
            time.sleep(2)
    raise TimeoutError("ACE-Step timed out")


def _mock_music(seconds: float, out: Path, bpm: int) -> Path:
    beat = 60.0 / bpm
    expr = ("0.10*sin(2*PI*220*t)+0.08*sin(2*PI*277.18*t)+0.07*sin(2*PI*329.63*t)"
            f"+0.12*sin(2*PI*55*t)*exp(-6*mod(t\\,{beat:.4f}))")
    ff.run(["-f", "lavfi", "-i", f"aevalsrc='{expr}':s=48000:d={seconds}", "-ac", "2",
            "-af", f"afade=t=in:d=1,afade=t=out:st={max(0, seconds-2)}:d=2", out])
    return out


# ---------------------------------------------------------------- SFX
def foley(video: Path, prompt: str, out: Path) -> Path:
    """HunyuanVideo-Foley: synthesise synchronised sound for a video clip."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if settings().mode == "mock":
        return sfx(prompt or "ambient room tone", ff.duration(video), out)
    cfg = _svc("foley")
    with scheduler().lease("foley"), open(video, "rb") as fh:
        r = httpx.post(f"{cfg['base_url']}/foley", files={"video": (Path(video).name, fh, "video/mp4")},
                       data={"prompt": prompt}, timeout=1800)
        r.raise_for_status()
    out.write_bytes(r.content)
    return out


def sfx(prompt: str, seconds: float, out: Path, *, seed: int | None = None) -> Path:
    """Stable Audio Open: text → sound effect (≤ 47 s)."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    seconds = max(0.3, min(47.0, float(seconds)))
    if settings().mode == "mock":
        color = "white" if "whoosh" in prompt.lower() else "brown"
        ff.run(["-f", "lavfi", "-i", f"anoisesrc=color={color}:sample_rate=48000:duration={seconds}:amplitude=0.5",
                "-af", f"bandpass=f=1200:w=900,afade=t=in:d={seconds*0.4:.2f},"
                       f"afade=t=out:st={seconds*0.5:.2f}:d={seconds*0.5:.2f}", "-ac", "2", out])
        return out
    cfg = _svc("sfx")
    with scheduler().lease("sfx"):
        r = httpx.post(f"{cfg['base_url']}/sfx", json={"prompt": prompt, "seconds": seconds, "seed": seed},
                       timeout=600)
        r.raise_for_status()
    out.write_bytes(r.content)
    return out
