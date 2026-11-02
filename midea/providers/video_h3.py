"""MiniMax H3 (open weights) through a local ComfyUI server.

Workflows are API-format JSON files exported from ComfyUI ("Export (API)") after
loading the official H3 T2V / I2V / R2V templates. Put these placeholders in the
node inputs you want Midea to control (as JSON strings or numbers):

    "{{PROMPT}}"  "{{NEGATIVE}}"  "{{SECONDS}}"  "{{FRAMES}}"  "{{WIDTH}}"  "{{HEIGHT}}"
    "{{SEED}}"    "{{STEPS}}"     "{{FIRST_FRAME}}"  "{{LAST_FRAME}}"  "{{REF_IMAGE_1}}" … "{{REF_IMAGE_9}}"

Numeric placeholders written as the quoted string "{{SECONDS}}" are replaced by
bare numbers, so the workflow stays valid JSON either way.
"""
from __future__ import annotations

import json
import random
import time
import uuid
from pathlib import Path

import httpx

from ..config import settings
from ..gpu import scheduler
from ..log import get_logger
from ..media import ff

log = get_logger("h3")

ASPECTS = {"16:9": (1344, 768), "9:16": (768, 1344), "1:1": (1024, 1024), "4:5": (896, 1120), "21:9": (1680, 720)}


def _fill(template: str, values: dict) -> dict:
    s = template
    for k, v in values.items():
        token = "{{" + k + "}}"
        if isinstance(v, (int, float)):
            s = s.replace(f'"{token}"', json.dumps(v)).replace(token, str(v))
        else:
            s = s.replace(token, json.dumps(str(v))[1:-1])
    return json.loads(s)


