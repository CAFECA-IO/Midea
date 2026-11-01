"""Video-to-audio Foley server wrapping Tencent HunyuanVideo-Foley's infer.py.

    python -m midea.servers.foley_server --port 8092 --repo ~/HunyuanVideo-Foley --weights ~/models/HunyuanVideo-Foley
POST /foley (multipart: video, prompt) -> audio/wav (48 kHz)

On a 24 GB card run it alone (Midea's scheduler unloads other services first when
vram_gb in config.yaml says so). Add --offload flags in --extra if your checkout supports them.
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

app = FastAPI(title="Midea Foley")
ARGS: argparse.Namespace


@app.get("/health")
def health() -> dict:
    return {"ok": Path(ARGS.repo, "infer.py").exists()}


@app.post("/foley")
async def foley(video: UploadFile = File(...), prompt: str = Form("")) -> Response:
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "in.mp4"
        src.write_bytes(await video.read())
        outdir = Path(td) / "out"
        cmd = [sys.executable, "infer.py", "--model_path", os.path.expanduser(ARGS.weights),
               "--config_path", ARGS.config, "--single_video", str(src),
               "--single_prompt", prompt or "natural ambient sound matching the scene",
               "--output_dir", str(outdir), *shlex.split(ARGS.extra)]
        p = subprocess.run(cmd, cwd=os.path.expanduser(ARGS.repo), capture_output=True, text=True)
        if p.returncode != 0:
            raise HTTPException(500, p.stderr[-3000:])
        wavs = sorted(outdir.rglob("*.wav"))
        if wavs:
            return Response(wavs[0].read_bytes(), media_type="audio/wav")
        vids = sorted(outdir.rglob("*.mp4"))
        if not vids:
            raise HTTPException(500, "Foley produced no output")
        wav = Path(td) / "a.wav"
        subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-y", "-i", str(vids[0]), "-vn", "-ar", "48000", str(wav)],
                       check=True, capture_output=True)
        return Response(wav.read_bytes(), media_type="audio/wav")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8092)
    ap.add_argument("--repo", default="~/HunyuanVideo-Foley")
    ap.add_argument("--weights", default="~/models/HunyuanVideo-Foley")
    ap.add_argument("--config", default="./configs/hunyuanvideo-foley-xxl.yaml")
    ap.add_argument("--extra", default="")
    ARGS = ap.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=ARGS.port)
