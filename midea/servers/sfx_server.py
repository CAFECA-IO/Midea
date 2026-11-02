"""Text-to-SFX server.

    python -m midea.servers.sfx_server --port 8785
POST /sfx {prompt, seconds (≤47), seed?} -> audio/wav

Uses Stable Audio Open 1.0 (44.1 kHz stereo, ~6 GB fp16) when its gated weights are
available (accept the license on Hugging Face + `hf auth login`), otherwise falls back
to AudioLDM2 (ungated, 16 kHz mono, upsampled to 48 kHz stereo).
"""
from __future__ import annotations

import argparse
import io

import uvicorn
from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel

app = FastAPI(title="Midea SFX")
PIPE = None
KIND = ""


class SfxReq(BaseModel):
    prompt: str
    seconds: float = 3.0
    seed: int | None = None
    steps: int = 100


@app.on_event("startup")
def _load() -> None:
    global PIPE, KIND
    import torch
    try:
        from diffusers import StableAudioPipeline
        PIPE = StableAudioPipeline.from_pretrained("stabilityai/stable-audio-open-1.0", torch_dtype=torch.float16).to("cuda")
        KIND = "stable-audio-open"
    except Exception as e:  # noqa: BLE001 — gated / not downloaded
        print(f"Stable Audio Open unavailable ({type(e).__name__}); falling back to AudioLDM2")
        from diffusers import AudioLDM2Pipeline
        PIPE = AudioLDM2Pipeline.from_pretrained("cvssp/audioldm2", torch_dtype=torch.float16).to("cuda")
        KIND = "audioldm2"


@app.get("/health")
def health() -> dict:
    return {"ok": PIPE is not None, "model": KIND}


@app.post("/sfx")
def sfx(req: SfxReq) -> Response:
    import numpy as np
    import soundfile as sf
    import torch
    seed = req.seed if req.seed is not None else int(torch.seed() % 2**31)
    g = torch.Generator("cuda").manual_seed(seed)
    secs = min(47.0, max(0.5, req.seconds))
    buf = io.BytesIO()
    if KIND == "stable-audio-open":
        audio = PIPE(req.prompt, negative_prompt="low quality, music, speech", num_inference_steps=req.steps,
                     audio_end_in_s=secs, num_waveforms_per_prompt=1, generator=g).audios
        sf.write(buf, audio[0].T.float().cpu().numpy(), PIPE.vae.sampling_rate, format="WAV")
    else:
        audio = PIPE(req.prompt, negative_prompt="low quality, music, speech", num_inference_steps=min(req.steps, 200),
                     audio_length_in_s=max(2.0, secs), num_waveforms_per_prompt=1, generator=g).audios[0]
        from scipy.signal import resample_poly
        a = resample_poly(np.asarray(audio, dtype=np.float32), 3, 1)[: int(secs * 48000)]
        sf.write(buf, np.stack([a, a], axis=1), 48000, format="WAV")
    return Response(buf.getvalue(), media_type="audio/wav")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8785)
    a = ap.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=a.port)
