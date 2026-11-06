#!/usr/bin/env bash
# Install the full Midea model stack on a shared Linux + NVIDIA server, without touching
# system Python or other users' services. Everything lives under $MIDEA_STACK.
#
#   MIDEA_STACK=/workspace/midea bash scripts/deploy_server.sh [step ...]
#   steps: llama qwen comfy h3 zimage qedit verify audio voxcpm sfx whisper acestep foley  (default: all)
#
# Each step is idempotent (marker files in $MIDEA_STACK/.done). Run inside tmux; total
# download ≈ 200 GB. Ampere (RTX A6000 / sm_86) choices: INT8 "convrot" H3 weights and the
# INT8 text encoder (NVFP4/FP8 kernels need Ada/Blackwell).
set -euo pipefail
S="${MIDEA_STACK:?set MIDEA_STACK}"
APP="$S/app"
export PATH="$HOME/.local/bin:$PATH" HF_HOME="$S/hf" UV_CACHE_DIR="$S/.uvcache" LLAMA_CACHE="$S/llama-cache"
export HF_HUB_ENABLE_HF_TRANSFER=1
CUDA_ARCH="${CUDA_ARCH:-86}"
TORCH_INDEX="${TORCH_INDEX:-https://download.pytorch.org/whl/cu126}"
mkdir -p "$S/.done" "$S/models" "$S/venvs" "$S/logs"
done_() { touch "$S/.done/$1"; echo "== $1 done $(date +%T)"; }
is_done() { [ -f "$S/.done/$1" ]; }
hfdl() { "$S/venvs/tools/bin/hf" download "$@"; }

step_tools() {   # small venv with the HF CLI (fast transfer)
  is_done tools && return
  uv venv -q -p 3.12 "$S/venvs/tools"
  uv pip install -q -p "$S/venvs/tools/bin/python" "huggingface_hub[cli,hf_transfer]"
  done_ tools
}

