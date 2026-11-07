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
MIDEA_STACK=/workspace/midea bash app/scripts/deploy_server.sh <step>   # 重跑某一步：tools llama comfy audio whisper acestep foley voxcpm sfx h3 zimage qwen
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

## 虛擬演員（Z-Image-Turbo + H3 Ref2VA + VoxCPM2）

- 權重：`deploy_server.sh zimage` 會從 `Comfy-Org/z_image_turbo` 下載三個檔案，共約 19GB，並連結到 `ComfyUI/models`：
  - `diffusion_models/z_image_turbo_bf16.safetensors`
  - `text_encoders/qwen_3_4b.safetensors`
  - `vae/ae.safetensors`
- 定妝照透過 `h3` 服務，跑在同一個 ComfyUI（8781）。租約與計費都算在 `h3`；費用記到演員自己的 `cost`，不會算進當時正在跑的專案。
- 演員資料放在 `$MIDEA_WORKSPACE/_actors/<id>/`，包含：
  - `actor.json`
  - `portraits/`（舊照片會移到 `portraits/archive/`）
  - `voice/`
  - `uploads/`（真人授權素材）
- 演員的生成工作一次只跑一件。GPU 租約遇到忙碌時會排隊等待（`gpu.wait_s`，預設 2 小時），不會直接失敗。VoxCPM2 伺服器內部也會把請求串行化，因為同時呼叫 `generate()` 會讓 KV 快取錯亂。
- 實測（2026-11-02）：
  - Z-Image-Turbo 每張 1024² 約 6 秒；ComfyUI 冷啟動加上載入約 40 秒。一位演員的 4 張定妝照加試音約 1 分鐘。
  - H3 Ref2VA（4 步 turbo，1024×576）每個 5–7 秒鏡頭約 2.5–3 分鐘，比 FL2VA 8 步快。
  - 測試片「巷口的第一道光」（專案 `20261102-185536-3536da`）：
    - 長度 25.7 秒，共 5 鏡，其中 4 鏡用 Ref2VA，雙人同框 1 鏡，演員親口說台詞 1 鏡。
    - QA 全數通過，GPU 電費 0.64 TWD。
    - 當時 Strata 未執行，企劃、腳本、分鏡是手寫後直接寫入 checkpoint。
- 提示詞**不放演員姓名**，只用 `<Picture i>` 指稱。實測放了英文名，H3 會把名字畫在店門玻璃上。
- 親口說台詞（`lipsync`）的做法：把 VoxCPM2 生成的該句台詞當成 H3 的 `<Audio 1>` 參考。H3 生成的影片會帶對嘴與語音，這段語音直接當作該鏡的人聲。實測 Whisper 能正確辨識出原句。可用 `ACTORS_LIPSYNC=false` 關閉。

## 演員升級：定妝確認、三視圖、說話影片（2026-11-06）

- **權重**：`deploy_server.sh qedit` 安裝 Qwen-Image-Edit-2511，約 31GB，包含：
  - `qwen_image_edit_2511_int8_convrot`（Ampere 用 INT8）
  - `qwen_2.5_vl_7b_fp8_scaled`
  - `qwen_image_vae`
  - Lightning 4 步 LoRA
  - 若 Xet 傳輸卡住，改用 `fetch_qedit.sh`，以 `curl -C -` 續傳。
- **驗收模型**：`deploy_server.sh verify` 安裝以下兩個模型：
  - RTMW 全身姿態（rtmlib＋onnxruntime，跑在 CPU，不需要系統 GL 函式庫；MediaPipe 在此機器缺 `libGLESv2`）
  - ECAPA 聲紋模型（speechbrain，裝在 audio venv，路徑由 `.env` 的 `ECAPA_DIR` 指定）
- **流程**：
  1. 定妝確認：Z-Image 生成正面大頭照與正面全身照，等人工確認。
  2. 三視圖：以確認的兩張照片為參考，用 Qwen-Image-Edit 展開四分之三側臉、側面全身、背面全身。
  3. 自我介紹：Qwen 寫自我介紹 → VoxCPM2 用演員聲音念 → H3 Ref2VA（`<Audio 1>`）生成對嘴影片 → 驗收（Whisper 字錯率、ECAPA 聲紋相似度、跳切偵測）。
