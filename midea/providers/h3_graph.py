"""Built-in ComfyUI API graphs for MiniMax H3 (no hand-exported workflow needed).

Mirrors the official ComfyUI templates (video_minimax_h3_t2v / _i2v / _r2v):
UNETLoader → (turbo LoRA) → BasicScheduler/BasicGuider → SamplerCustomAdvanced →
VAEDecode + VAEDecodeAudio → CreateVideo (native audio) → SaveVideo (mp4).
"""
from __future__ import annotations


def snap_frames(seconds: float, fps: int = 24) -> int:
    """H3 frame counts live on a 17k+5 grid (124 ≈ 5 s)."""
    n = max(5, round(seconds * fps))
    return n + (5 - n % 17) % 17


def _common(m: dict, unet: str, lora: str | None, lora_strength: float, steps: int, seed: int) -> dict:
    g = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": m["text_encoder"], "type": "minimax", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": m["video_vae"]}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": m["audio_vae"]}},
        "7": {"class_type": "RandomNoise", "inputs": {"noise_seed": int(seed)}},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["4", 0]}},
        "13": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["11", 0], "vae": ["5", 0]}},
        "14": {"class_type": "CreateVideo", "inputs": {"images": ["12", 0], "audio": ["13", 0], "fps": 24.0}},
        "15": {"class_type": "SaveVideo", "inputs": {"video": ["14", 0], "filename_prefix": "midea/h3",
                                                     "format": "mp4", "format.codec": "h264"}},
    }
    model = ["1", 0]
    if lora:
        g["2"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": lora,
                                                                  "strength_model": float(lora_strength)}}
        model = ["2", 0]
    g["9"] = {"class_type": "BasicScheduler", "inputs": {"model": model, "scheduler": "simple", "steps": int(steps), "denoise": 1.0}}
    g["10"] = {"class_type": "BasicGuider", "inputs": {"model": model, "conditioning": ["6", 0]}}
    g["11"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["7", 0], "guider": ["10", 0], "sampler": ["8", 0],
                                                                 "sigmas": ["9", 0], "latent_image": ["6", 1]}}
    return g


def fl2va(m: dict, *, prompt: str, width: int, height: int, seconds: float, seed: int, steps: int | None = None,
          first_frame: str | None = None, last_frame: str | None = None) -> dict:
    """Text→video, or image→video when first/last frames (uploaded image names) are given."""
    lora = m.get("lora_fl2v")
    g = _common(m, m["fl2va"], lora, 1.0, steps or (8 if lora else 20), seed)
    inputs = {"clip": ["3", 0], "vae": ["4", 0], "prompt": prompt, "width": int(width), "height": int(height),
              "length": snap_frames(seconds)}
    if first_frame:
        g["20"] = {"class_type": "LoadImage", "inputs": {"image": first_frame}}
        inputs["first_frame"] = ["20", 0]
    if last_frame:
        g["21"] = {"class_type": "LoadImage", "inputs": {"image": last_frame}}
        inputs["last_frame"] = ["21", 0]
    g["6"] = {"class_type": "MiniMaxH3ImageToVideo", "inputs": inputs}
    return g


def ref2va(m: dict, *, prompt: str, width: int, height: int, seconds: float, seed: int, refs: list[str],
           steps: int | None = None, audios: list[str] | None = None) -> dict:
    """Reference→video: up to 9 reference images (<Picture 1>…) and up to 3 standalone reference
    audio clips (<Audio 1>…, e.g. an actor's line for voice + lip-sync) — names are uploaded input files."""
    lora = m.get("lora_r2v")
    g = _common(m, m["ref2va"], lora, 1.0, steps or (4 if lora else 20), seed)
    inputs = {"clip": ["3", 0], "vae": ["4", 0], "audio_vae": ["5", 0], "prompt": prompt, "width": int(width),
              "height": int(height), "length": snap_frames(seconds), "ref_image_size": "match"}
    for i, name in enumerate(refs[:9]):
        nid = str(30 + i)
        g[nid] = {"class_type": "LoadImage", "inputs": {"image": name}}
        inputs[f"ref_images.ref_image_{i}"] = [nid, 0]
    for j, name in enumerate((audios or [])[:3]):
        nid = str(40 + j)
        g[nid] = {"class_type": "LoadAudio", "inputs": {"audio": name}}
        inputs[f"ref_audios.ref_audio_{j}"] = [nid, 0]
    g["6"] = {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": inputs}
    return g
