# 元件規劃

元件分兩批：**已完成**的在 `window.Midea`（v1 19 個、v2 15 個，共 34 個），有即時預覽與使用說明；**規劃中**的列出用途、主要資料與優先順序（P1 = 首頁上線前、P2 = 上線後第一個月、P3 = 之後）。新增元件一律先用現有 token，不新增顏色。

## 已完成（v1）

| 群組 | 元件 | 用途 |
|---|---|---|
| 品牌 | `Logo` | 標誌加字標 |
| 品牌 | `Icon` | 線條圖示：search、play、key、sound-off、arrow-right、chevron-right；v2 加 heart、sparkle、smile、tear、plus、x、bookmark、share、eye、people、sound、expand、home、calendar、grid、user、check |
| 動作 | `Button` | primary（琥珀）／secondary（外框）／ghost／light（影像上的白色） |
| 動作 | `SignInButton` | 「以 CAFECA 登入」，填色或外框 |
| 輸入 | `SearchField` | 搜尋框 |
| 輸入 | `SegmentedTabs` | 排行期間等 2–4 個互斥選項 |
| 導覽 | `SiteHeader` | 標誌、主選單、搜尋、登入 |
| 導覽 | `SiteFooter` | 版權、AI 製作聲明、連結 |
| 狀態 | `Badge` | LIVE、現正播放、排行升降、新上榜 |
| 狀態 | `Tag` | 推薦理由、主題分類 |
| 狀態 | `ProgressBar` | 直播進度、繼續觀看 |
| 版面 | `SectionHeader` | 區塊標題列 |
| 版面 | `BentoGrid` | 4／2／1 欄磚塊格線 |
| 媒體 | `VideoTile` | 影像磚：直播主磚、下一個時段、主題主打、小磚、直式（v2 加 `corner`：右上角放 `ViewerCount`） |
| 媒體 | `ThemeTile` | 本週主題（琥珀色純色磚） |
| 媒體 | `RankTile` | 排行第 1–5 名的影像磚與外框數字 |
| 媒體 | `RankRow` | 排行第 6–10 名的清單列 |
| 節目 | `DaySlot` | 本週每晚的主打時段（v2 加 `tag`：放 `InfluenceTag`） |
| 人物 | `ActorCard` | 平台演員卡 |

## 已完成（v2，2026-11-08，隨首頁與第一期觀眾互動上線）

| 群組 | 元件 | 用途 |
|---|---|---|
| 播放 | `LivePlayer` | 官方頻道直播：從節目表位置開始、不能快轉；疊加即時反應與時段結束投票 |
| 播放 | `VideoPlayer` | 單一影片：字幕、直式、觀眾最有反應的片段標記、看完進度回報 |
| 影片資訊 | `VideoMeta` | 片名、時段或類型、演員、標籤、收藏與分享 |
| 影片資訊 | `AIDisclosure` | 「本片由 AI 製作，演員皆為虛擬角色」 |
| 主題 | `TopicBento` | 一個主題的完整 Bento（主打 + 最多 4 部，自動補滿） |
| 登入 | `SignInDialog` | 以 CAFECA 登入：彈出視窗、在這個分頁登入、QR 碼 |
| 登入 | `AccountMenu` | 登入後的頭像選單 |
| 回饋 | `Skeleton` | 載入中的色塊 |
| 回饋 | `EmptyState` | 沒有內容時的說明與動作 |
| 行動版 | `BottomNav` | 手機底部導覽 |
| 互動 | `ReactionBar` | 播完後的三個反應與「不感興趣」理由（匿名可用） |
| 互動 | `LiveReactions` | 直播 5 個即時反應、飄起動畫、可關閉 |
| 互動 | `ViewerCount` | 「N 人正在看」，少於 10 人不顯示 |
| 互動 | `PollCard` | 觀眾決定投票（tile／full）與時段結束投票（overlay） |
| 互動 | `InfluenceTag` | 「觀眾投票選出」等影響說明（`Tag` 的變體） |

