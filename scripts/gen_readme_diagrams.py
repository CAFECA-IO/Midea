#!/usr/bin/env python3
"""Generate the README diagrams in docs/images/ (slate palette: slate background, amber accent, lavender secondary).

Usage: python scripts/gen_readme_diagrams.py docs/images
"""
import sys
from pathlib import Path
from xml.sax.saxutils import escape as E

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
BG, PANEL, PANEL2, LINE = "#1d2330", "#272f3f", "#323b4e", "#4a556b"
TXT, MUTED, AMBER, LAV, TEAL = "#e9edf4", "#9ba6b8", "#f2b84b", "#b7a6ff", "#7fd1c2"
FONT = "'PingFang TC','Noto Sans CJK TC','Microsoft JhengHei','Noto Sans TC',system-ui,sans-serif"
MONO = "'SF Mono',Menlo,Consolas,monospace"


def svg(w, h, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
            f'aria-label="{E(title)}" font-family="{FONT}">\n<title>{E(title)}</title>\n'
            f'<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0 0L10 5L0 10z" fill="{MUTED}"/></marker>'
            f'<marker id="am" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0 0L10 5L0 10z" fill="{AMBER}"/></marker></defs>\n'
            f'<rect width="{w}" height="{h}" rx="16" fill="{BG}"/>\n{body}\n</svg>\n')


def t(x, y, s, size=14, fill=TXT, weight=400, anchor="start", mono=False, op=1):
    fam = f' font-family="{MONO}"' if mono else ""
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}" text-anchor="{anchor}"'
            f'{fam}{"" if op == 1 else f" opacity={chr(34)}{op}{chr(34)}"}>{E(s)}</text>')


def box(x, y, w, h, fill=PANEL, stroke=LINE, rx=10, dash=False, sw=1.2):
    d = ' stroke-dasharray="5 4"' if dash else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>'


def card(x, y, w, h, title, lines=(), accent=LAV, fill=PANEL, tsize=15, lsize=12.5, mono_first=False):
    out = [box(x, y, w, h, fill=fill), f'<rect x="{x}" y="{y + 10}" width="3" height="{h - 20}" rx="1.5" fill="{accent}"/>',
           t(x + 14, y + 24, title, tsize, TXT, 600)]
    for i, ln in enumerate(lines):
        out.append(t(x + 14, y + 44 + i * 18, ln, lsize, MUTED, mono=(mono_first and i == 0)))
    return "\n".join(out)


