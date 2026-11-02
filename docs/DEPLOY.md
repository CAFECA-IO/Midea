# 部署：cafeca-aich-001（RTX A6000 48GB，共用伺服器）

Midea 部署在 `borg@211.22.118.147:/workspace/midea`。所有東西（程式、venv、模型、ComfyUI、專案）都放在這個目錄裡，不動系統 Python，也不碰其他使用者的服務。

## 目錄

| 路徑 | 內容 |
|---|---|
| `app/` | Midea 程式碼。`app/.env` 是伺服器專用設定 |
| `venv/` | Midea 主環境（看板、管線、QA、motion 引擎、faster-whisper） |
| `venvs/comfy` · `venvs/audio` · `venvs/foley` · `venvs/tools` | ComfyUI / VoxCPM2 + SFX / HunyuanVideo-Foley / HF CLI，各自獨立 |
| `ComfyUI/` | Midea 專用的 ComfyUI（port 8781），不是 sinobee 在 8188 的那一個 |
| `ACE-Step-1.5/` · `HunyuanVideo-Foley/` · `llama.cpp/` | 各模型的原始碼 |
| `models/` · `hf/` | 權重。MiniMax H3 INT8、Foley XL；`hf/` 是 Hugging Face 快取 |
| `projects/` | 實際專案 |
| `logs/` | `board.log`、`install.log`，以及各服務的 log（在 `app/.logs/`） |

## Port 配置

8080 和 8188 已經有別人在用，所以 Midea 改用 87xx：

| 服務 | Port | 備註 |
|---|---|---|
| 看板 | 7788 | 只綁 127.0.0.1，從外面要走 SSH tunnel |
| Qwen3.8-Flash-Next | **8080（Strata，外部）** | 由 root 的 Strata 提供，Midea 只連線，不負責啟停 |
| ComfyUI + MiniMax H3 | 8781 | 獨佔 GPU |
| VoxCPM2 | 8782 | |
| ACE-Step 1.5 | 8783 | |
| HunyuanVideo-Foley | 8784 | |
| SFX（Stable Audio Open → AudioLDM2） | 8785 | |

## 開看板

```bash
ssh -i ~/Documents/workspace/faith/BORG.pem -N -L 7788:127.0.0.1:7788 borg@211.22.118.147
# 然後用瀏覽器開 http://127.0.0.1:7788
```

## 常用指令（在伺服器上）

```bash
tmux attach -t midea-board              # 看板（Ctrl-b d 離開）
/workspace/midea/run_board.sh           # 看板啟動腳本（會載入 app/.env）
tail -f /workspace/midea/logs/install.log
cd /workspace/midea/app && ../venv/bin/python -m midea doctor
cd /workspace/midea/app && ../venv/bin/python -m midea services status
MIDEA_STACK=/workspace/midea bash app/scripts/deploy_server.sh <step>   # 重跑某一步：tools llama comfy audio whisper acestep foley voxcpm sfx h3 qwen
```

## 接 Strata 的 Qwen（app/.env）

```
QWEN_BASE_URL=http://127.0.0.1:8080/v1
QWEN_API_MODEL=qwen3.8-flash-next-iq3_s
QWEN_VISION=false     # Strata 的 IQ3_S 是純文字模型：參考影片分析改用逐鏡數值描述，抽影格視覺審核會跳過
QWEN_EXTERNAL=true    # Midea 不會啟停 Strata
QWEN_BILL=false       # 不計入影片的 GPU 成本
QWEN_VRAM_GB=0
```

實測約 125 tokens/s。腳本與分鏡的 JSON 會先經過 schema 驗證，不合格時自動修復或重試。

## GPU 共用（重要）

Strata 用 `strata-iq3_s-local.json` 啟動時，會把專家快取塞滿 GPU，**占用約 47GB，整張 A6000 就滿了**。這時 Midea 的 GPU 模型（H3、VoxCPM2、ACE-Step、Foley、SFX）都無法載入。排程會擋下並說明是哪個行程占著，看板也會顯示「其他程式占用 xx GB」。

有三種做法：

1. **改用 Strata 的共用模式**：`/srv/strata/stop.sh && /srv/strata/start-shared.sh`（專家快取 8GB）。Qwen 會變慢，但能空出約 35GB 給 VoxCPM2、ACE-Step、Foley、SFX，H3 也可以用 `H3_MEGAPIXELS=0.4` 試跑。
2. **分時段**：製作影片時先停掉 Strata，Midea 改用自己的 llama-server（把 `QWEN_*` 移掉，再執行 `deploy_server.sh qwen`）。
3. **只跑規劃**：在 `.env` 設 `MIDEA_MOCK_SERVICES=h3,voxcpm,acestep,foley,sfx,whisper`。真實的 Qwen 會負責企劃、腳本、分鏡和動態圖形，GPU 生成的部分用佔位素材代替，可以先驗證內容與流程。

## 實測（2026-11-02，GPU 閒置、Strata 未執行）

| 服務 | 結果 | 耗時 |
|---|---|---|
| VoxCPM2 | 6.9 秒旁白 | 13 秒（含載入） |
| SFX（AudioLDM2） | 2 秒音效 | 11 秒 |
| ACE-Step 1.5 | 20 秒配樂 | 首次 9.7 分鐘（含下載約 15GB 權重），之後約 35 秒 |
| HunyuanVideo-Foley XL | 4 秒 Foley | 20 秒 |
| MiniMax H3（1024×576，8 步 turbo） | 每個 6 秒鏡頭 | 約 5 分鐘，GPU 吃滿 48GB |
| faster-whisper large-v3 | 41 秒混音的逐字時間戳 | 約 4 秒 |

一支 41 秒、含 2 個 H3 鏡頭的動畫解說片，GPU 合計約 11 分鐘，電費約 0.38 TWD。H3 獨佔 GPU 時，其他服務會自動卸載，用完再換回來。

要做的設定：
- 系統安裝了 `python3.12-dev`。triton／torch 的原生 kernel 需要 `Python.h`，沒有的話 H3 會在文字編碼階段失敗。
- `venvs/sfx` 獨立安裝 transformers 4.46，因為 AudioLDM2 不相容 transformers 5。
- Foley 的 `torchaudio.save` 改走 soundfile，因為 torchcodec 的 CUDA 版本不合。
- VoxCPM2 預設 `optimize=False`。要開啟可設 `VOXCPM_OPTIMIZE=1`。

**Qwen 端點**：Strata 停掉時，Midea 無法做企劃、腳本、分鏡（已規劃好的專案仍可繼續生成與合成）。可以選擇：
- 以 shared 模式啟動 Strata（約 8GB 專家快取），與 Midea 共用 GPU。
- 執行 `deploy_server.sh qwen` 下載 GGUF，讓 Midea 自己管理 llama-server（移除 `.env` 中的 `QWEN_*`）。

## 模型選擇（Ampere / sm_86）

- H3：`fl2va_pruned_int8_convrot`、`ref2va_pruned_int8_convrot`、文字編碼器 `qwen3vl_32b_..._int8_convrot`（NVFP4 需要 Blackwell）。turbo LoRA：8 步（T2V/I2V）、4 步（R2V）。
- 預設約 0.6MP（16:9 時為 1024×576），可用 `H3_MEGAPIXELS` 調整。
- Foley 用 XL（5.9GB）並開啟 `--enable_offload`。
- Stable Audio Open 需要授權（gated）：要先 `hf auth login` 並在 Hugging Face 接受授權條款。沒做之前會自動改用 AudioLDM2。