class H3:
    service = "h3"

    def __init__(self) -> None:
        self.cfg = settings().services.get(self.service, {})
        self.base = self.cfg.get("base_url", "http://127.0.0.1:8188")
        self.defaults = self.cfg.get("defaults", {})

    # -- ComfyUI helpers ---------------------------------------------------
    def _upload(self, client: httpx.Client, path: str | Path) -> str:
        with open(path, "rb") as fh:
            r = client.post(f"{self.base}/upload/image", files={"image": (Path(path).name, fh)},
                            data={"overwrite": "true"})
        r.raise_for_status()
        return r.json()["name"]

    def _wait(self, client: httpx.Client, prompt_id: str, timeout: float) -> dict:
        t0 = time.time()
        while time.time() - t0 < timeout:
            r = client.get(f"{self.base}/history/{prompt_id}")
            if r.status_code == 200 and prompt_id in r.json():
                h = r.json()[prompt_id]
                st = h.get("status", {})
                if st.get("status_str") == "error":
                    raise RuntimeError(f"H3 workflow failed: {st.get('messages')}")
                if st.get("completed", True) and h.get("outputs"):
                    return h["outputs"]
            time.sleep(3)
        raise TimeoutError("H3 generation timed out")

    def generate(self, prompt: str, out: Path, *, seconds: int = 6, aspect: str = "16:9",
                 mode: str = "t2v", first_frame: str | None = None, last_frame: str | None = None,
                 ref_images: list[str] | None = None, seed: int | None = None,
                 negative: str = "blurry, low quality, watermark, text artifacts, deformed hands, flicker") -> Path:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        seconds = int(max(4, min(int(self.defaults.get("max_seconds", 15)), round(seconds))))
        w, h = ASPECTS.get(aspect, ASPECTS["16:9"])
        fps = int(self.defaults.get("fps", 24))
        seed = seed if seed is not None else random.randint(0, 2**31 - 1)
        if settings().mocked("h3"):
            return mock_video(prompt, out, seconds=seconds, w=w // 2, h=h // 2, fps=fps, seed=seed)

        clean = self.defaults.get("clean_suffix", "Clean frame: no on-screen text, no captions, no subtitles, no logos, no watermark.")
        if clean and clean.lower() not in prompt.lower():
            prompt = f"{prompt.rstrip('. ')}. {clean}"          # BasicGuider has no negative prompt
        mp = float(self.defaults.get("megapixels", 0))
        if mp:                                         # size from a pixel budget, multiples of 32 (like ResolutionSelector)
            a, b = (int(x) for x in aspect.split(":")) if ":" in aspect else (16, 9)
            hh = (mp * 1e6 * b / a) ** 0.5
            w, h = int(round(hh * a / b / 32) * 32), int(round(hh / 32) * 32)
        wf_rel = (self.cfg.get("workflows") or {}).get(mode)
        wf_path = settings().root / wf_rel if wf_rel else None
        builtin = not (wf_path and wf_path.exists())
        values = {"PROMPT": prompt, "NEGATIVE": negative, "SECONDS": seconds, "FRAMES": seconds * fps + 1,
                  "WIDTH": w, "HEIGHT": h, "SEED": seed, "STEPS": int(self.defaults.get("steps", 30)),
                  "FPS": fps}
        with scheduler().lease(self.service), httpx.Client(timeout=120) as client:
            if first_frame:
                values["FIRST_FRAME"] = self._upload(client, first_frame)
            if last_frame:
                values["LAST_FRAME"] = self._upload(client, last_frame)
            for i, ref in enumerate((ref_images or [])[:9], 1):
                values[f"REF_IMAGE_{i}"] = self._upload(client, ref)
            if builtin:                                # graphs mirroring the official H3 templates
                from . import h3_graph
                models = self.cfg.get("models") or {}
                steps = self.defaults.get("steps")
                if mode == "r2v":
                    refs = [values[k] for k in sorted(values) if k.startswith("REF_IMAGE_")]
                    workflow = h3_graph.ref2va(models, prompt=prompt, width=w, height=h, seconds=seconds, seed=seed,
                                               refs=refs, steps=self.defaults.get("r2v_steps"))
                else:
                    workflow = h3_graph.fl2va(models, prompt=prompt, width=w, height=h, seconds=seconds, seed=seed,
                                              steps=steps, first_frame=values.get("FIRST_FRAME"),
                                              last_frame=values.get("LAST_FRAME"))
            else:
                workflow = _fill(wf_path.read_text(encoding="utf-8"), values)
            r = client.post(f"{self.base}/prompt", json={"prompt": workflow, "client_id": str(uuid.uuid4())})
            if r.status_code != 200:
                raise RuntimeError(f"ComfyUI rejected workflow: {r.text[:1000]}")
            pid = r.json()["prompt_id"]
            log.info("H3 %s queued (%ss %dx%d seed=%d)", pid, seconds, w, h, seed)
            outputs = self._wait(client, pid, timeout=3600)
            for node in outputs.values():
                for key in ("gifs", "videos", "images"):
                    for f in node.get(key, []):
                        if str(f.get("filename", "")).endswith((".mp4", ".webm", ".mov", ".mkv")):
                            v = client.get(f"{self.base}/view", params={"filename": f["filename"],
                                           "subfolder": f.get("subfolder", ""), "type": f.get("type", "output")})
                            v.raise_for_status()
                            out.write_bytes(v.content)
                            return out
        raise RuntimeError("H3 workflow produced no video output; check the SaveVideo node in your workflow")


def mock_video(prompt: str, out: Path, *, seconds: float, w: int = 672, h: int = 384, fps: int = 24,
               seed: int = 0) -> Path:
    """Moving gradient + caption + tone; stands in for a generated shot in mock mode."""
    from ..tools.motion_engine import default_font
    hue = seed % 360
    label = ff.esc_text(prompt[:60])
    vf = (f"hue=h={hue}+t*20,zoompan=z='1+0.002*on':x='iw/2-(iw/zoom/2)+on*2':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={fps},drawtext=fontfile='{ff.esc_filter_path(default_font())}':text='{label}':fontcolor=white:fontsize={max(14, h // 22)}:"
          f"x=(w-text_w)/2:y=h-th-20:box=1:boxcolor=black@0.4")
    ff.run(["-f", "lavfi", "-i", f"gradients=s={w}x{h}:r={fps}:d={seconds}:speed=0.12:seed={seed % 1000}",
            "-f", "lavfi", "-i", f"sine=frequency={220 + seed % 200}:sample_rate=48000:duration={seconds}",
            "-filter_complex", f"[0:v]{vf}[v];[1:a]volume=0.05[a]", "-map", "[v]", "-map", "[a]",
            "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
            "-c:a", "aac", "-shortest", out])
    return out


_h3: H3 | None = None


def h3() -> H3:
    global _h3
    if _h3 is None:
        _h3 = H3()
    return _h3
