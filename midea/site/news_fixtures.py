"""Offline material for the daily reports in mock mode and tests.

Facts come from real reports of early November 2026 (AI Weekly 11/6, Shareuhack's GitHub weekly for 10/14–10/21,
arXiv 2610.00812), one per template, so every layout can be previewed without the network or Qwen.
"""
from __future__ import annotations

import copy

AIW = "AI Weekly 11/6"
AIW_URL = "https://aiweekly.co/ai-news-today/edition/2026-11-06"
GH_URL = "https://www.shareuhack.com/en/posts/github-trending-weekly-2026-10-21"
PAPER_URL = "https://arxiv.org/abs/2610.00812"

CANDIDATES = [
    {"kind": "news", "title": "Chip stocks slide: SOX down 12%", "url": AIW_URL + "#chips", "source": AIW,
     "summary": "The Nasdaq 100 fell 6.4% on Thursday, erasing $2.3T in market value; the Philadelphia semiconductor index dropped 12%."},
    {"kind": "repo", "title": "GitHub weekly star gains", "url": GH_URL, "source": "Shareuhack GitHub 週報", "roundup": True,
     "summary": "morluto/rea +201,065; debpalash/VoiceStudio +17,291; storytold/artcraft +13,572; boykopovar/AnyPS5 +12,389; MadsLorentzen/ai-job-search +9,073."},
    {"kind": "paper", "title": "Video Generation Models: A Survey of Post-Training and Alignment", "url": PAPER_URL, "source": "arXiv 2610.00812",
     "summary": "First comprehensive review of post-training and alignment in video generation models; four categories of methods."},
    {"kind": "news", "title": "Google's $17B Wyoming data center", "url": AIW_URL + "#google", "source": AIW,
     "summary": "A $17B data center in Laramie County, Wyoming, powered by a 702 MW on-site fuel-cell system with carbon capture."},
    {"kind": "news", "title": "Thinking Machines Lab raising $5B", "url": AIW_URL + "#tml", "source": "Business Insider（經 AI Weekly）",
     "summary": "Closing a $5B round led by Accel at a $40B pre-money valuation, more than triple its roughly $12B valuation last year."},
    {"kind": "news", "title": "Meta pauses scraping terms", "url": AIW_URL + "#meta", "source": AIW,
     "summary": "Meta indefinitely paused a commercial-terms update set for November 20 after pushback from publishers and regulators."},
    {"kind": "repo", "title": "VoiceStudio vs ai-job-search", "url": GH_URL + "#local", "source": "Shareuhack GitHub 週報",
     "summary": "Two local-first AI tools on this week's list: voice work and job search."},
]

FIT = {
    "Chip stocks slide: SOX down 12%": {"brief": 1.0},
    "GitHub weekly star gains": {"ranking": 1.0},
    "Video Generation Models: A Survey of Post-Training and Alignment": {"paper": 1.0},
    "Google's $17B Wyoming data center": {"howto": 1.0},
    "Thinking Machines Lab raising $5B": {"story": 1.0},
    "Meta pauses scraping terms": {"timeline": 1.0},
    "VoiceStudio vs ai-job-search": {"versus": 1.0},
}