- **驗收門檻**（`config.yaml` → `verify.*`、`actors.*`），以實測值校準：

  | 項目 | 實測值 | 門檻 |
  |---|---|---|
  | 腳踝信心（看得到腳 / 看不到） | 0.9 / 0.2–0.3 | 0.5 |
  | 肩寬／軀幹高（正面 / 正側面） | ≈1.0 / ≈0.27 | 側面 ≤ 0.35 |
  | 背面判定：左右肩、左右髖在畫面上對調（正面 +0.4、背面 −0.4） | — | 須對調 |

  - 背面照**不能**用臉部信心判斷，因為模型會在後腦勺「猜」出一張臉。
- **腳太貼畫面下緣**：直接縮小畫面，用兩下角的背景色延伸攝影棚地面，不重新生成。不可用邊緣複製，會把鞋子拉成長條。
- **說話影片的跳切**：H3 偶爾會在片中自己插入溶接轉場。ffmpeg 的 scene score 測不到，改比對相隔 1 秒的縮圖差異：說話、揮手約 4–22，溶接約 35–50，門檻設 30。片長上限 10 秒，因為片子越長越容易出現。
- **實測耗時**：
  - Z-Image 每張 3–6 秒。
  - Qwen-Image-Edit 每張約 20–30 秒（4 步）。
  - H3 說話影片 10 秒 704×864 每次約 6 分鐘。

## 廣告製作（ad-60，2026-11-07）

- **流程**（◆ 為人工確認點）：
  1. 商品 ◆：抓網頁（httpx，失敗改用 Playwright），整理出商品事實表、主色、去背圖。
  2. 試穿 ◆：穿戴類商品才做，用 Qwen-Image-Edit 讓主角換上商品。
  3. 三個概念 ◆：每個概念有 4 張氛圍圖和 10 秒預覽（2 個 H3 鏡頭）。
  4. 文案 ◆：只用網頁上的事實；先自動查核宣稱，不合格就自動改寫一次。
  5. 分鏡 ◆：每一鏡用 Qwen-Image-Edit 合成關鍵畫面，再交給 H3 I2V 當第一幀。
  6. 配音 → 素材 → 音樂音效 → 剪輯 → 合成。
  7. 版本：16:9、9:16、1:1，各有 60 秒和 15 秒。
  8. QA → 發佈 ◆。
- **直式 9:16 混合策略**：從 16:9 裁切；裁切範圍的真實像素寬度少於 `ads.min_crop_px`（480），或主體裝不進去時，該鏡改用 H3 重新生成。
  - 1080p 的 H3 畫面裁成直式只有約 324px 寬，所以實測 10/11 鏡都重新生成了。這是 GPU 時間的大宗。
- **交付檔名**：用「品牌＋文案標題」命名，例如 `iSunTVMall A pause before departure_60s_9x16.mp4`。
- **附件**：`storyboard.pdf`（Playwright 輸出）、`copy.md`、`moodboard.jpg`。
- **實測**（navy travel shirt，@chengen 主演，@yuqing 搭檔）：
  - 11 鏡，60 秒，商品入鏡 42.4 秒。
  - QA 僅有警告。
  - GPU 約 3 小時，其中 H3 I2V 每鏡 4–6 分鐘。
  - 計費 4.98 TWD。
- **注意**：看板重啟後，等待中的人工確認會重新開始等待，需要重新送出決定。

### 廣告風格：時尚大片（`brief.style = "fashion"`）

- **畫面語言**：
  - 壯闊、與商品日常用途無關的場景。
  - 人物從容：停頓、回頭、背影、臉常被裁切。
  - 景別兩極：特寫或大遠景，最多 2 個中景。
  - 至少 3 個 1.5–2 秒的自然意象插入鏡頭。
  - 一個低機位廣角強迫透視鏡頭、一個超現實的商品擺放。
  - 商品約在 40% 處第一次特寫，結尾用商品微距加拉焦。
- **聲音**：
  - 無對白：所有台詞都改由旁白念，H3 提示詞加上「閉嘴、不說話」。
  - 旁白最多 6 句、每句 ≤ 9 字（英文）。
  - 旁白聲音為低沉男聲設計，再用 `asetrate` 降一個半音、放慢 6%（`voice_pitch: 0.94`）。
  - 配樂限古典或鄉村，可用 `brief.music_genre` 指定；三個方向會輪流使用。
  - 混音：H3 環境音 −24 dB，音樂 −3 dB。
- **調色**：`fashion_film`（低飽和、陰影偏青、細顆粒、暗角）。
- **字卡**：置中、細字、寬字距、慢淡入淡出。
- **片尾**：極簡字標卡（品牌、slogan、網址），3–4 秒。
- **QA**：商品出現比例門檻降為 25%（刻意晚出場）。
