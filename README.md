# Midea — 本地 GPU AI 影片工作室

參考 [OpenMontage](https://github.com/calesthio/openmontage) 的「管線＋工具＋審核關卡」架構，Midea 完全以**本地模型**運作，並內建一個**程式化的導演（Runner）**，不需要外部 AI 編碼助手來編排：

| 角色 | 模型 | 在 Midea 中負責 |
|---|---|---|
| 編劇／導演／審片 | **Qwen3.8-Flash-Next**（llama-server，OpenAI 相容） | 企劃、腳本、分鏡、素材排序、參考影片解構、抽影格視覺審核、翻譯 |
| 影片生成 | **MiniMax H3**（ComfyUI，FL2VA pruned INT8） | T2V／I2V（末幀接首幀保持連續性）／R2V（參考圖一致性），原生音訊 |
| 旁白 | **VoxCPM2** | 48 kHz 旁白、聲音設計（用文字描述聲音）、聲音複製（需取得授權） |
| 背景音樂 | **ACE-Step 1.5**（MIT 授權，turbo 版 < 4 GB VRAM） | 10 秒～10 分鐘配樂，可選人聲歌詞 |
| 畫面音效 | **HunyuanVideo-Foley** | 依畫面內容生成同步的 Foley 音效與環境音（48 kHz） |
| 文字音效 | **Stable Audio Open 1.0** | 轉場 whoosh、UI 音、環境音 |
| 字幕對齊 | faster-whisper large-v3 | 字級時間戳記、參考影片轉錄 |
| 演員定妝照 | **Z-Image-Turbo**（Apache-2.0，與 H3 共用 ComfyUI） | 虛擬演員的正面大頭照、四分之三側臉、側面、全身定裝 |

> 音樂與音效模型是依需求補上的：ACE-Step 1.5 負責配樂，HunyuanVideo-Foley（影片→音效）與 Stable Audio Open（文字→音效）互補。三者都能在 24 GB 卡上跟其他模型輪流使用。

## 四大功能

1. **一句話成片**：`midea make "製作一支 60 秒解釋神經網路的動畫"` → 企劃 → 腳本 → 分鏡 → 旁白 → 素材 → 配樂音效 → 剪輯 → 響度與字幕 → 自我審核 → 成片。
2. **全真實素材紀錄片**：`--real-only` 會鎖定只用 Archive.org、NASA、Wikimedia Commons、Pexels、Pixabay 的素材，依授權過濾，由 Qwen 依相關性與年代排序，再加上 Ken Burns、去交錯、膠片質感，片尾自動列出出處。
3. **參考影片結構改編**：`--ref <Shorts/Reels/TikTok 連結>` 以 yt-dlp 下載，接著做切點偵測、抽關鍵影格、ASR，交給 Qwen 視覺分析，抽出節奏、鉤子、分段、字幕樣式這些「模板」，再套到新主題上。
4. **動態圖形與角色動畫**：內建逐格決定性渲染引擎（Playwright + SVG／Canvas／three.js → FFmpeg），提供動態文字排版、圖表、儀表 KPI、神經網路圖、時間軸、路線地圖、**SVG 骨架角色**（idle／wave／walk／talk／point／jump，依旁白音量自動對嘴，可匯入自訂骨架），以及 **3D 產品轉台**（可載入 .glb）。

## 虛擬演員（@ 指定演出）

在看板左上角切到「演員陣容」建立擬真虛擬演員，製作影片時在描述中輸入 `@` 就能指定誰演出：

- **完整設定**：姓名、@代號、年齡、性別、國籍、職業、外貌（族裔外觀、身高、體型、五官、髮型、眼睛、膚色、辨識特徵）、預設造型、個性、表演風格、背景故事、聲音。只要寫一句話（例如「32 歲台灣女記者，俐落短髮」），Qwen 就會補完整份設定，之後都能手動修改。
- **定妝照**：Z-Image-Turbo 以同一個 seed 生成正面大頭照、四分之三側臉、側面、全身定裝。每張都可以單獨重生、設為主照；也可以整組重生，換一張臉。
- **專屬聲音**：VoxCPM2 依年齡、性別與聲音描述設計出聲音並錄一段試音。之後這位演員的每一句台詞，都以這段試音做聲音複製，所以每支影片的聲音都一致。
- **跨鏡頭、跨影片保持同一張臉**：分鏡中出現演員的鏡頭會自動改用 MiniMax H3 Ref2VA，並附上主照和全身定裝當參考圖（單鏡最多 4 位演員、9 張圖）。Qwen 會依演員的個性安排動作與台詞，`speaker` 欄位決定每一段由誰以自己的聲音說。
- **演出作品**：演員頁會列出這位演員出現過的每支影片，包括角色（主演或配音）、出場鏡頭縮圖、台詞段數與製作狀態。點一下就能打開該專案。
- **真人授權**：可以上傳真人照片或聲音樣本來建立演員，但上傳前必須勾選「已取得本人書面授權」並填寫授權來源。授權紀錄會保存在演員資料中，也會列在成片 README 的演員清單裡。
- CLI：`midea actors new "一句話描述"`、`midea actors list`、`midea actors show @mei`，以及 `midea make "@mei 走訪台南老街的一天" --pipeline cinematic`。

> 限制：H3 的參考影片模式不會對嘴到 VoxCPM2 的台詞，所以台詞以畫外音的方式呈現。分鏡規劃會盡量避免演員正對鏡頭說話的特寫。

## 特色

- **即時分鏡看板（Approval Gates）**：`midea serve` → http://127.0.0.1:7788。看板即時呈現企劃、腳本、分鏡卡、生成素材、旁白試聽、預估與實際花費（GPU 秒 → kWh → 新台幣），並在**企劃／腳本／分鏡（含預估花費）／素材／發佈**這幾個節點暫停。可以逐鏡勾選重做、改提示詞、換一個真實素材候選，也能直接編修 JSON 後再核准。
- **單卡 GPU 排程**：針對 24–48 GB 單卡設計。`h3` 會獨佔整張卡；其他服務在 VRAM 預算內共存，超出時依 LRU 卸載，閒置一段時間自動釋放。Qwen 的 MoE 專家層放在 CPU（`--n-cpu-moe`）。
- **嚴謹自我審核**：12 條管線、146 種工具。輸出前一定會檢查以下項目，失敗的成片不會發佈：

  | 檢查 | 內容 |
  |---|---|
  | container | ffprobe：H.264／AAC、yuv420p、48 kHz 立體聲、解析度、fps、影音長度漂移 |
  | delivery | 長度符合承諾（±5% 警告、±10% 失敗）、比例、有字幕 |
  | frames | 4 個位置抽影格：全黑、過曝、空白畫面 |
  | black／freeze／slideshow | 節目內黑畫面比例、凍結畫面、靜態（幻燈片）風險 |
  | loudness／clipping／dead_air | EBU R128（預設 −14 LUFS、TP ≤ −1 dBTP）、削波、> 2 秒靜音 |
  | subtitles | 每秒字數、每行字數、重疊、旁白覆蓋率、與 ASR 字級時間戳的同步誤差 |
  | vision | Qwen 檢視抽出的影格是否符合分鏡（崩臉、亂碼文字、浮水印） |

  響度不合格時會自動以兩段式 loudnorm 修正後重驗。

## 12 條製作管線

`animated-explainer` 動畫解說 · `hybrid` 一鍵混合 · `cinematic` 電影感 · `shorts-factory` 直式短影音 · `documentary-montage` 真實素材紀錄片 · `archival-history` 歷史檔案 · `reference-remix` 參考改編 · `motion-graphics` 動態圖形 · `character-animation` SVG 角色 · `product-3d` 3D 產品 · `clip-factory` 長片切短片 · `localization-dub` 在地化配音

## 快速開始

```bash
make setup                 # 核心（不需要 GPU）
make demo                  # mock 模式端到端跑一支片，確認環境
make setup-gpu             # GPU 機器：安裝並下載所有模型（請先讀 scripts/install_models.sh）
# 依 workflows/README.md 從 ComfyUI 匯出 H3 的 API workflow
python -m midea doctor     # 檢查 ffmpeg 濾鏡、字型、GPU、各模型服務
make serve                 # 開看板
```

CLI 範例：

```bash
python -m midea make "製作一支 60 秒解釋神經網路的動畫"
python -m midea make "1969 登月" --real-only --duration 90
python -m midea make "三個咖啡沖煮技巧" --ref https://www.youtube.com/shorts/XXXX
python -m midea make "小明介紹垃圾分類" --pipeline character-animation --voice "(活潑的小男孩聲音)"
python -m midea make "把這集 Podcast 剪成短片" --media ep12.mp4 --pipeline clip-factory
python -m midea approve <project-id> scene_plan          # 不開看板時從 CLI 核准
python -m midea services status                          # 查看 VRAM 配置
```

## 硬體建議（單卡 24–48 GB）

- **48 GB**（RTX 6000 Ada／A6000／L40S）：預設設定，H3 1344×768、30 steps。
- **24 GB**（RTX 4090／5090）：在 `config.yaml` 設 `gpu.vram_gb: 24`，H3 改為 1024×576、24 steps，每鏡 ≤ 8 秒。成本估算會自動乘 1.8 倍時間。
- **系統記憶體 ≥ 128 GB**：Qwen3.8-Flash-Next 4-bit 約需 96–114 GB（RAM + VRAM），H3 的 offload 約需 64 GB 以上。記憶體不足時可以在 `services.qwen` 把 `base_url` 指到另一台機器的 OpenAI 相容端點。

## 伺服器部署

共用 GPU 伺服器（cafeca-aich-001）的部署方式、port 配置、接 Strata Qwen 端點與 GPU 共用策略見 [docs/DEPLOY.md](docs/DEPLOY.md)；一鍵安裝模型堆疊：`MIDEA_STACK=/workspace/midea bash scripts/deploy_server.sh`。

## 授權注意

- **MiniMax H3 Community License** 不涵蓋美國、歐盟、英國、南韓的使用與輸出；年營收 ≥ 2,000 萬美元的組織商用需要另外取得授權。成片 README 會自動附上標示。
- 真實素材依各來源授權，片尾與 `final/README.md` 會列出出處。Archive.org 標示為 public domain 的素材仍建議人工確認。
- VoxCPM2 聲音複製只能用於已取得授權的聲音；以真人照片或聲音建立演員時，系統會強制要求勾選授權聲明並保存紀錄。
- Z-Image-Turbo 為 Apache-2.0 授權。
- 視覺風格（`slate` 調色盤：石板藍底、琥珀色重點、薰衣草紫次要色）參考 `docs/style-reference.png`。

## 架構

```
midea/
  config.py  gpu/manager.py          設定、單卡 VRAM 排程（獨佔／共存／LRU／閒置卸載）
  providers/                         llm(Qwen) video_h3(ComfyUI) audio(VoxCPM2/ACE-Step/Foley/SFX) stock asr reference + mock
  servers/                           VoxCPM2、Stable Audio、Foley 的常駐 HTTP 服務
  tools/                             146 種工具：video audio subtitles analysis generation motion_engine
  motion/templates/                  14 個逐格渲染範本（SVG／Canvas／three.js）
  pipelines/runner.py                階段機：checkpoint、關卡、修訂迴圈、成本、QA、發佈
  actors.py                          虛擬演員：設定、定妝照、聲音、@ 解析、演出作品
  qa.py  cost.py  project.py         自我審核、成本模型、專案儲存／事件
  web/                               FastAPI + SSE 分鏡看板
pipeline_defs/*.yaml                 12 條管線定義（階段、關卡、風格預設）
workflows/                           MiniMax H3 ComfyUI API workflow（自行匯出）
```

在沒有 GPU 的環境可以用 `MIDEA_MODE=mock`：Qwen 改由決定性規劃器代答，影像、聲音、音樂改用程式產生的佔位素材，其餘剪輯、字幕、動態圖形、QA、看板都會真實執行。
