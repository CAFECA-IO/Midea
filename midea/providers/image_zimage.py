"""Z-Image-Turbo (Tongyi-MAI, Apache-2.0) text→image through the same local ComfyUI that serves H3.

Used for virtual-actor costume/headshot photos. The graph mirrors the official ComfyUI
template `image_z_image_turbo`: UNETLoader → ModelSamplingAuraFlow(shift 3) → KSampler
(8 steps, cfg 1, res_multistep/simple), CLIPLoader(type lumina2), EmptySD3LatentImage,
negative = ConditioningZeroOut(positive) → VAEDecode → SaveImage.
"""
from __future__ import annotations

import random
import uuid
from pathlib import Path

import httpx

from ..config import settings
from ..gpu import scheduler
from ..log import get_logger
from ..media import ff

log = get_logger("image")


def _cfg() -> dict:
    return settings().get("image", {}) or {}


def graph(prompt: str, *, width: int, height: int, seed: int) -> dict:
    c = _cfg()
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": c.get("unet", "z_image_turbo_bf16.safetensors"),
                                                     "weight_dtype": "default"}},
        "2": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": float(c.get("shift", 3))}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": c.get("text_encoder", "qwen_3_4b.safetensors"),
                                                     "type": "lumina2", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": c.get("vae", "ae.safetensors")}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": prompt}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": int(width), "height": int(height), "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["2", 0], "seed": int(seed), "steps": int(c.get("steps", 8)),
                                                   "cfg": 1.0, "sampler_name": "res_multistep", "scheduler": "simple",
                                                   "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["7", 0],
                                                   "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["4", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "midea/actor"}},
    }


def generate(prompt: str, out: Path, *, width: int = 1024, height: int = 1024, seed: int | None = None,
             label: str = "") -> Path:
    """Render one image to `out` (PNG). Returns the path."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    seed = seed if seed is not None else random.randint(0, 2**31 - 1)
    svc = _cfg().get("service", "h3")
    if settings().mocked(svc):
        return mock_portrait(label or prompt, out, width=width // 2, height=height // 2, seed=seed)
    from .video_h3 import h3
    client_h3 = h3()
    with scheduler().lease(svc), httpx.Client(timeout=120) as client:
        r = client.post(f"{client_h3.base}/prompt", json={"prompt": graph(prompt, width=width, height=height, seed=seed),
                                                          "client_id": str(uuid.uuid4())})
        if r.status_code != 200:
            raise RuntimeError(f"ComfyUI rejected Z-Image workflow: {r.text[:800]}")
        pid = r.json()["prompt_id"]
        log.info("Z-Image %s queued (%dx%d seed=%d)", pid, width, height, seed)
        outputs = client_h3._wait(client, pid, timeout=900)
        for node in outputs.values():
            for f in node.get("images", []):
                v = client.get(f"{client_h3.base}/view", params={"filename": f["filename"], "subfolder": f.get("subfolder", ""),
                                                                "type": f.get("type", "output")})
                v.raise_for_status()
                out.write_bytes(v.content)
                return out
    raise RuntimeError("Z-Image workflow produced no image")


def mock_portrait(label: str, out: Path, *, width: int = 512, height: int = 512, seed: int = 0) -> Path:
    """Offline stand-in: a slate card with a head-and-shoulders silhouette and the actor's label."""
    from ..tools.motion_engine import default_font
    hue = seed % 360
    font = ff.esc_filter_path(default_font())
    txt = ff.esc_text(label[:24])
    cx, cy, r = width // 2, int(height * 0.42), max(20, min(width, height) // 7)
    vf = (f"format=yuv444p,"
          f"geq=lum='if(lt(pow(X-{cx},2)+pow(Y-{cy},2),{r*r}),200,if(lt(pow((X-{cx})/1.9,2)+pow(Y-{cy+int(r*2.6)},2),{int(r*r*1.2)}),170,lum(X,Y)))':cb='cb(X,Y)':cr='cr(X,Y)',hue=h={hue}:s=0.6,"
          f"drawtext=fontfile='{font}':text='{txt}':fontcolor=white:fontsize={max(14, height // 18)}:x=(w-text_w)/2:y=h-th-{height // 14}")
    ff.run(["-f", "lavfi", "-i", f"gradients=s={width}x{height}:c0=0x2a3042:c1=0x3b4258:seed={seed % 1000}:d=1",
            "-frames:v", "1", "-vf", vf, out])
    return out