ARTICLES = {
    "brief": {
        "title": "晶片股單日重挫，費城半導體指數跌 12%",
        "dek": "Nasdaq 100 跌 6.4%，市值少了 2.3 兆美元；市場擔心期中選舉後資料中心擴建放緩。",
        "headline_number": {"display": "−12%", "label": "費城半導體指數 · 11/5 單日"},
        "points": ["Nasdaq 100 跌 6.4%，市值少 2.3 兆美元。", "Nvidia 與 Qualcomm 各跌超過 9%。", "市場擔心期中選舉後資料中心擴建放緩。"],
        "paragraphs": ["11/5（四）美股科技股重挫，費城半導體指數單日下跌 12%，是這次跌幅最大的指數。",
                       "Nvidia 與 Qualcomm 各跌超過 9%。報導指出，市場擔心期中選舉結果會讓資料中心的擴建速度放慢。"],
        "why": "AI 晶片的需求來自資料中心；擴建放慢，影響的是整條供應鏈。",
        "figure": {"type": "bars", "title": "11/5（四）單日跌幅", "unit": "%", "highlight": 0,
                   "rows": [{"label": "費城半導體指數", "value": -12, "display": "−12%"}, {"label": "Nvidia", "value": -9, "display": "逾 −9%"},
                            {"label": "Qualcomm", "value": -9, "display": "逾 −9%"}, {"label": "Nasdaq 100", "value": -6.4, "display": "−6.4%"}]},
        "quiz": {"q": "這次哪一個指數跌得最多？", "options": ["Nasdaq 100", "費城半導體指數", "道瓊工業指數"], "answer": 1},
    },
    "ranking": {
        "title": "GitHub 本週：逆向工程代理 rea 一週多 20 萬顆星",
        "dek": "週增星數前五名裡，VoiceStudio 與 ai-job-search 都強調在本機執行。",
        "intro": "10/14–10/21 這一週，GitHub 上星數增加最多的五個專案。",
        "items": [{"name": "morluto/rea", "desc": "把 AI 代理接上逆向工程", "value": 201065, "display": "+201,065"},
                  {"name": "debpalash/VoiceStudio", "desc": "本機聲音複製、配音、聽寫", "value": 17291, "display": "+17,291"},
                  {"name": "storytold/artcraft", "desc": "—", "value": 13572, "display": "+13,572"},
                  {"name": "boykopovar/AnyPS5", "desc": "—", "value": 12389, "display": "+12,389"},
                  {"name": "MadsLorentzen/ai-job-search", "desc": "本機履歷、求職信、面試準備", "value": 9073, "display": "+9,073"}],
        "paragraphs": ["rea 一週增加的星數，是第二名的十倍以上。星數代表關注度，不等於實際採用。"],
        "why": "看開發者這週在注意什麼：AI 代理與在自己電腦上執行的工具。",
        "figure": {"type": "ranking", "title": "10/14–10/21 週增星數", "highlight": 0,
                   "items": [{"name": "morluto/rea", "value": 201065, "display": "+201,065"},
                             {"name": "debpalash/VoiceStudio", "value": 17291, "display": "+17,291"},
                             {"name": "storytold/artcraft", "value": 13572, "display": "+13,572"},
                             {"name": "boykopovar/AnyPS5", "value": 12389, "display": "+12,389"},
                             {"name": "MadsLorentzen/ai-job-search", "value": 9073, "display": "+9,073"}]},
    },
    "paper": {
        "title": "影片模型怎麼「調教」：一篇後訓練與對齊的綜述",
        "dek": "把方法分成四類，並說明影片為什麼比圖片難對齊：錯誤會隨時間累積。",
        "oneline": "第一篇整理「影片模型預訓練之後，怎麼再調整」的綜述，把方法分成四類。",
        "method": "整理既有研究，分成監督微調、自我訓練與蒸餾、偏好與獎勵、推論時方法。",
        "findings": "影片比圖片難對齊：錯誤會隨時間累積、動作與外觀互相牽動、目標彼此拉扯，以及時間上的監督資料太少。",
        "limits": "綜述沒有附程式碼，也沒有統一的基準數字。",
        "midea": "演員影片的動作一致性，可以參考「推論時方法」。",
        "figure": {"type": "categories", "center": "預訓練影片模型", "highlight": 2,
                   "items": [{"label": "監督微調", "sub": "SFT"}, {"label": "自我訓練與蒸餾", "sub": "Self-training"},
                             {"label": "偏好與獎勵", "sub": "Preference / Reward"}, {"label": "推論時方法", "sub": "Inference-time"}]},
        "quiz": {"q": "哪一類是在生成當下才調整，不必重新訓練？", "options": ["監督微調", "偏好與獎勵", "推論時方法"], "answer": 2},
    },
    "howto": {
        "title": "Google 在懷俄明州蓋 170 億美元資料中心，用燃料電池供電",
        "dek": "702 MW 現場燃料電池由 Bloom Energy 建置，搭配碳捕捉。",
        "steps": [{"title": "天然氣進場", "text": "Tallgrass Energy 等合作夥伴供應。"},
                  {"title": "燃料電池發電 702 MW", "text": "Bloom Energy 建置，American Electric Power 簽約採購。"},
                  {"title": "碳捕捉", "text": "發電產生的二氧化碳被捕捉。"},
                  {"title": "供給資料中心", "text": "位於拉勒米郡，投資 170 億美元。"}],
        "paragraphs": ["Black Hills Energy 與 Related Digital 也是合作夥伴。"],
        "why": "AI 資料中心的電力需求大，供電方式成了選址的關鍵。",
        "figure": {"type": "flow", "highlight": 1, "branch": {"label": "碳捕捉", "from": 1},
                   "nodes": [{"label": "天然氣", "sub": "Tallgrass"}, {"label": "燃料電池 702 MW", "sub": "Bloom Energy"},
                             {"label": "資料中心", "sub": "170 億美元"}]},
    },
    "story": {
        "title": "Thinking Machines Lab 一年估值翻三倍多",
        "dek": "Accel 領投，投前估值 400 億美元；去年種子輪時約 120 億。",
        "steps": [{"title": "去年的種子輪", "text": "募得 20 億美元，估值約 120 億美元。", "highlight": 0},
                  {"title": "這一輪", "text": "募 50 億美元，Accel 領投，投前估值 400 億美元。", "highlight": 1},
                  {"title": "還有 Nvidia", "text": "Nvidia 另外洽談投資約 25 億美元。", "highlight": 1}],
        "why": "AI 新創的估值變化，反映資金對模型公司的期待。",
        "figure": {"type": "bars", "title": "估值（億美元）", "unit": " 億", "highlight": 1,
                   "rows": [{"label": "去年種子輪", "value": 120, "display": "約 120 億"}, {"label": "這一輪（投前）", "value": 400, "display": "400 億"}]},
    },
    "timeline": {
        "title": "Meta 無限期暫停「抓取商家網站」的條款更新",
        "dek": "原定 11/20 生效的商業條款，在出版商與監管機關反對後喊停。",
        "events": [{"date": "原定 11/20", "text": "條款生效，允許抓取 Meta Business 帳戶所屬網站的內容。"},
                   {"date": "公布後", "text": "出版商反對，挪威與巴西的監管機關表達疑慮。"},
                   {"date": "11/6 前後", "text": "Meta 宣布無限期暫停這次更新。"},
                   {"date": "接下來", "text": "是否修改條款後重新推出。"}],
        "paragraphs": ["這次暫停沒有說明重新推出的時間。"],
        "why": "AI 訓練資料從哪裡來，是平台、出版商與監管機關角力的焦點。",
        "figure": {"type": "timeline", "highlight": 2,
                   "events": [{"date": "原定 11/20", "text": "條款生效"}, {"date": "公布後", "text": "出版商與監管機關反對"},
                              {"date": "11/6 前後", "text": "無限期暫停"}, {"date": "接下來", "text": "是否重新推出"}]},
    },
    "versus": {
        "title": "兩個本機 AI 工具：VoiceStudio 與 ai-job-search",
        "dek": "都上了本週 GitHub 週增星數前五名，都強調在自己的電腦上執行。",
        "sides": [{"name": "VoiceStudio", "desc": "聲音複製、聲音設計、配音、聽寫、有聲書", "value": 17291, "display": "+17,291", "points": ["本機 API", "支援 MCP"]},
                  {"name": "ai-job-search", "desc": "評估職缺、調整履歷、寫求職信、面試準備", "value": 9073, "display": "+9,073", "points": ["本機流程"]}],
        "same": "都強調在自己的電腦上執行，資料不離開本機。",
        "diff": "一個處理聲音，一個處理求職文件。",
        "figure": {"type": "compare", "value_label": "10/14–10/21 週增星數",
                   "sides": [{"name": "VoiceStudio", "value": 17291, "display": "+17,291"}, {"name": "ai-job-search", "value": 9073, "display": "+9,073"}]},
    },
}


def article_for(title: str, template: str) -> dict:
    """The fixture article for a candidate (sequels reuse the original's template content with a new title)."""
    art = copy.deepcopy(ARTICLES[template])
    if title.startswith("續作："):
        art["title"] = "續作：" + art["title"]
        art["dek"] = "依讀者的問題，再看一次這個題目。"
    art.setdefault("sections", [
        {"heading": "發生了什麼", "paragraphs": [art["dek"], "（示範資料：正式版由 AI 依多個來源寫成 2000 字以上的分析。）"]},
        {"heading": "背後的脈絡", "paragraphs": [art.get("why") or art["dek"]]},
        {"heading": "接下來看什麼", "paragraphs": ["之後的發展會在續作裡追蹤。"]}])
    art.setdefault("follow", ["這件事接下來會怎麼發展？", "還有哪些人會受到影響？"])
    art.setdefault("cover_prompt", "an abstract editorial illustration of light and data on a dark desk")
    art["sources"] = []
    return art
