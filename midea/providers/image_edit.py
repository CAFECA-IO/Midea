"""Qwen-Image-Edit-2511 (Apache-2.0) multi-reference image editing on the shared local ComfyUI.

Used for actor turnarounds (three-quarter / side / back from the approved front photos), product try-on
and ad keyframes (actor + product + scene). The graph mirrors the official ComfyUI template
`image_qwen_image_edit_2511`: UNETLoader → ModelSamplingAuraFlow(3.1) → CFGNorm → Lightning LoRA (4 steps)
→ KSampler(euler/simple, cfg 1); TextEncodeQwenImageEditPlus(image1..3) for positive / empty negative,
each through FluxKontextMultiReferenceLatentMethod(index_timestep_zero). Output size follows image1
(FluxKontextImageScale) unless width/height are given.
"""
from __future__ import annotations

import random
import uuid
from pathlib import Path

import httpx

from ..config import settings
from ..gpu import scheduler
from ..log import get_logger

log = get_logger("image_edit")


def _cfg() -> dict:
    return settings().get("image_edit", {}) or {}


def graph(prompt: str, images: list[str], *, seed: int, width: int | None = None, height: int | None = None) -> dict:
    c = _cfg()
    lora = c.get("lora")
    steps = int(c.get("steps", 4 if lora else 40))
    cfg = float(c.get("cfg", 1.0 if lora else 4.0))
    g: dict = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": c.get("unet", "qwen_image_edit_2511_int8_convrot.safetensors"),
                                                     "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": c.get("text_encoder", "qwen_2.5_vl_7b_fp8_scaled.safetensors"),
                                                     "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": c.get("vae", "qwen_image_vae.safetensors")}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": float(c.get("shift", 3.1))}},
        "5": {"class_type": "CFGNorm", "inputs": {"model": ["4", 0], "strength": 1.0}},
    }
    model = ["5", 0]
    if lora:
        g["6"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": model, "lora_name": lora, "strength_model": 1.0}}
        model = ["6", 0]
    for i, extra in enumerate(c.get("extra_loras") or []):        # e.g. multiple-angles LoRA for turnarounds
        nid = str(60 + i)
        g[nid] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": model, "lora_name": extra["name"],
                                                                  "strength_model": float(extra.get("strength", 1.0))}}
        model = [nid, 0]
    imgs = []
    for i, name in enumerate(images[:3]):
        nid = str(10 + i)
        g[nid] = {"class_type": "LoadImage", "inputs": {"image": name}}
        imgs.append([nid, 0])
    g["20"] = {"class_type": "FluxKontextImageScale", "inputs": {"image": imgs[0]}}
    first = ["20", 0]
    enc = {"clip": ["2", 0], "vae": ["3", 0], "image1": first}
    for k, ref in zip(("image2", "image3"), imgs[1:]):
        enc[k] = ref
    g["21"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {**enc, "prompt": prompt}}
    g["22"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {**enc, "prompt": ""}}
    g["23"] = {"class_type": "FluxKontextMultiReferenceLatentMethod",
               "inputs": {"conditioning": ["21", 0], "reference_latents_method": "index_timestep_zero"}}
    g["24"] = {"class_type": "FluxKontextMultiReferenceLatentMethod",
               "inputs": {"conditioning": ["22", 0], "reference_latents_method": "index_timestep_zero"}}
    if width and height:
        g["25"] = {"class_type": "EmptySD3LatentImage", "inputs": {"width": int(width) // 16 * 16, "height": int(height) // 16 * 16,
                                                                   "batch_size": 1}}
    else:
        g["25"] = {"class_type": "VAEEncode", "inputs": {"pixels": first, "vae": ["3", 0]}}
    g["26"] = {"class_type": "KSampler", "inputs": {"model": model, "seed": int(seed), "steps": steps, "cfg": cfg,
                                                    "sampler_name": "euler", "scheduler": "simple", "positive": ["23", 0],
                                                    "negative": ["24", 0], "latent_image": ["25", 0], "denoise": 1.0}}
    g["27"] = {"class_type": "VAEDecode", "inputs": {"samples": ["26", 0], "vae": ["3", 0]}}
    g["28"] = {"class_type": "SaveImage", "inputs": {"images": ["27", 0], "filename_prefix": "midea/edit"}}
    return g


def edit(prompt: str, images: list[str | Path], out: Path, *, seed: int | None = None, width: int | None = None,
         height: int | None = None, label: str = "") -> Path:
    """Render an edit of image 1 guided by up to two more reference images (refer to them as image 1/2/3)."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    seed = seed if seed is not None else random.randint(0, 2**31 - 1)
    svc = _cfg().get("service", "h3")
    if not images:
        raise ValueError("image edit needs at least one input image")
    if settings().mocked(svc):
        from .image_zimage import mock_portrait
        from ..media import ff
        info = ff.video_stream(images[0]) or {}
        w = int(width or info.get("width", 768)) // 2
        h = int(height or info.get("height", 1024)) // 2
        return mock_portrait(label or prompt, out, width=w // 2 * 2, height=h // 2 * 2, seed=seed)
    from .video_h3 import h3
    c3 = h3()
    with scheduler().lease(svc), httpx.Client(timeout=120) as client:
        names = [c3._upload(client, p) for p in images[:3]]
        r = client.post(f"{c3.base}/prompt", json={"prompt": graph(prompt, names, seed=seed, width=width, height=height),
                                                   "client_id": str(uuid.uuid4())})
        if r.status_code != 200:
            raise RuntimeError(f"ComfyUI rejected Qwen-Image-Edit workflow: {r.text[:800]}")
        pid = r.json()["prompt_id"]
        log.info("Qwen-Image-Edit %s queued (%d refs, seed=%d)", pid, len(names), seed)
        outputs = c3._wait(client, pid, timeout=900)
        for node in outputs.values():
            for f in node.get("images", []):
                v = client.get(f"{c3.base}/view", params={"filename": f["filename"], "subfolder": f.get("subfolder", ""),
                                                          "type": f.get("type", "output")})
                v.raise_for_status()
                out.write_bytes(v.content)
                return out
    raise RuntimeError("Qwen-Image-Edit workflow produced no image")
