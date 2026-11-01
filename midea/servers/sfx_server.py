"""Text-to-SFX server (Stable Audio Open 1.0 via diffusers; ~6 GB VRAM in fp16).

    python -m midea.servers.sfx_server --port 8093
POST /sfx {prompt, seconds (≤47), seed?} -> audio/wav (44.1 kHz stereo)
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


class SfxReq(BaseModel):
    prompt: str
    seconds: float = 3.0
    seed: int | None = None
    steps: int = 100


@app.on_event("startup")
def _load() -> None:
    global PIPE
    import torch
    from diffusers import StableAudioPipeline
    PIPE = StableAudioPipeline.from_pretrained("stabilityai/stable-audio-open-1.0", torch_dtype=torch.float16).to("cuda")


@app.get("/health")
def health() -> dict:
    return {"ok": PIPE is not None}


@app.post("/sfx")
def sfx(req: SfxReq) -> Response:
    import soundfile as sf
    import torch
    g = torch.Generator("cuda").manual_seed(req.seed if req.seed is not None else torch.seed() % 2**31)
    audio = PIPE(req.prompt, negative_prompt="low quality, music, speech", num_inference_steps=req.steps,
                 audio_end_in_s=min(47.0, max(0.5, req.seconds)), num_waveforms_per_prompt=1, generator=g).audios
    buf = io.BytesIO()
    sf.write(buf, audio[0].T.float().cpu().numpy(), PIPE.vae.sampling_rate, format="WAV")
    return Response(buf.getvalue(), media_type="audio/wav")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8093)
    a = ap.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=a.port)