def arrow(x1, y1, x2, y2, color=MUTED, dash=False, head="a"):
    d = ' stroke-dasharray="5 4"' if dash else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.6"{d} marker-end="url(#{head})"/>'


def path(d, color=MUTED, dash=False, head="a"):
    dd = ' stroke-dasharray="5 4"' if dash else ""
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.6"{dd} marker-end="url(#{head})"/>'


# ------------------------------------------------------------------ 1. architecture
W, H = 1200, 800
b = [t(40, 52, "系統架構", 26, TXT, 700), t(40, 78, "一台單卡 GPU 伺服器上的完整影片工作室：看板與導演程式在上層，模型服務在下層，由 GPU 排程器輪流使用顯示卡", 14, MUTED)]
# users
b += [card(40, 104, 340, 70, "瀏覽器 · 分鏡看板", ["http://<伺服器>:10030（需登入）"], AMBER),
      card(400, 104, 260, 70, "命令列 CLI", ["python -m midea make / approve …"], AMBER),
      card(680, 104, 480, 70, "SSE 即時事件", ["進度、關卡、費用即時推送到看板"], AMBER)]
# app panel
b += [box(40, 196, 840, 352, fill="#222a39", stroke=LINE, rx=14), t(60, 224, "Midea 應用程式（Python · /workspace/midea/app）", 16, TXT, 600)]
cw, ch = 256, 92
cells = [("web/app.py", ["FastAPI 看板與 API", "HTTP Basic 登入、SSE"]),
         ("pipelines/runner.py", ["階段機：checkpoint、審核關卡", "修訂迴圈、成本、QA、發佈"]),
         ("pipelines/ad.py", ["AdRunner：商品、試穿、提案", "文案、分鏡、多版本、風格"]),
         ("actors.py", ["虛擬演員：設定、定妝照", "三視圖、聲音、說話影片"]),
         ("tools/ · motion/", ["146 種工具：剪輯、字幕、音訊", "逐格動態圖形渲染（Playwright）"]),
         ("qa.py · cost.py", ["自我審核 11 類檢查", "GPU 秒 → kWh → 新台幣"]),
         ("providers/", ["各模型的用戶端", "LLM、H3、影像、聲音、ASR"]),
         ("vision_check.py", ["RTMW 全身姿態驗收", "腳部、側面、背面、跳切"]),
         ("project.py", ["專案儲存、事件匯流排", "關卡決定（重啟後仍有效）"])]
for i, (n, ls) in enumerate(cells):
    x = 60 + (i % 3) * (cw + 12); y = 240 + (i // 3) * (ch + 12)
    b.append(card(x, y, cw, ch, n, ls, LAV if i not in (1, 2) else AMBER, fill=PANEL))
# storage
b += [box(900, 196, 260, 352, fill="#222a39", rx=14), t(920, 224, "工作區（磁碟）", 16, TXT, 600)]
store = [("projects/<id>/", ["project.json 狀態與關卡", "stages/*.json 每階段存檔", "scenes/ audio/ compose/", "final/ 成片與附件"]),
         ("_actors/<id>/", ["actor.json 設定", "portraits/ 定妝照、三視圖", "voice/ intro/ 聲音、說話影片"]),
         ("logs/board.log", ["看板與排程紀錄"])]
yy = 240
for n, ls in store:
    hh = 32 + 18 * len(ls)
    b.append(card(916, yy, 228, hh, n, ls, TEAL, tsize=14, lsize=12))
    yy += hh + 12
# scheduler
b += [box(40, 568, 1120, 62, fill=PANEL2, stroke=AMBER, rx=12),
      t(60, 594, "GPU 排程器 gpu/manager.py", 16, AMBER, 700),
      t(60, 616, "租約：H3 獨佔整張卡；其他服務在 VRAM 預算內共存，超出時依 LRU 卸載 · 卡忙時排隊等待 · 閒置 600 秒自動停止並釋放顯存 · 依專案／演員計費", 13, MUTED)]
# services
svc = [("Qwen3.8-Flash-Next", ":8080 Strata", "企劃、腳本、分鏡、審片"),
       ("ComfyUI", ":8781", "H3 · Z-Image · Qwen-Edit"),
       ("VoxCPM2", ":8782", "旁白、聲音複製、聲紋"),
       ("ACE-Step 1.5", ":8783", "配樂"),
       ("HunyuanVideo-Foley", ":8784", "畫面音效"),
       ("SFX", ":8785", "文字→音效"),
       ("faster-whisper", "看板內", "字幕對齊、字錯率")]
sw_ = (1120 - 6 * 10) / 7
for i, (n, p, d) in enumerate(svc):
    x = 40 + i * (sw_ + 10)
    b += [box(x, 652, sw_, 84, fill=PANEL), t(x + sw_ / 2, 676, n, 13, TXT, 600, "middle"),
          t(x + sw_ / 2, 696, p, 12.5, AMBER, 500, "middle", mono=True), t(x + sw_ / 2, 718, d, 11.5, MUTED, 400, "middle")]
b += [box(40, 750, 1120, 30, fill="#161b25", rx=8), t(600, 770, "NVIDIA RTX A6000 48 GB · 系統記憶體 188 GB（Qwen 的 MoE 專家層放在 CPU）", 13, MUTED, 400, "middle")]
# arrows
b += [arrow(210, 174, 210, 238), arrow(530, 174, 530, 196), path("M 920 174 L 920 186 L 600 186 L 600 238", MUTED, True),
      arrow(880, 372, 900, 372), arrow(460, 548, 460, 566), arrow(600, 630, 600, 650)]
(OUT / "architecture.svg").write_text(svg(W, H, "\n".join(b), "Midea 系統架構"), encoding="utf-8")

# ------------------------------------------------------------------ 2. how it works
W, H = 1200, 700
b = [t(40, 52, "運作原理", 26, TXT, 700), t(40, 78, "導演程式依管線定義逐階段執行；每階段先存檔，遇到審核關卡就暫停等人決定；GPU 由排程器輪流分配", 14, MUTED)]
# left: stage machine
b += [box(40, 100, 640, 400, fill="#222a39", rx=14), t(60, 128, "① 階段機與審核關卡", 17, TXT, 600)]
b += [card(70, 170, 170, 62, "執行階段", ["呼叫模型與工具"], LAV),
      card(290, 170, 170, 62, "存檔 checkpoint", ["stages/<階段>.json"], TEAL),
      card(510, 170, 150, 62, "是關卡嗎？", ["pipeline_defs/*.yaml"], LAV)]
b += [arrow(240, 201, 288, 201), arrow(460, 201, 508, 201)]
b += [path("M 585 232 L 585 274", AMBER, head="am"), t(595, 258, "是", 13, AMBER, 600),
      path("M 660 201 L 668 201 L 668 152 L 155 152 L 155 168", MUTED, True), t(420, 146, "否 → 下一階段", 12.5, MUTED, 400, "middle")]
b += [box(470, 276, 190, 62, fill=PANEL2, stroke=AMBER), t(565, 302, "◆ 等待審核", 15, AMBER, 700, "middle"),
      t(565, 322, "看板即時顯示內容與花費", 12, MUTED, 400, "middle")]
dec = [("核准", "寫入存檔 → 下一階段", TEAL, 70), ("退回＋意見", "整段重做（最多 3 次）", AMBER, 270),
       ("指定重做", "只重畫／重生勾選的鏡頭", LAV, 470)]
for n, d, c, x in dec:
    b += [card(x, 384, 190, 62, n, [d], c)]
b += [path("M 565 338 L 565 360 L 165 360 L 165 382"), arrow(365, 360, 365, 382), arrow(565, 360, 565, 382)]
b += [t(60, 472, "· 看板或伺服器重啟：從最後一個存檔接續；重啟前送出的關卡決定仍會被採用一次。", 12.5, MUTED),
      t(60, 491, "· 自動模式（auto_approve）跳過關卡；花費低於門檻的分鏡也會自動核准。", 12.5, MUTED)]
# right: gpu
b += [box(700, 100, 460, 400, fill="#222a39", rx=14), t(720, 128, "② 單卡 GPU 排程（48 GB）", 17, TXT, 600)]
gx, gy, gw, gh = 740, 160, 390, 230
b += [box(gx, gy, gw, gh, fill="#161b25", rx=6), t(gx - 8, gy + 8, "48", 11, MUTED, 400, "end"), t(gx - 8, gy + gh, "0 GB", 11, MUTED, 400, "end")]
sc = gh / 48
def blk(x0, x1, g0, g1, color, label):
    y0 = gy + gh - g1 * sc; hh = (g1 - g0) * sc
    return (f'<rect x="{gx + x0}" y="{y0}" width="{x1 - x0}" height="{hh}" rx="4" fill="{color}" opacity=".85"/>'
            + t(gx + (x0 + x1) / 2, y0 + hh / 2 + 4, label, 12, BG, 700, "middle"))
b += [blk(6, 120, 0, 27, LAV, "Qwen 27 GB"), blk(6, 120, 27.5, 33, TEAL, "VoxCPM2"),
      blk(132, 290, 0, 44, AMBER, "H3 獨佔"), blk(302, 384, 0, 6, TEAL, "ACE-Step")]
b += [t(gx + 63, gy + gh + 20, "企劃、旁白", 12, MUTED, 400, "middle"), t(gx + 211, gy + gh + 20, "生成鏡頭", 12, MUTED, 400, "middle"),
      t(gx + 343, gy + gh + 20, "配樂", 12, MUTED, 400, "middle")]
b += [t(720, 432, "· 需要整張卡的 H3 來時，先停掉其他服務釋放顯存。", 12.5, MUTED),
      t(720, 452, "· 卡被占用時租約排隊等待，不會直接失敗。", 12.5, MUTED),
      t(720, 472, "· 服務閒置 600 秒自動停止，整棵行程樹一併結束。", 12.5, MUTED)]
# bottom: QA
b += [box(40, 520, 1120, 156, fill="#222a39", rx=14), t(60, 548, "③ 自我審核：沒通過就不發佈", 17, TXT, 600)]
qa = [("容器規格", "H.264／AAC、解析度、漂移"), ("片長與比例", "符合承諾；廣告 ±0.3 秒"),
      ("畫面", "全黑、過曝、凍結、幻燈片"), ("聲音", "−14 LUFS、真峰值、削波、靜音"),
      ("字幕", "閱讀速度、覆蓋率、ASR 同步"), ("廣告專屬", "商品時長、字卡、宣稱檢查")]
qw = (1080 - 5 * 10) / 6
for i, (n, d) in enumerate(qa):
    x = 60 + i * (qw + 10)
    b += [box(x, 566, qw, 60, fill=PANEL), t(x + qw / 2, 590, n, 14, TXT, 600, "middle"), t(x + qw / 2, 610, d, 11.5, MUTED, 400, "middle")]
b += [t(60, 656, "不合格時自動修正可修的項目（兩段式 loudnorm、影音漂移重新封裝），再重新檢查；通過後才進入「發佈」關卡並寫入 final/。", 13, MUTED)]
(OUT / "how-it-works.svg").write_text(svg(W, H, "\n".join(b), "Midea 運作原理"), encoding="utf-8")

# ------------------------------------------------------------------ 3. workflow
W, H = 1200, 640
b = [t(40, 52, "工作流程", 26, TXT, 700), t(40, 78, "三條主要流程；◆ 為審核關卡（暫停等人決定），其他步驟自動執行", 14, MUTED)]
def lane(y, title, sub, steps, color):
    out = [box(40, y, 1120, 150, fill="#222a39", rx=14), t(60, y + 28, title, 17, TXT, 600), t(60 + len(title) * 18 + 16, y + 28, sub, 13, MUTED)]
    n = len(steps); gap = 12; w = (1080 - gap * (n - 1)) / n
    for i, (name, model, gate) in enumerate(steps):
        x = 60 + i * (w + gap)
        out.append(box(x, y + 48, w, 76, fill=PANEL2 if gate else PANEL, stroke=AMBER if gate else LINE, sw=1.6 if gate else 1.2))
        out.append(t(x + w / 2, y + 76, ("◆ " if gate else "") + name, 13.5 if n < 12 else 12.5, AMBER if gate else TXT, 700 if gate else 600, "middle"))
        for j, m in enumerate(model.split("|")):
            out.append(t(x + w / 2, y + 96 + j * 15, m, 11, MUTED, 400, "middle"))
        if i < n - 1:
            out.append(arrow(x + w + 1, y + 86, x + w + gap - 1, y + 86))
    return out
b += lane(100, "影片製作", "midea make / 看板「影片製作」· 12 條管線共用此骨架",
          [("企劃", "Qwen", 1), ("腳本", "Qwen", 1), ("分鏡", "含預估花費", 1), ("旁白", "VoxCPM2", 0), ("素材", "H3 · 真實素材|動態圖形", 1),
           ("配樂音效", "ACE-Step|Foley · SFX", 0), ("剪輯", "轉場、字幕對齊", 0), ("合成", "響度、調色|燒字幕", 0), ("自我審核", "QA 11 類", 0), ("發佈", "寫入 final/", 1)], LAV)
b += lane(266, "廣告製作 ad-60", "看板「廣告製作」· 標準或時尚大片風格",
          [("商品解析", "事實表、去背|主色", 1), ("商品定裝", "Qwen-Edit|姿態驗收", 1), ("創意提案", "3 方向|10 秒預覽", 1), ("文案大綱", "宣稱檢查|雙語", 1),
           ("分鏡", "關鍵分鏡圖|規則檢查", 1), ("旁白", "演員聲音|或低沉旁白", 0), ("素材", "H3 I2V|分鏡圖為首格", 1), ("配樂", "ACE-Step", 0),
           ("剪輯合成", "字卡、片尾卡", 0), ("多版本", "60/15 秒 ×|16:9 9:16 1:1", 0), ("自我審核", "＋廣告檢查", 0), ("發佈", "6 支影片|＋附件", 1)], AMBER)
b += lane(432, "虛擬演員", "看板「演員陣容」· 完成後可在任何描述中以 @代號 指定演出",
          [("一句話描述", "Qwen 補完設定", 0), ("定妝照", "Z-Image|大頭＋全身", 1), ("三視圖", "Qwen-Edit|¾、側面、背面", 0), ("姿態驗收", "RTMW|失敗自動重生", 0),
           ("專屬聲音", "VoxCPM2|各語言樣本", 0), ("說話影片", "H3 對嘴|字錯率＋聲紋", 0), ("可被 @ 使用", "跨片同臉同聲", 0)], TEAL)
b += [t(60, 612, "外貌或聲音修改後，三視圖與說話影片會標記為過期，演員頁會提示重做；演員頁也列出他出演過的所有影片。", 13, MUTED)]
(OUT / "workflow.svg").write_text(svg(W, H, "\n".join(b), "Midea 工作流程"), encoding="utf-8")

# ------------------------------------------------------------------ 4. operation
W, H = 1200, 340
b = [t(40, 52, "操作說明", 26, TXT, 700), t(40, 78, "從開啟看板到下載成品的五個步驟", 14, MUTED)]
steps = [("1", "登入看板", ["瀏覽器開 :10030", "輸入 .env 中的帳密", "左上切換三個分頁"]),
         ("2", "建立演員", ["演員陣容 → 新增演員", "一句話描述，AI 補完", "確認定妝照（選用）"]),
         ("3", "開始製作", ["影片：寫描述、選管線", "廣告：主演＋商品網址", "選風格、配樂、規格"]),
         ("4", "審核關卡", ["◆ 出現時檢視內容", "核准／退回寫意見", "逐鏡勾選重畫或重生"]),
         ("5", "下載成品", ["最後核准「發佈」", "final/ 影片、字幕", "分鏡 PDF、文案、README"])]
sw_ = (1120 - 4 * 24) / 5
for i, (num, name, ls) in enumerate(steps):
    x = 40 + i * (sw_ + 24)
    b += [box(x, 104, sw_, 200, fill=PANEL), f'<circle cx="{x + 30}" cy="{138}" r="16" fill="{AMBER}"/>',
          t(x + 30, 143, num, 15, BG, 800, "middle"), t(x + 56, 144, name, 17, TXT, 700)]
    for j, ln in enumerate(ls):
        b.append(t(x + 18, 186 + j * 26, ln, 13.5, MUTED if not ln.startswith("◆") else AMBER))
    if i < 4:
        b.append(arrow(x + sw_ + 3, 204, x + sw_ + 21, 204, AMBER, head="am"))
(OUT / "operation.svg").write_text(svg(W, H, "\n".join(b), "Midea 操作說明"), encoding="utf-8")
print("ok")
