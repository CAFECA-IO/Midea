# MiniMax H3 ComfyUI workflows

> **Optional since v0.2:** Midea builds the H3 API graphs itself (`midea/providers/h3_graph.py`, mirroring the official ComfyUI T2V / I2V / R2V templates) using the model files in `config.yaml → services.h3.models`. You only need this guide if you want a custom node graph — set `services.h3.workflows: {t2v: workflows/h3_t2v_api.json}` to override.

Midea drives MiniMax H3 through ComfyUI's HTTP API using **API-format workflow files** that you export once from your own ComfyUI. ComfyUI's H3 node names and inputs change between releases, so Midea doesn't ship pre-made node graphs. You export them from the version you actually run.

## Steps

1. Update ComfyUI to a version with H3 support (≥ 0.30.0), and download the H3 files into `ComfyUI/models/`:
   - `diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors` (T2V / I2V; this pruned INT8 file is needed on 24–48 GB cards)
   - `diffusion_models/minimax_h3_ref2va_*.safetensors` (R2V, optional)
   - the text encoder plus the video and audio VAEs listed on the `Comfy-Org/MiniMax-H3` model card
2. In ComfyUI, open **Template Library ▸ Video ▸ MiniMax H3 T2V**. Confirm it renders once.
3. Replace these node inputs with placeholders, typing them in exactly, braces included:

| Placeholder | Put it in |
|---|---|
| `{{PROMPT}}` | positive prompt text |
| `{{NEGATIVE}}` | negative prompt text (if the template has one) |
| `{{WIDTH}}` / `{{HEIGHT}}` | latent / video size |
| `{{SECONDS}}` or `{{FRAMES}}` | duration (whichever the node uses; FRAMES = seconds × fps + 1) |
| `{{FPS}}` | frame rate on the save / encode node |
| `{{SEED}}` | sampler seed (set "control after generate" to *fixed*) |
| `{{STEPS}}` | sampler steps |
| `{{FIRST_FRAME}}` / `{{LAST_FRAME}}` | `LoadImage` image name (I2V template) |
| `{{REF_IMAGE_1}}` … `{{REF_IMAGE_9}}` | `LoadImage` nodes (R2V template) |

   For numeric widgets that won't accept text, export first, then edit the JSON and put the quoted placeholder (for example `"{{SEED}}"`) in as the value. Midea writes a bare number in its place.
4. **Workflow ▸ Export (API)**, and save the files as:
   - `workflows/h3_t2v_api.json`
   - `workflows/h3_i2v_api.json`
   - `workflows/h3_r2v_api.json`
5. Make sure the output node writes an `.mp4` (Save Video / VHS Video Combine) **with audio**, so you keep H3's native 32 kHz audio.

## Low-VRAM settings (single 24–48 GB card)

- Start ComfyUI with `--lowvram --reserve-vram 1.5` (that's already the `services.h3.start` command in `config.yaml`).
- Use the pruned INT8 checkpoint. Expect roughly 64 GB+ of system RAM for offloaded layers, and 128 GB to be comfortable.
- On 24 GB, reduce `services.h3.defaults` to `width: 1024, height: 576, steps: 24`, and keep shots ≤ 8 s.
- `h3` is marked `exclusive: true`, so Midea unloads Qwen, VoxCPM2, ACE-Step and the other services before each H3 job.

## License reminder

The MiniMax H3 Community License (effective 2 Aug 2026) does **not** cover use, hosting or outputs of the open weights in the US, EU, UK or South Korea without separate authorization. Organisations with ≥ US$20M annual revenue also need written authorization for commercial use. Read the full license before you publish.
