#!/usr/bin/env bash
# One-time setup of the local model stack on a Linux + NVIDIA (24–48 GB) machine.
# Review before running; downloads are large (~150 GB total).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODELS="${MODELS:-$HOME/models}"
mkdir -p "$MODELS"

echo "== Python deps (Midea + GPU servers)"
pip install -r "$ROOT/requirements.txt" -r "$ROOT/requirements-gpu.txt"
playwright install chromium

echo "== llama.cpp (Qwen3.8-Flash-Next server, CUDA build)"
if ! command -v llama-server >/dev/null; then
  git clone --depth 1 https://github.com/ggml-org/llama.cpp "$HOME/llama.cpp"
  cmake -S "$HOME/llama.cpp" -B "$HOME/llama.cpp/build" -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
  cmake --build "$HOME/llama.cpp/build" -j --target llama-server
  sudo ln -sf "$HOME/llama.cpp/build/bin/llama-server" /usr/local/bin/llama-server
fi
# 4-bit dynamic quant (~96–114 GB RAM+VRAM). Experts are offloaded to CPU with --n-cpu-moe (see config.yaml).
# The weights are fetched by `llama-server -hf unsloth/Qwen3.8-Flash-Next-GGUF:UD-Q4_K_XL` on first start
# (cached under ~/.cache/llama.cpp). Pre-fetch now so the first video doesn't wait:
llama-server -hf unsloth/Qwen3.8-Flash-Next-GGUF:UD-Q4_K_XL --port 18080 -ngl 0 -c 512 & LP=$!
until curl -sf localhost:18080/health >/dev/null; do sleep 10; kill -0 $LP 2>/dev/null || break; done; kill $LP 2>/dev/null || true

echo "== ComfyUI + MiniMax H3 (pruned INT8)"
if [ ! -d "$HOME/ComfyUI" ]; then
  git clone https://github.com/comfyanonymous/ComfyUI "$HOME/ComfyUI"
  pip install -r "$HOME/ComfyUI/requirements.txt"
fi
huggingface-cli download Comfy-Org/MiniMax-H3 minimax_h3_fl2va_pruned_int8_convrot.safetensors \
  --local-dir "$HOME/ComfyUI/models/diffusion_models"
echo "   -> also download the text encoder + video/audio VAEs listed on the Comfy-Org/MiniMax-H3 card,"
echo "      then export the API workflows as described in workflows/README.md"

echo "== VoxCPM2 (weights download on first start)"
python -c "from voxcpm import VoxCPM; VoxCPM.from_pretrained('openbmb/VoxCPM2', load_denoiser=False)" || true

echo "== ACE-Step 1.5 (music)"
if [ ! -d "$HOME/ACE-Step-1.5" ]; then
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
  git clone https://github.com/ACE-Step/ACE-Step-1.5 "$HOME/ACE-Step-1.5"
  (cd "$HOME/ACE-Step-1.5" && uv sync)
fi

echo "== HunyuanVideo-Foley (video→audio)"
if [ ! -d "$HOME/HunyuanVideo-Foley" ]; then
  git clone https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley "$HOME/HunyuanVideo-Foley"
  pip install -r "$HOME/HunyuanVideo-Foley/requirements.txt"
fi
huggingface-cli download tencent/HunyuanVideo-Foley --local-dir "$MODELS/HunyuanVideo-Foley"

echo "== Stable Audio Open (text→SFX; gated model: accept the license on Hugging Face first)"
python -c "from diffusers import StableAudioPipeline; StableAudioPipeline.from_pretrained('stabilityai/stable-audio-open-1.0')" || \
  echo "   -> run 'huggingface-cli login' and accept the model license, then re-run"

echo "== fonts (CJK subtitles & motion graphics)"
command -v fc-list >/dev/null && (fc-list | grep -qi "Noto Sans CJK" || sudo apt-get install -y fonts-noto-cjk)

echo "Done. Next: python -m midea doctor"