step_llama() {   # llama.cpp with CUDA for Qwen3.8-Flash-Next
  is_done llama && return
  [ -d "$S/llama.cpp" ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp "$S/llama.cpp"
  cmake -S "$S/llama.cpp" -B "$S/llama.cpp/build" -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCH" \
        -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=ON >/dev/null
  cmake --build "$S/llama.cpp/build" -j"$(nproc)" --target llama-server >/dev/null
  "$S/llama.cpp/build/bin/llama-server" --version
  done_ llama
}

step_qwen() {    # 4-bit dynamic GGUF (~70 GB) into $LLAMA_CACHE-independent folder
  is_done qwen && return
  hfdl unsloth/Qwen3.8-Flash-Next-GGUF --include "*UD-Q4_K_XL*" --local-dir "$S/models/Qwen3.8-Flash-Next-GGUF"
  done_ qwen
}

step_comfy() {   # private ComfyUI instance (own venv, own port) for MiniMax H3
  is_done comfy && return
  [ -d "$S/ComfyUI" ] || git clone https://github.com/comfyanonymous/ComfyUI "$S/ComfyUI"
  uv venv -q -p 3.12 "$S/venvs/comfy"
  uv pip install -q -p "$S/venvs/comfy/bin/python" torch torchvision torchaudio --index-url "$TORCH_INDEX"
  uv pip install -q -p "$S/venvs/comfy/bin/python" -r "$S/ComfyUI/requirements.txt"
  done_ comfy
}

step_h3() {      # MiniMax H3 (FL2VA + Ref2VA, pruned INT8) + INT8 text encoder + VAEs + turbo LoRAs (~82 GB)
  is_done h3 && return
  M="$S/ComfyUI/models"
  # filenames are positional (with --include the CLI would treat all but the first as filenames)
  hfdl Comfy-Org/MiniMax-H3 --local-dir "$S/models/MiniMax-H3" \
              "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors" \
              "diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors" \
              "text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors" \
              "vae/minimax_h3_video_vae_fp16.safetensors" "vae/minimax_h3_audio_vae_fp32.safetensors" \
              "vae/minimax_h3_sol_vae_fp16.safetensors" \
              "loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors" \
              "loras/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"
  for d in diffusion_models text_encoders vae loras; do
    mkdir -p "$M/$d"; for f in "$S/models/MiniMax-H3/$d"/*; do ln -sf "$f" "$M/$d/"; done
  done
  done_ h3
}

step_zimage() {  # Z-Image-Turbo (Apache-2.0) for virtual-actor costume photos (~19 GB), same ComfyUI as H3
  is_done zimage && return
  M="$S/ComfyUI/models"
  hfdl Comfy-Org/z_image_turbo --local-dir "$S/models/z_image_turbo" \
              "split_files/diffusion_models/z_image_turbo_bf16.safetensors" \
              "split_files/text_encoders/qwen_3_4b.safetensors" "split_files/vae/ae.safetensors"
  for d in diffusion_models text_encoders vae; do
    mkdir -p "$M/$d"; for f in "$S/models/z_image_turbo/split_files/$d"/*; do ln -sf "$f" "$M/$d/"; done
  done
  done_ zimage
}

step_qedit() {   # Qwen-Image-Edit-2511 (Apache-2.0): turnarounds, try-on, keyframes (~31 GB), same ComfyUI
  is_done qedit && return
  M="$S/ComfyUI/models"
  hfdl Comfy-Org/Qwen-Image-Edit --local-dir "$S/models/qwen_image_edit" \
              "split_files/diffusion_models/qwen_image_edit_2511_int8_convrot.safetensors" \
              "split_files/loras/Qwen-Edit-2509-Multiple-angles.safetensors"
  hfdl Comfy-Org/Qwen-Image --local-dir "$S/models/qwen_image" \
              "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" "split_files/vae/qwen_image_vae.safetensors"
  hfdl lightx2v/Qwen-Image-Edit-2511-Lightning --local-dir "$S/models/qwen_image_edit/split_files/loras" \
              "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors"
  for d in diffusion_models text_encoders vae loras; do
    mkdir -p "$M/$d"
    for f in "$S/models/qwen_image_edit/split_files/$d"/* "$S/models/qwen_image/split_files/$d"/*; do
      [ -f "$f" ] && ln -sf "$f" "$M/$d/"
    done
  done
  done_ qedit
}

step_verify() {  # self-QA models: RTMW whole-body pose (rtmlib/onnxruntime, CPU) + ECAPA speaker model (audio venv)
  is_done verify && return
  uv pip install -q -p "$S/venv/bin/python" rtmlib onnxruntime
  "$S/venv/bin/python" -c "from rtmlib import Wholebody; Wholebody(mode='balanced', backend='onnxruntime', device='cpu')"
  uv pip install -q -p "$S/venvs/audio/bin/python" speechbrain
  "$S/venvs/audio/bin/python" -c "from speechbrain.inference.speaker import EncoderClassifier as E; E.from_hparams('speechbrain/spkrec-ecapa-voxceleb', savedir='$S/models/ecapa', run_opts={'device':'cpu'})"
  done_ verify
}

step_audio() {   # shared venv for VoxCPM2 + SFX servers (torch cu126)
  is_done audio && return
  uv venv -q -p 3.12 "$S/venvs/audio"
  uv pip install -q -p "$S/venvs/audio/bin/python" torch torchaudio --index-url "$TORCH_INDEX"
  uv pip install -q -p "$S/venvs/audio/bin/python" voxcpm "diffusers>=0.30" transformers accelerate soundfile \
     fastapi uvicorn pydantic pyyaml httpx python-multipart scipy
  done_ audio
}

step_voxcpm() {
  is_done voxcpm && return
  hfdl openbmb/VoxCPM2 >/dev/null
  done_ voxcpm
}

step_sfx() {     # Stable Audio Open is gated; AudioLDM2 (ungated) is the automatic fallback
  is_done sfx && return
  # own venv: AudioLDM2 in diffusers needs transformers 4.x (GPT2 generation API removed in 5.x)
  uv venv -q -p 3.12 "$S/venvs/sfx"
  uv pip install -q -p "$S/venvs/sfx/bin/python" torch torchaudio --index-url "$TORCH_INDEX"
  uv pip install -q -p "$S/venvs/sfx/bin/python" "diffusers==0.32.2" "transformers==4.46.3" accelerate soundfile scipy \
     sentencepiece fastapi uvicorn pydantic pyyaml httpx
  hfdl cvssp/audioldm2 >/dev/null
  hfdl stabilityai/stable-audio-open-1.0 >/dev/null 2>&1 || echo "   (stable-audio-open gated: run 'hf auth login' + accept license to enable; using AudioLDM2)"
  done_ sfx
}

step_whisper() { # faster-whisper in the Midea app venv (CTranslate2, CUDA)
  is_done whisper && return
  uv pip install -q -p "$S/venv/bin/python" faster-whisper nvidia-cublas-cu12 nvidia-cudnn-cu12
  hfdl Systran/faster-whisper-large-v3 >/dev/null
  done_ whisper
}

step_acestep() {
  is_done acestep && return
  [ -d "$S/ACE-Step-1.5" ] || git clone https://github.com/ACE-Step/ACE-Step-1.5 "$S/ACE-Step-1.5"
  (cd "$S/ACE-Step-1.5" && uv sync -q)
  done_ acestep
}

step_foley() {   # HunyuanVideo-Foley XL (5.9 GB) in its own venv
  is_done foley && return
  [ -d "$S/HunyuanVideo-Foley" ] || git clone https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley "$S/HunyuanVideo-Foley"
  uv venv -q -p 3.12 "$S/venvs/foley"
  uv pip install -q -p "$S/venvs/foley/bin/python" torch torchvision torchaudio --index-url "$TORCH_INDEX"
  uv pip install -q -p "$S/venvs/foley/bin/python" -r "$S/HunyuanVideo-Foley/requirements.txt" fastapi uvicorn python-multipart pyyaml httpx pydantic
  hfdl tencent/HunyuanVideo-Foley --local-dir "$S/models/HunyuanVideo-Foley" \
    "hunyuanvideo_foley_xl.pth" "synchformer_state_dict.pth" "vae_128d_48k.pth" "config.yaml" "config_xl.yaml"
  hfdl google/siglip2-base-patch16-512 >/dev/null
  hfdl laion/larger_clap_general >/dev/null
  done_ foley
}

STEPS=("$@")
[ ${#STEPS[@]} -eq 0 ] && STEPS=(tools llama comfy audio whisper acestep foley voxcpm sfx h3 zimage qedit verify qwen)
step_tools
for s in "${STEPS[@]}"; do echo "== $s start $(date +%T)"; "step_$s"; done
echo "ALL DONE $(date)"