## 規劃中

### 播放

| 元件 | 用途 | 主要資料 | 優先 |
|---|---|---|---|
| `MiniPlayer` | 離開首頁後直播縮到右下角繼續播 | 目前直播 | P2 |
| `UpNext` | 一部播完前 5 秒顯示下一部 | 下一部影片 | P2 |

### 節目表

| 元件 | 用途 | 主要資料 | 優先 |
|---|---|---|---|
| `ScheduleWeek` | 整週節目表（7 天 × 20:00–24:00），首播／特輯／重播分色 | 時段清單 | P1 |
| `ScheduleDay` | 單日時間軸，現在時間線 | 當天時段 | P1 |
| `ProgramCard` | 時段詳情：AI 排入的每部影片與排入理由 | 時段、影片、理由 | P2 |
| `ScheduleNotice` | 「下週節目表 11/9（一）09:00 公布」的提示列 | 公布時間 | P2 |

### 主題與探索

| 元件 | 用途 | 主要資料 | 優先 |
|---|---|---|---|
| `TopicHeader` | 主題頁頭：名稱、推薦理由、上次歸納時間、部數 | 主題 | P1 |
| `FilterChips` | 類型篩選：全部／廣告／短片／演員／直式 | 選項 | P2 |
| `SearchResults` | 搜尋結果：影片、演員、主題分組 | 查詢結果 | P2 |

### 影片資訊

| 元件 | 用途 | 主要資料 | 優先 |
|---|---|---|---|
| `CreditList` | 素材出處與授權（MiniMax H3 標示等） | 出處清單 | P2 |
| `VersionSwitch` | 切換同一支片的 16:9／9:16／1:1、60／15 秒 | 版本清單 | P2 |

### 個人與登入

| 元件 | 用途 | 主要資料 | 優先 |
|---|---|---|---|
| `ContinueRow` | 繼續觀看列，含進度 | 觀看紀錄 | P2 |
| `InterestPicker` | 第一次登入時選幾個感興趣的主題 | 主題清單 | P3 |

### 回饋與行動版

| 元件 | 用途 | 主要資料 | 優先 |
|---|---|---|---|
| `Toast` | 短訊息：「已加入收藏」 | 文字 | P2 |
| `ErrorState` | 播放失敗、網路中斷，說明原因與重試 | 錯誤 | P2 |
| `Sheet` | 手機上的選單與篩選面板 | 內容 | P2 |

### 觀眾互動（第二、三期，見「觀眾反饋與互動功能規劃」）

| 元件 | 用途 | 主要資料 | 優先 |
|---|---|---|---|
| `ChatPanel` | 直播聊天室：置頂訊息、訊息列、輸入框、審核提示；手機收起 | 時段、訊息 | P2 |
| `WishCard` | 許願卡：內容、+1 數與門檻進度、狀態（征求中／成為主題／製作中／完成） | 許願卡 | P2 |
| `WishComposer` | 許願表單：主題（≤ 40 字）或演員組合（1–2 位 + 一句情境），每週 3 個 | 演員清單 | P2 |
| `AskActor` | 向演員提問（≤ 60 字，每天 3 題）與演員的文字回覆（標「AI 生成 · 虛擬演員」） | 演員、問題 | P2 |
| `AnswerTile` | 演員影片回答（`VideoTile` 變體，附提問內容） | 回答影片 | P3 |

## 命名與 API 約定

- 元件名用英文 PascalCase；畫面文字一律由呼叫端傳入，元件不寫死中文（`SignInButton` 的預設文字除外）。
- 影像一律傳 `image`（網址）與 `alt`；人像加 `focus="top"`。
- 尺寸用 `cols`、`rows`（Bento 格數），不傳像素。
- 狀態用語意名稱：`tone="live" | "now" | "new" | "up" | "down" | "same" | "neutral"`，不傳顏色。
