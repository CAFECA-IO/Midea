"""Tiny HTTP wrapper around VoxCPM2 so the model stays resident between scenes.

    python -m midea.servers.voxcpm_server --port 8090

POST /tts {text, voice?, reference_wav?, cfg_value?, inference_timesteps?} -> audio/wav (48 kHz)
Voice design: `voice` is a natural-language description, prepended as "(description) text".
Voice cloning: `reference_wav` is a path on this machine to a clean 5–15 s sample.
"""
from __future__ import annotations

import argparse
import io

import soundfile as sf
import uvicorn
from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel

app = FastAPI(title="Midea VoxCPM2")
MODEL = None


class TTSReq(BaseModel):
    text: str
    voice: str | None = None
    reference_wav: str | None = None
    cfg_value: float = 2.0
    inference_timesteps: int = 10


@app.on_event("startup")
def _load() -> None:
    global MODEL
    import os
    from voxcpm import VoxCPM
    # torch.compile needs Python headers + a working triton toolchain; off by default for portability
    optimize = os.environ.get("VOXCPM_OPTIMIZE", "0").lower() in ("1", "true", "yes")
    MODEL = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False, optimize=optimize)


@app.get("/health")
def health() -> dict:
    return {"ok": MODEL is not None}


@app.post("/tts")
def tts(req: TTSReq) -> Response:
    text = req.text
    if req.voice:
        v = req.voice.strip()
        text = (v if v.startswith("(") else f"({v})") + " " + text
    kw = {"text": text, "cfg_value": req.cfg_value, "inference_timesteps": req.inference_timesteps}
    if req.reference_wav:
        kw["reference_wav_path"] = req.reference_wav
        kw["cfg_value"] = max(req.cfg_value, 2.5)
    wav = MODEL.generate(**kw)
    buf = io.BytesIO()
    sf.write(buf, wav, MODEL.tts_model.sample_rate, format="WAV")
    return Response(buf.getvalue(), media_type="audio/wav")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    uvicorn.run(app, host=a.host, port=a.port)
