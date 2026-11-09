"""每日報導: five AI-written articles every morning, readers' feedback, follow-ups, and two report videos a week.

Daily run (06:00 Asia/Taipei, `site.news.daily_at`):
  1. collect   — news feeds (RSS/Atom), GitHub (repositories created in the last 7 days with the most stars, plus one
                 「本週新星」 roundup), arXiv (newest papers in the configured categories). Sequel requests from
                 readers (「想看續作」 ≥ threshold) join as candidates that must be written.
  2. pick      — Qwen picks five topics (at least one GitHub and one paper when there are any) and scores how well
                 each of the seven templates fits the topic (0–1).
  3. template  — weighted random draw among templates scoring ≥ 0.5, at most two per template per day, and the
                 same source kind does not use yesterday's template again (`choose_template`).
  4. write     — Qwen writes the template's JSON (text + a figure *spec*). Every number in the figure has to appear
                 in the source text, otherwise it is rewritten once and then replaced by a figure without numbers.
  5. publish   — straight to the site (status `live`); admins can hide an article afterwards in /studio.

Weekly run (Monday 06:30): from last Monday–Sunday's articles pick one 「編輯選」 (Qwen judges which is most worth a
video) and one 「觀眾選」 (highest feedback score), and create two platform projects in the studio, presented by the
reporter actor. They go through the normal gates and the listing review.

Mock mode (`MIDEA_MODE=mock`) uses `news_fixtures` instead of the network and Qwen.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta
from html import unescape
from typing import Any, Callable
from xml.etree import ElementTree as ET

from ..config import settings
from ..log import get_logger
from . import news_svg
from .community import norm, rules_check
from .programming import TZ, now_local, week_start
from .store import Store

log = get_logger("site.news")

SCHEMA = """
CREATE TABLE IF NOT EXISTS article (
  id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, day TEXT NOT NULL, rank INTEGER NOT NULL DEFAULT 0,
  kind TEXT NOT NULL, template TEXT NOT NULL, title TEXT NOT NULL, dek TEXT NOT NULL, body TEXT NOT NULL,
  figure TEXT, sources TEXT NOT NULL DEFAULT '[]', fit TEXT, status TEXT NOT NULL DEFAULT 'live', note TEXT,
  sequel_of INTEGER, video_project TEXT, video_pick TEXT, minutes INTEGER NOT NULL DEFAULT 2, created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS article_day ON article(day, rank);
CREATE TABLE IF NOT EXISTS article_react (
  article INTEGER NOT NULL, viewer INTEGER NOT NULL, kind TEXT NOT NULL, anon INTEGER NOT NULL, at REAL NOT NULL,
  PRIMARY KEY (article, viewer, kind)
);
CREATE TABLE IF NOT EXISTS article_read (
  article INTEGER NOT NULL, viewer INTEGER NOT NULL, done INTEGER NOT NULL DEFAULT 0, at REAL NOT NULL,
  PRIMARY KEY (article, viewer)
);
CREATE TABLE IF NOT EXISTS article_quiz (
  article INTEGER NOT NULL, viewer INTEGER NOT NULL, choice INTEGER NOT NULL, at REAL NOT NULL, PRIMARY KEY (article, viewer)
);
CREATE TABLE IF NOT EXISTS article_question (
  id INTEGER PRIMARY KEY, article INTEGER NOT NULL, viewer INTEGER NOT NULL, para INTEGER, quote TEXT, text TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'shown', reason TEXT, checked INTEGER NOT NULL DEFAULT 0, answered_in INTEGER, at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS article_question_a ON article_question(article, status);
CREATE TABLE IF NOT EXISTS article_qsupport (
  question INTEGER NOT NULL, viewer INTEGER NOT NULL, at REAL NOT NULL, PRIMARY KEY (question, viewer)
);
CREATE TABLE IF NOT EXISTS news_run (
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, key TEXT NOT NULL, status TEXT NOT NULL, tries INTEGER NOT NULL DEFAULT 1,
  started REAL NOT NULL, finished REAL, result TEXT, error TEXT, UNIQUE (kind, key)
);
"""

REACTS = {"helpful": "有幫助", "sequel": "想看續作", "video": "做成影片", "question": "有疑問"}
KINDS = {"news": "新聞", "repo": "GitHub", "paper": "論文"}
TEMPLATES = {
    "brief":    {"name": "快訊", "fit": "單一事件，有一個關鍵數字（漲跌、金額、人數）", "figure": "bars"},
    "story":    {"name": "數據故事", "fit": "同一主題有 3 個以上的數據點、前後變化或趨勢", "figure": "bars"},
    "ranking":  {"name": "排行榜", "fit": "天然是名單：GitHub 熱門、模型排名、下載數", "figure": "ranking"},
    "timeline": {"name": "時間軸", "fit": "事情有先後：政策、訴訟、產品上市、延宕", "figure": "timeline"},
    "versus":   {"name": "對照", "fit": "兩個東西可以並排比：產品、方案、前後兩版", "figure": "compare"},
    "howto":    {"name": "圖解", "fit": "在講一個系統或流程怎麼運作", "figure": "flow"},
    "paper":    {"name": "論文速讀", "fit": "arXiv 等論文", "figure": "categories"},
}
QUESTION_MAX, QUESTIONS_PER_DAY = 80, 5
UA = "MideaNews/1.0 (+https://midea.cafeca.io)"


def cfg(key: str, default: Any = None) -> Any:
    v = settings().get(f"site.news.{key}")
    return default if v is None else v


def is_mock() -> bool:
    return settings().mode == "mock"


# ================================================================================================ template choice
def choose_template(scores: dict[str, float], kind: str, used_today: Counter, yesterday: dict[str, str],
                    rng: random.Random | None = None, threshold: float = 0.5, per_day: int = 2) -> str:
    """Weighted random draw among the templates that fit (score ≥ threshold).

    Rules: a template appears at most `per_day` times a day; a source kind does not repeat yesterday's template.
    Relaxed in that order when nothing is left; the last resort is the kind's natural template."""
    rng = rng or random.Random()
    sc = {t: max(0.0, min(1.0, float(s or 0))) for t, s in (scores or {}).items() if t in TEMPLATES}

    def pool(th: float, avoid_yesterday: bool) -> dict[str, float]:
        return {t: s for t, s in sc.items() if s >= th and used_today[t] < per_day
                and not (avoid_yesterday and yesterday.get(kind) == t)}
    for th, avoid in ((threshold, True), (threshold, False), (0.0001, False)):
        p = pool(th, avoid)
        if p:
            ts = sorted(p)
            return rng.choices(ts, weights=[p[t] for t in ts], k=1)[0]
    return {"paper": "paper", "repo": "ranking"}.get(kind, "brief")


# ================================================================================================ sources
def _get(url: str, *, accept: str | None = None, timeout: float = 20) -> str:
    import httpx
    h = {"User-Agent": UA}
    if accept:
        h["Accept"] = accept
    r = httpx.get(url, headers=h, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return r.text


def _strip(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|nav|header|footer|aside|form|noscript)[^>]*>.*?</\1>", " ", html)
    paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", html) or [html]
    text = "\n".join(unescape(re.sub(r"<[^>]+>", " ", p)) for p in paras)
    text = re.sub(r"[ \t ]+", " ", text)
    return "\n".join(ln.strip() for ln in text.splitlines() if len(ln.strip()) > 30)


def _feed(url: str, limit: int = 12) -> list[dict]:
    root = ET.fromstring(_get(url, accept="application/rss+xml, application/atom+xml, application/xml"))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    src = (root.findtext("channel/title") or root.findtext("a:title", namespaces=ns) or url).strip()
    for it in root.findall("channel/item")[:limit]:
        out.append({"title": (it.findtext("title") or "").strip(), "url": (it.findtext("link") or "").strip(),
                    "summary": _strip(it.findtext("description") or "")[:600], "published": it.findtext("pubDate") or "", "source": src})
    for it in root.findall("a:entry", ns)[:limit]:
        link = it.find("a:link", ns)
        out.append({"title": (it.findtext("a:title", namespaces=ns) or "").strip(), "url": link.get("href") if link is not None else "",
                    "summary": _strip(it.findtext("a:summary", namespaces=ns) or it.findtext("a:content", namespaces=ns) or "")[:600],
                    "published": it.findtext("a:updated", namespaces=ns) or "", "source": src})
    return [x for x in out if x["title"] and x["url"]]


def collect_news() -> list[dict]:
    out = []
    for url in cfg("feeds", []) or []:
        try:
            for x in _feed(url):
                out.append({"kind": "news", **x})
        except Exception as e:  # noqa: BLE001
            log.warning("news feed %s: %s", url, e)
    return out


def collect_github(day: date) -> list[dict]:
    since = (day - timedelta(days=7)).isoformat()
    try:
        j = json.loads(_get(f"https://api.github.com/search/repositories?q=created:%3E{since}&sort=stars&order=desc&per_page=15",
                            accept="application/vnd.github+json"))
    except Exception as e:  # noqa: BLE001
        log.warning("github search: %s", e)
        return []
    repos = [{"name": r["full_name"], "url": r["html_url"], "desc": (r.get("description") or "")[:200], "stars": r["stargazers_count"],
              "lang": r.get("language") or "", "created": r["created_at"][:10]} for r in j.get("items", [])]
    if not repos:
        return []
    lines = "\n".join(f"{i + 1}. {r['name']}（{r['lang'] or '—'}，{r['created']} 建立）：{r['stars']} 顆星。{r['desc']}" for i, r in enumerate(repos[:10]))
    out = [{"kind": "repo", "title": f"過去 7 天新建、星數最多的 GitHub 專案（{since} 起）", "url": "https://github.com/search?q=created%3A%3E"
            + since + "&s=stars&o=desc&type=repositories", "summary": lines[:600], "text": lines, "source": "GitHub", "roundup": True}]
    for r in repos[:6]:
        out.append({"kind": "repo", "title": r["name"], "url": r["url"], "summary": f"{r['desc']}（{r['stars']} 顆星，{r['created']} 建立）",
                    "source": "GitHub", "repo": r})
    return out


def collect_arxiv() -> list[dict]:
    cats = cfg("arxiv_categories", ["cs.CV", "cs.CL", "cs.AI", "cs.LG"])
    q = "+OR+".join(f"cat:{c}" for c in cats)
    try:
        root = ET.fromstring(_get(f"https://export.arxiv.org/api/query?search_query={q}&sortBy=submittedDate&sortOrder=descending&max_results=30"))
    except Exception as e:  # noqa: BLE001
        log.warning("arxiv: %s", e)
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in root.findall("a:entry", ns):
        abs_ = re.sub(r"\s+", " ", e.findtext("a:summary", namespaces=ns) or "").strip()
        aid = (e.findtext("a:id", namespaces=ns) or "").rsplit("/", 1)[-1]
        authors = [a.findtext("a:name", namespaces=ns) for a in e.findall("a:author", ns)]
        out.append({"kind": "paper", "title": re.sub(r"\s+", " ", e.findtext("a:title", namespaces=ns) or "").strip(),
                    "url": f"https://arxiv.org/abs/{aid}", "summary": abs_[:600], "text": abs_, "source": f"arXiv {re.sub(r'v[0-9]+$', '', aid)}",
                    "authors": authors[:6], "n_authors": len(authors)})
    return out


def fetch_text(c: dict) -> str:
    """Full source text for the writer (≤ 8000 characters)."""
    if c.get("text"):
        return c["text"][:8000]
    try:
        if c["kind"] == "repo" and c.get("repo"):
            readme = _get(f"https://api.github.com/repos/{c['repo']['name']}/readme", accept="application/vnd.github.raw")
            return (c["summary"] + "\n\nREADME:\n" + re.sub(r"<[^>]+>", "", readme))[:8000]
        return (c.get("summary", "") + "\n\n" + _strip(_get(c["url"])))[:8000]
    except Exception as e:  # noqa: BLE001
        log.info("source text %s: %s", c.get("url"), e)
        return c.get("summary", "")


# ================================================================================================ fact check
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(spec: Any) -> list[str]:
    """Every number that the figure would print."""
    found: list[str] = []
    if isinstance(spec, dict):
        for k, v in spec.items():
            if k in ("highlight", "from", "type", "i"):
                continue
            found += _numbers(v)
    elif isinstance(spec, list):
        for v in spec:
            found += _numbers(v)
    elif isinstance(spec, (int, float)) and not isinstance(spec, bool):
        found.append(f"{abs(spec):g}")
    elif isinstance(spec, str):
        found += [m.replace(",", "") for m in _NUM.findall(spec)]
    return found


def unverified_numbers(spec: dict | None, source: str) -> list[str]:
    """Numbers in the figure that do not appear in the source text (commas ignored; years and 1–9 are free)."""
    if not spec:
        return []
    src = source.replace(",", "")
    bad = []
    for n in _numbers({k: v for k, v in spec.items() if k not in ("title", "alt")} | {"_t": spec.get("title", "")}):
        n2 = n.rstrip("0").rstrip(".") if "." in n else n
        if len(n2) <= 1 or re.fullmatch(r"(19|20)\d\d", n2):
            continue
        if n2 not in src and n not in src:
            bad.append(n)
    return bad


# ================================================================================================ LLM prompts
PICK_SYSTEM = (
    "You are the morning editor of Midea, a Traditional Chinese AI video platform. From the candidate list pick exactly "
    "{n} topics for today's reports. Rules: include every candidate marked must=true; include at least one 'repo' and one "
    "'paper' candidate when available; prefer stories with concrete numbers, broad interest, technology/AI/science/culture; "
    "avoid duplicates of the recent titles; avoid tragedies, crime victims, accusations against private persons, and "
    "medical/investment advice. For each pick score how well each template fits (0–1): {templates}. "
    "Return {{\"picks\": [{{\"index\": <int>, \"angle\": \"一句話角度（繁中）\", \"fit\": {{\"brief\": 0.0, ...}}}}]}}.")

WRITE_SYSTEM = (
    "You write a short report for Midea (Traditional Chinese, Taiwan usage, plain and calm, no exclamation marks, no emoji, "
    "no hype words like 超/爆/必看). Put a space between Chinese and Latin letters or digits (例：OpenAI 傳以 1.25 兆美元). "
    "24-hour time; dates like 11/9（一）. Keep product and paper names in their original "
    "language. Use ONLY facts and numbers from the SOURCE; never invent numbers, quotes or names. A chart compares like with "
    "like: every row/side in one figure has the SAME unit and measures the same kind of thing (never mix counts, percents, "
    "seconds and money in one chart); if the source has no comparable set, use another figure type or fewer rows. "
    "If the source lacks a "
    "number, leave it out. Write for curious general readers; explain jargon in one clause. "
    "Template: {template} — {fit}. Return JSON with these fields:\n{schema}\n"
    "Common fields: title (≤ 30 字), dek (≤ 60 字), why (為什麼重要, ≤ 60 字), quiz (optional: {{\"q\": str, \"options\": [3 short strings], "
    "\"answer\": index}} — answerable from the article), tags (≤ 3 short strings).")

SCHEMAS = {
    "brief": '{"points": [3 sentences], "paragraphs": [2–3 paragraphs], "figure": {"type": "bars", "title": str, "unit": str, "rows": [{"label": str, "value": number, "display": str}], "highlight": 0}, "headline_number": {"display": str, "label": str}}',
    "story": '{"steps": [{"title": str, "text": str, "highlight": index of the figure row this step talks about}] (3–5 steps), "figure": {"type": "bars", "title": str, "unit": str, "rows": [...]}}',
    "ranking": '{"intro": str, "items": [{"name": str, "desc": str (≤ 30 字), "value": number, "display": str, "url": str}] (5–10), "figure": {"type": "ranking", "title": str, "items": same names/values}, "paragraphs": [1–2 paragraphs]}',
    "timeline": '{"events": [{"date": str, "text": str (≤ 40 字)}] (3–6, oldest first; use 「接下來」 for what to watch), "figure": {"type": "timeline", "events": same, "highlight": index of the newest real event}, "paragraphs": [1–2]}',
    "versus": '{"sides": [{"name": str, "desc": str, "value": number or null, "display": str, "points": [≤ 3 short strings]}] (exactly 2), "same": str, "diff": str, "figure": {"type": "compare", "value_label": str, "sides": same 2 with name/value/display}, "paragraphs": [1–2]}',
    "howto": '{"steps": [{"title": str, "text": str}] (3–5), "figure": {"type": "flow", "nodes": [{"label": str (≤ 10 字), "sub": str}] (3–4), "highlight": index, "branch": {"label": str, "from": index} or null}, "paragraphs": [1]}',
    "paper": '{"oneline": str, "method": str, "findings": str, "limits": str, "midea": str (what it means for an AI video studio, ≤ 50 字), "figure": {"type": "categories", "center": str (≤ 8 字), "items": [{"label": str, "sub": str}] (3–6)}}',
}

WEEKLY_SYSTEM = (
    "You are the editor of Midea's weekly report videos (60–90 s, presented by a virtual reporter). Score each article "
    "0–1 on: importance (0.30), visual potential — numbers that can animate or a process that can be drawn (0.25), "
    "still meaningful a week later (0.20), fit with Midea viewers interested in AI, video, technology and culture (0.15), "
    "source reliability (0.10). Mark excluded=true for accusations against real people, unresolved lawsuits, harm, or a "
    "single unclear source. Return {\"scores\": [{\"id\": <id>, \"total\": 0.0, \"reason\": \"一句話理由（繁中）\", \"excluded\": false}]}.")


# ================================================================================================ the newsroom
class Newsroom:
    def __init__(self, store: Store, *, community=None, catalog=None):
        self.s, self.com, self.cat = store, community, catalog
        with store._wlock:
            store.db.executescript(SCHEMA)
        self._busy = threading.Lock()
        self.rng = random.Random()

    # ------------------------------------------------------------ scheduling (called every minute)
    def tick(self, now: datetime | None = None) -> str | None:
        if not cfg("enabled", True):
            return None
        now = now or now_local()
        hh, mm = (int(x) for x in str(cfg("daily_at", "06:00")).split(":"))
        if (now.hour, now.minute) >= (hh, mm) and self._due("daily", now.date().isoformat()):
            self.run_daily(now.date())
            return "daily"
        wd, wt = int(cfg("weekly_weekday", 0)), str(cfg("weekly_at", "06:30"))
        wh, wm = (int(x) for x in wt.split(":"))
        if now.weekday() == wd and (now.hour, now.minute) >= (wh, wm) and self._due("weekly", week_start(now.date()).isoformat()):
            self.run_weekly(now.date())
            return "weekly"
        return None

    def _due(self, kind: str, key: str) -> bool:
        r = self.s.one("SELECT status, tries, started FROM news_run WHERE kind=? AND key=?", (kind, key))
        if not r:
            return True
        return r["status"] == "failed" and r["tries"] < int(cfg("max_tries", 3)) and time.time() - r["started"] > float(cfg("retry_s", 1800))

    def _start(self, kind: str, key: str) -> bool:
        with self.s.tx() as c:
            r = c.execute("SELECT status, tries FROM news_run WHERE kind=? AND key=?", (kind, key)).fetchone()
            if r and r["status"] in ("running", "done"):
                return False
            if r:
                c.execute("UPDATE news_run SET status='running', tries=tries+1, started=?, error=NULL WHERE kind=? AND key=?",
                          (time.time(), kind, key))
            else:
                c.execute("INSERT INTO news_run(kind, key, status, started) VALUES(?,?,'running',?)", (kind, key, time.time()))
        return True

    def _finish(self, kind: str, key: str, ok: bool, result: Any = None, error: str | None = None) -> None:
        with self.s.tx() as c:
            c.execute("UPDATE news_run SET status=?, finished=?, result=?, error=? WHERE kind=? AND key=?",
                      ("done" if ok else "failed", time.time(), json.dumps(result, ensure_ascii=False) if result is not None else None,
                       error, kind, key))

    def runs(self, limit: int = 20) -> list[dict]:
        return [dict(r) | {"result": json.loads(r["result"]) if r["result"] else None}
                for r in self.s.q("SELECT * FROM news_run ORDER BY started DESC LIMIT ?", (limit,))]

    # ------------------------------------------------------------ daily
    def run_daily(self, day: date | None = None, *, force: bool = False) -> dict:
        day = day or now_local().date()
        key = day.isoformat()
        if force:
            with self.s.tx() as c:
                c.execute("DELETE FROM news_run WHERE kind='daily' AND key=?", (key,))
        if not self._busy.acquire(blocking=False):
            return {"busy": True}
        try:
            if not self._start("daily", key):
                return {"skipped": True}
            try:
                out = self._daily(day)
                self._finish("daily", key, True, out)
                return out
            except Exception as e:  # noqa: BLE001
                log.exception("daily reports failed")
                self._finish("daily", key, False, error=str(e)[:500])
                return {"error": str(e)}
        finally:
            self._busy.release()

    def _daily(self, day: date) -> dict:
        n = int(cfg("per_day", 5))
        have = self.s.q("SELECT id FROM article WHERE day=? AND status='live'", (day.isoformat(),))
        if len(have) >= n:
            return {"articles": len(have), "note": "already published"}
        cands = self.candidates(day)
        if not cands:
            raise RuntimeError("沒有收集到任何來源")
        picks = self.pick(cands, n - len(have))
        used = Counter(r["template"] for r in self.s.q("SELECT template FROM article WHERE day=?", (day.isoformat(),)))
        yday = {r["kind"]: r["template"] for r in self.s.q("SELECT kind, template FROM article WHERE day=?",
                                                         ((day - timedelta(days=1)).isoformat(),))}
        made = []
        for p in picks:
            c = cands[p["index"]]
            t = choose_template(p.get("fit") or {}, c["kind"], used, yday, self.rng)
            try:
                art = self.write(c, t, p.get("angle") or "")
            except Exception as e:  # noqa: BLE001
                log.warning("write failed for %s: %s", c.get("title"), e)
                continue
            used[t] += 1
            made.append(self.publish(day, c, t, art, p.get("fit") or {}, rank=self._next_rank(day)))
        if not made:
            raise RuntimeError("五篇都沒有寫成")
        return {"articles": [m["slug"] for m in made], "templates": [m["template"] for m in made]}

    def _next_rank(self, day: date) -> int:
        r = self.s.one("SELECT MAX(rank) m FROM article WHERE day=?", (day.isoformat(),))
        return 0 if r is None or r["m"] is None else int(r["m"]) + 1

    def candidates(self, day: date) -> list[dict]:
        if is_mock():
            from .news_fixtures import CANDIDATES
            cands = [dict(c) for c in CANDIDATES]
        else:
            cands = collect_news() + collect_github(day) + collect_arxiv()
        rows = self.s.q("SELECT title, sources FROM article WHERE day>=?", ((day - timedelta(days=14)).isoformat(),))
        urls = {json.loads(r["sources"])[0]["url"] for r in rows if json.loads(r["sources"])}
        titles = [r["title"] for r in rows]
        cands = [c for c in cands if c.get("url") not in urls and not any(_similar(c["title"], t) > 0.8 for t in titles)]
        return self.sequel_requests() + cands

    def sequel_requests(self) -> list[dict]:
        th = int(cfg("sequel_threshold", 20))
        rows = self.s.q("""SELECT a.*, (SELECT COUNT(*) FROM article_react r WHERE r.article=a.id AND r.kind='sequel') n
                           FROM article a WHERE a.status='live' AND a.day>=? AND NOT EXISTS (SELECT 1 FROM article b WHERE b.sequel_of=a.id)
                           ORDER BY n DESC LIMIT 2""", ((now_local().date() - timedelta(days=10)).isoformat(),))
        out = []
        for a in rows:
            if a["n"] < th:
                continue
            qs = self.questions(a["id"], None, limit=5)
            src = json.loads(a["sources"])
            text = (f"這是續作。原文《{a['title']}》：{a['dek']}\n原文內容：{_article_text(a)}\n"
                    f"讀者最想知道（依 +1）：" + "；".join(f"{q['text']}（+{q['supporters']}）" for q in qs))
            out.append({"kind": a["kind"], "title": f"續作：{a['title']}", "url": src[0]["url"] if src else "", "summary": a["dek"],
                        "text": text, "source": src[0]["source"] if src else "Midea 報導", "must": True, "sequel_of": a["id"],
                        "readers": int(a["n"]), "answers": [q["id"] for q in qs]})
        return out

    def pick(self, cands: list[dict], n: int) -> list[dict]:
        must = [i for i, c in enumerate(cands) if c.get("must")][:n]
        if is_mock():
            from .news_fixtures import FIT
            idx = must + [i for i in range(len(cands)) if i not in must][: n - len(must)]
            return [{"index": i, "angle": "", "fit": FIT.get(cands[i]["title"], {"brief": 0.7})} for i in idx]
        from ..providers.llm import llm
        lst = [{"index": i, "kind": c["kind"], "title": c["title"], "source": c.get("source"), "summary": c.get("summary", "")[:300],
                "must": bool(c.get("must"))} for i, c in enumerate(cands[:80])]
        sys = PICK_SYSTEM.format(n=n, templates=json.dumps({k: v["fit"] for k, v in TEMPLATES.items()}, ensure_ascii=False))
        try:
            out = llm().json("news_pick", sys, json.dumps(lst, ensure_ascii=False), max_tokens=4096)
            picks = [p for p in (out.get("picks") or []) if isinstance(p, dict) and isinstance(p.get("index"), int) and 0 <= p["index"] < len(cands)]
        except Exception as e:  # noqa: BLE001
            log.warning("pick fell back to rules: %s", e)
            picks = []
        seen, res = set(), []
        for i in must:
            p = next((x for x in picks if x["index"] == i), {"index": i, "fit": {}})
            res.append(p)
            seen.add(i)
        for p in picks:
            if len(res) >= n:
                break
            if p["index"] not in seen:
                res.append(p)
                seen.add(p["index"])
        for want in ("repo", "paper"):                          # at least one GitHub and one paper when there are any
            if any(cands[x["index"]]["kind"] == want for x in res):
                continue
            alt = next((i for i, c in enumerate(cands) if c["kind"] == want and i not in seen), None)
            if alt is None:
                continue
            slot = next((k for k in range(len(res) - 1, -1, -1) if not cands[res[k]["index"]].get("must")
                         and sum(cands[x["index"]]["kind"] == cands[res[k]["index"]]["kind"] for x in res) > 1), None)
            if slot is not None and len(res) >= n:
                seen.discard(res[slot]["index"])
                res[slot] = {"index": alt, "fit": {}}
            else:
                res.append({"index": alt, "fit": {}})
            seen.add(alt)
        for want in ("repo", "paper", "news"):                  # rule fallback: fill by kind, newest first
            for i, c in enumerate(cands):
                if len(res) >= n:
                    break
                if i not in seen and c["kind"] == want and not any(cands[x["index"]]["kind"] == want for x in res):
                    res.append({"index": i, "fit": {}})
                    seen.add(i)
        for i, c in enumerate(cands):
            if len(res) >= n:
                break
            if i not in seen:
                res.append({"index": i, "fit": {}})
                seen.add(i)
        for p in res:                                            # sensible defaults when the model gave no scores
            if not p.get("fit"):
                k = cands[p["index"]]["kind"]
                p["fit"] = {"paper": {"paper": 0.9}, "repo": {"ranking": 0.9} if cands[p["index"]].get("roundup") else {"brief": 0.6, "howto": 0.5}}.get(k, {"brief": 0.7, "timeline": 0.5})
        return res[:n]

    def write(self, c: dict, template: str, angle: str) -> dict:
        if is_mock():
            from .news_fixtures import article_for
            return article_for(c["title"], template)
        from ..providers.llm import llm
        source = fetch_text(c)
        sys = WRITE_SYSTEM.format(template=TEMPLATES[template]["name"], fit=TEMPLATES[template]["fit"], schema=SCHEMAS[template])
        user = json.dumps({"angle": angle, "kind": KINDS[c["kind"]], "source_name": c.get("source"), "url": c.get("url"),
                           "title": c["title"], "SOURCE": source}, ensure_ascii=False)
        art = llm().json("news_write", sys, user, max_tokens=4096)
        issue = _figure_issue(art.get("figure"), source)
        if issue:
            art = llm().json("news_write", sys, user + f"\n\nFix the figure: {issue}", max_tokens=4096)
            if _figure_issue(art.get("figure"), source):
                art["figure"] = _numberless_figure(art, template)
        art = _spaced(art)
        problems = validate(art, template)
        if problems:
            raise ValueError("; ".join(problems))
        art["_source_text"] = source[:2000]
        return art

    def publish(self, day: date, c: dict, template: str, art: dict, fit: dict, rank: int) -> dict:
        slug = f"{day.isoformat()}-{hashlib.sha1((c.get('url') or c['title']).encode()).hexdigest()[:6]}"
        sources = [{"title": c["title"], "url": c.get("url", ""), "source": c.get("source", "")}] + \
                  [s for s in (art.get("sources") or []) if isinstance(s, dict) and s.get("url")][:3]
        fig = art.get("figure")
        body = {k: v for k, v in art.items() if k not in ("title", "dek", "figure", "sources", "_source_text")}
        if c.get("sequel_of"):
            body["readers"] = c.get("readers")
        words = len(json.dumps(body, ensure_ascii=False))
        with self.s.tx() as cx:
            cx.execute("INSERT OR REPLACE INTO article(slug, day, rank, kind, template, title, dek, body, figure, sources, fit, status, "
                       "sequel_of, minutes, created) VALUES(?,?,?,?,?,?,?,?,?,?,?,'live',?,?,?)",
                       (slug, day.isoformat(), rank, c["kind"], template, _clean(art["title"])[:60], _clean(art["dek"])[:120],
                        json.dumps(body, ensure_ascii=False), json.dumps(fig, ensure_ascii=False) if fig else None,
                        json.dumps(sources, ensure_ascii=False), json.dumps(fit), c.get("sequel_of"), max(1, round(words / 450)), time.time()))
            aid = cx.execute("SELECT id FROM article WHERE slug=?", (slug,)).fetchone()["id"]
            for q in c.get("answers") or []:
                cx.execute("UPDATE article_question SET answered_in=? WHERE id=?", (aid, q))
        return {"slug": slug, "template": template}

    # ------------------------------------------------------------ reading
    def get(self, slug: str) -> Any:
        return self.s.one("SELECT * FROM article WHERE slug=?", (slug,))

    def counts(self, aid: int) -> dict[str, int]:
        c = {k: 0 for k in REACTS}
        for r in self.s.q("SELECT kind, COUNT(*) n FROM article_react WHERE article=? GROUP BY kind", (aid,)):
            c[r["kind"]] = int(r["n"])
        return c

    def card(self, a, *, full: bool = False, viewer: int | None = None) -> dict:
        fig = json.loads(a["figure"]) if a["figure"] else None
        d = {"slug": a["slug"], "day": a["day"], "kind": a["kind"], "kind_label": KINDS[a["kind"]], "template": a["template"],
             "template_label": TEMPLATES[a["template"]]["name"], "title": a["title"], "dek": a["dek"], "minutes": a["minutes"],
             "sources": json.loads(a["sources"]), "counts": self.counts(a["id"]), "status": a["status"],
             "sequel_threshold": int(cfg("sequel_threshold", 20)), "date_label": _day_label(a["day"]),
             "published": now_local(a["created"]).strftime("%H:%M"), "mini": news_svg.mini(fig),
             "lead_fig": news_svg.render(fig)["wide"], "video": self.video_of(a)}
        if a["sequel_of"]:
            o = self.s.one("SELECT slug, title FROM article WHERE id=?", (a["sequel_of"],))
            d["sequel_of"] = dict(o) if o else None
        if full:
            body = json.loads(a["body"])
            d |= {"body": body, "figure": news_svg.render(fig), "figure_spec": fig}
            mine = [r["kind"] for r in self.s.q("SELECT kind FROM article_react WHERE article=? AND viewer=?", (a["id"], viewer))] if viewer else []
            d["mine"] = mine
            quiz = body.get("quiz")
            if isinstance(quiz, dict) and quiz.get("options"):
                tally = Counter(r["choice"] for r in self.s.q("SELECT choice FROM article_quiz WHERE article=?", (a["id"],)))
                my = self.s.one("SELECT choice FROM article_quiz WHERE article=? AND viewer=?", (a["id"], viewer)) if viewer else None
                total = sum(tally.values())
                d["quiz"] = {"q": quiz.get("q"), "options": quiz["options"], "mine": my["choice"] if my else None,
                             "answer": quiz.get("answer") if my else None, "total": total,
                             "right": round(100 * tally.get(int(quiz.get("answer") or 0), 0) / total) if total else None}
            d["sequels"] = [{"slug": r["slug"], "title": r["title"]} for r in self.s.q("SELECT slug, title FROM article WHERE sequel_of=? AND status='live'", (a["id"],))]
            d["reads"] = int(self.s.one("SELECT COUNT(*) n FROM article_read WHERE article=?", (a["id"],))["n"])
        return d

    def video_of(self, a) -> dict | None:
        if not a["video_project"]:
            return None
        out = {"pick": a["video_pick"], "label": "編輯選" if a["video_pick"] == "editor" else "觀眾選", "status": "producing"}
        if self.cat:
            vs = self.cat.versions(a["video_project"])
            if vs:
                out |= {"status": "ready", "id": vs[0].id, "image": vs[0].image}
        return out

    def day_list(self, day: str | None = None) -> tuple[str | None, list]:
        if not day:
            r = self.s.one("SELECT day FROM article WHERE status='live' ORDER BY day DESC LIMIT 1")
            day = r["day"] if r else None
        if not day:
            return None, []
        return day, list(self.s.q("SELECT * FROM article WHERE day=? AND status='live' ORDER BY rank", (day,)))

    def today(self) -> dict:
        day, rows = self.day_list()
        follow = []
        for a in self.s.q("SELECT * FROM article WHERE status='live' AND sequel_of IS NOT NULL ORDER BY created DESC LIMIT 3"):
            follow.append({"type": "sequel", **self.card(a)})
        for a in self.s.q("SELECT * FROM article WHERE status='live' AND video_project IS NOT NULL ORDER BY created DESC LIMIT 3"):
            follow.append({"type": "video", **self.card(a)})
        sources = sum(len(json.loads(r["sources"])) for r in rows)
        run = self.s.one("SELECT result FROM news_run WHERE kind='daily' AND key=?", (day,)) if day else None
        return {"day": day, "date_label": _day_label(day) if day else None, "articles": [self.card(a) for a in rows],
                "followups": follow[:3], "sources": sources, "at": cfg("daily_at", "06:00"), "has_run": bool(run)}

    def archive(self, days: int = 14) -> list[dict]:
        out = []
        for r in self.s.q("SELECT DISTINCT day FROM article WHERE status='live' ORDER BY day DESC LIMIT ?", (days,)):
            out.append({"day": r["day"], "label": _day_label(r["day"]), "articles": [self.card(a) for a in self.day_list(r["day"])[1]]})
        return out

    # ------------------------------------------------------------ feedback
    def react(self, aid: int, viewer: int, kind: str, on: bool, *, anon: bool) -> dict:
        if kind not in REACTS:
            raise ValueError("unknown reaction")
        with self.s.tx() as c:
            if on:
                c.execute("INSERT OR IGNORE INTO article_react(article, viewer, kind, anon, at) VALUES(?,?,?,?,?)",
                          (aid, viewer, kind, int(anon), time.time()))
            else:
                c.execute("DELETE FROM article_react WHERE article=? AND viewer=? AND kind=?", (aid, viewer, kind))
        return {"counts": self.counts(aid), "mine": [r["kind"] for r in self.s.q("SELECT kind FROM article_react WHERE article=? AND viewer=?", (aid, viewer))]}

    def read(self, aid: int, viewer: int, done: bool) -> None:
        with self.s.tx() as c:
            c.execute("INSERT INTO article_read(article, viewer, done, at) VALUES(?,?,?,?) "
                      "ON CONFLICT(article, viewer) DO UPDATE SET done=MAX(done, excluded.done), at=excluded.at",
                      (aid, viewer, int(done), time.time()))

    def answer_quiz(self, aid: int, viewer: int, choice: int) -> None:
        with self.s.tx() as c:
            c.execute("INSERT OR IGNORE INTO article_quiz(article, viewer, choice, at) VALUES(?,?,?,?)", (aid, viewer, int(choice), time.time()))

    def questions_left(self, viewer: int) -> int:
        n = self.s.one("SELECT COUNT(*) n FROM article_question WHERE viewer=? AND at>?", (viewer, time.time() - 86400))["n"]
        return max(0, QUESTIONS_PER_DAY - int(n))

    def ask(self, v, aid: int, text: str, para: int | None, quote: str | None) -> dict:
        if self.com:
            ok, why = self.com.writer_state(v)
            if not ok:
                raise PermissionError(why)
        t = norm(text)
        if not t:
            raise ValueError("請寫下你的問題")
        if len(t) > QUESTION_MAX:
            raise ValueError(f"問題最多 {QUESTION_MAX} 字")
        if self.questions_left(int(v["id"])) <= 0:
            raise OverflowError(f"每天最多問 {QUESTIONS_PER_DAY} 題，明天再來")
        cat = rules_check(t)
        if cat and cat != "ads":
            from .community import CATEGORY
            raise ValueError(f"這則問題沒有送出：疑似{CATEGORY.get(cat, '不當')}內容")
        with self.s.tx() as c:
            qid = c.execute("INSERT INTO article_question(article, viewer, para, quote, text, at) VALUES(?,?,?,?,?,?)",
                            (aid, int(v["id"]), para, norm(quote or "")[:120] or None, t, time.time())).lastrowid
        return {"id": qid, "left": self.questions_left(int(v["id"]))}

    def support(self, qid: int, viewer: int, on: bool) -> int:
        if not self.s.one("SELECT 1 FROM article_question WHERE id=? AND status='shown'", (qid,)):
            raise LookupError("找不到這個問題")
        with self.s.tx() as c:
            if on:
                c.execute("INSERT OR IGNORE INTO article_qsupport(question, viewer, at) VALUES(?,?,?)", (qid, viewer, time.time()))
            else:
                c.execute("DELETE FROM article_qsupport WHERE question=? AND viewer=?", (qid, viewer))
        return int(self.s.one("SELECT COUNT(*) n FROM article_qsupport WHERE question=?", (qid,))["n"])

    def questions(self, aid: int, viewer: int | None, limit: int = 20) -> list[dict]:
        rows = self.s.q("""SELECT q.*, v.nickname, v.handle, (SELECT COUNT(*) FROM article_qsupport s WHERE s.question=q.id) n,
                           (SELECT slug FROM article b WHERE b.id=q.answered_in) ans
                           FROM article_question q JOIN viewer v ON v.id=q.viewer WHERE q.article=? AND q.status='shown'
                           ORDER BY n DESC, q.id DESC LIMIT ?""", (aid, limit))
        mine = {r["question"] for r in self.s.q("SELECT question FROM article_qsupport WHERE viewer=?", (viewer,))} if viewer else set()
        return [{"id": r["id"], "text": r["text"], "para": r["para"], "quote": r["quote"], "supporters": int(r["n"]),
                 "by": r["nickname"] or r["handle"] or "讀者", "mine": r["viewer"] == viewer, "supported": r["id"] in mine,
                 "answered_in": r["ans"]} for r in rows]

    def set_status(self, slug: str, status: str, note: str = "") -> None:
        if status not in ("live", "hidden"):
            raise ValueError("status")
        with self.s.tx() as c:
            c.execute("UPDATE article SET status=?, note=? WHERE slug=?", (status, note[:200] or None, slug))

    # ------------------------------------------------------------ weekly videos
    def feedback_score(self, aid: int) -> dict:
        """做成影片 ×3 + 想看續作 ×2 + 段落問題的 +1 ×1 + 有幫助 ×0.5 + 讀完人數 / 100; anonymous reactions ≤ 30 %."""
        rows = self.s.q("SELECT kind, anon, COUNT(*) n FROM article_react WHERE article=? GROUP BY kind, anon", (aid,))
        eff: dict[str, float] = {}
        raw: dict[str, int] = {}
        for k in REACTS:
            signed = sum(r["n"] for r in rows if r["kind"] == k and not r["anon"])
            anon = sum(r["n"] for r in rows if r["kind"] == k and r["anon"])
            eff[k] = signed + min(anon, signed * 3 / 7)
            raw[k] = signed + anon
        sup = int(self.s.one("SELECT COUNT(*) n FROM article_qsupport s JOIN article_question q ON q.id=s.question "
                             "WHERE q.article=? AND q.status='shown'", (aid,))["n"])
        done = int(self.s.one("SELECT COUNT(*) n FROM article_read WHERE article=? AND done=1", (aid,))["n"])
        score = 3 * eff["video"] + 2 * eff["sequel"] + sup + 0.5 * eff["helpful"] + done / 100
        people = int(self.s.one("SELECT COUNT(DISTINCT viewer) n FROM (SELECT viewer FROM article_react WHERE article=? "
                                "UNION SELECT s.viewer FROM article_qsupport s JOIN article_question q ON q.id=s.question WHERE q.article=?)",
                                (aid, aid))["n"])
        return {"score": round(score, 1), "video": raw["video"], "sequel": raw["sequel"], "helpful": raw["helpful"],
                "support": sup, "done": done, "people": people}

    def run_weekly(self, today: date | None = None, *, force: bool = False) -> dict:
        today = today or now_local().date()
        key = week_start(today).isoformat()
        if force:
            with self.s.tx() as c:
                c.execute("DELETE FROM news_run WHERE kind='weekly' AND key=?", (key,))
        if not self._start("weekly", key):
            return {"skipped": True}
        try:
            out = self._weekly(week_start(today))
            self._finish("weekly", key, True, out)
            return out
        except Exception as e:  # noqa: BLE001
            log.exception("weekly report videos failed")
            self._finish("weekly", key, False, error=str(e)[:500])
            return {"error": str(e)}

    def _weekly(self, monday: date) -> dict:
        start, end = monday - timedelta(days=7), monday - timedelta(days=1)
        arts = list(self.s.q("SELECT * FROM article WHERE status='live' AND day BETWEEN ? AND ? AND video_project IS NULL",
                             (start.isoformat(), end.isoformat())))
        if not arts:
            return {"note": "上週沒有報導"}
        fb = {a["id"]: self.feedback_score(a["id"]) for a in arts}
        audience = max(arts, key=lambda a: (fb[a["id"]]["score"], fb[a["id"]]["done"]))
        ed = self.editor_scores(arts)
        ranked = sorted((a for a in arts if not ed[a["id"]].get("excluded")), key=lambda a: -ed[a["id"]]["total"])
        editor = next((a for a in ranked if a["id"] != audience["id"]), None)
        picks = []
        for a, who in ((editor, "editor"), (audience, "audience")):
            if a is None:
                continue
            note = ed[a["id"]].get("reason") if who == "editor" else f"依 {fb[a['id']]['people']} 位讀者的反饋（{fb[a['id']]['score']} 分）"
            pid = self.make_video(a, who, note, fb[a["id"]])
            with self.s.tx() as c:
                c.execute("UPDATE article SET video_project=?, video_pick=? WHERE id=?", (pid, who, a["id"]))
            picks.append({"pick": who, "slug": a["slug"], "title": a["title"], "project": pid, "note": note,
                          "score": ed[a["id"]]["total"] if who == "editor" else fb[a["id"]]["score"]})
        return {"week": f"{start.isoformat()}–{end.isoformat()}", "picks": picks, "considered": len(arts)}

    def editor_scores(self, arts: list) -> dict[int, dict]:
        base = {"howto": 0.8, "story": 0.75, "paper": 0.72, "versus": 0.65, "timeline": 0.6, "ranking": 0.6, "brief": 0.5}
        default = {a["id"]: {"total": base.get(a["template"], 0.5), "reason": f"{TEMPLATES[a['template']]['name']}的內容適合做成動態圖卡"} for a in arts}
        if is_mock():
            return default
        from ..providers.llm import llm
        payload = [{"id": a["id"], "title": a["title"], "dek": a["dek"], "template": TEMPLATES[a["template"]]["name"],
                    "sources": [s.get("source") for s in json.loads(a["sources"])]} for a in arts]
        try:
            out = llm().json("news_weekly", WEEKLY_SYSTEM, json.dumps(payload, ensure_ascii=False), max_tokens=4096)
            for s in out.get("scores") or []:
                if isinstance(s, dict) and s.get("id") in default:
                    default[s["id"]] = {"total": float(s.get("total") or 0), "reason": str(s.get("reason") or "")[:80],
                                        "excluded": bool(s.get("excluded"))}
        except Exception as e:  # noqa: BLE001
            log.warning("weekly editor scoring fell back to template rules: %s", e)
        return default

    make_video_hook: Callable[[dict, str], str] | None = None   # tests can replace project creation

    def make_video(self, a, who: str, note: str, fb: dict) -> str:
        """A platform project in the studio: the reporter actor presents the article; the figure becomes animated cards."""
        body = json.loads(a["body"])
        reporter = cfg("reporter", "yen_lin")
        secs = 90 if who == "editor" else 60
        points = _article_text(a)[:900]
        lead = "" if who == "editor" else f"開頭一句說明：這部影片依 {fb['people']} 位讀者的反饋製作。"
        prompt = (f"製作一支 {secs} 秒的新聞解說影片，由 @{reporter} 擔任主播播報。題目：{a['title']}。{a['dek']}"
                  f"重點：{points}。把文章的數據圖做成動態圖卡（{TEMPLATES[a['template']]['name']}）。{lead}"
                  f"片尾寫出來源：{'、'.join(s.get('source', '') for s in json.loads(a['sources']))}，以及「AI 撰寫 · 演員皆為虛擬角色」。")
        brief = {"prompt": prompt, "duration_s": secs, "aspect": "16:9", "aspect_locked": True, "language": "zh-TW",
                 "music": True, "subtitles": True, "source_article": a["slug"], "news_pick": who, "news_note": note,
                 "figure": json.loads(a["figure"]) if a["figure"] else None, "quiz": body.get("quiz")}
        if self.make_video_hook:
            return self.make_video_hook(brief, who)
        from .. import actors as AC
        from ..pipelines import route, run_async
        from ..project import Project
        brief["actors"] = AC.resolve_list([reporter])
        p = Project.create(brief, cfg("video_pipeline", "") or route(brief | {"prompt": brief["prompt"] + " 解釋"}), owner="")
        if not is_mock() and cfg("weekly_autostart", True):
            run_async(p)
        return p.id


# ================================================================================================ helpers
def validate(art: dict, template: str) -> list[str]:
    p = []
    for k in ("title", "dek"):
        if not str(art.get(k) or "").strip():
            p.append(f"missing {k}")
    need = {"brief": ["points", "paragraphs"], "story": ["steps"], "ranking": ["items"], "timeline": ["events"],
            "versus": ["sides"], "howto": ["steps"], "paper": ["oneline", "method", "findings"]}[template]
    for k in need:
        if not art.get(k):
            p.append(f"missing {k}")
    if template == "versus" and len(art.get("sides") or []) != 2:
        p.append("versus needs two sides")
    text = json.dumps({k: v for k, v in art.items() if k not in ("figure", "sources")}, ensure_ascii=False)
    cat = rules_check(re.sub(r"https?://\S+", "", text))
    if cat and cat not in ("ads",):
        p.append(f"rules: {cat}")
    return p


_GENERIC_UNIT = re.compile(r"^(數值|數字|依各行.*|各.*|混合|mixed|various|n/?a|)$", re.I)


def mixed_units(spec: dict | None) -> bool:
    """A bar chart whose rows measure different things (count vs percent vs seconds) — misleading on one scale."""
    if not spec or spec.get("type") not in ("bars", "ranking", "compare"):
        return False
    rows = spec.get("rows") or spec.get("items") or spec.get("sides") or []
    if len(rows) < 2:
        return False
    if spec.get("type") == "bars" and _GENERIC_UNIT.match(str(spec.get("unit") or "").strip()):
        tails = {re.sub(r"[\d.,+\-−\s約逾]", "", str(r.get("display") or "")) for r in rows}
        if len(tails) != 1 or tails == {""}:
            return True
    paren = {m.group(1) for r in rows for m in [re.search(r"[（(]([^）)]+)[）)]\s*$", str(r.get("label") or r.get("name") or ""))] if m}
    suffix = {re.sub(r"[\d.,+\-−\s約逾]", "", str(r.get("display") or "")) for r in rows if r.get("display")}
    return len(paren) > 1 or len(suffix) > 1


def _figure_issue(spec: dict | None, source: str) -> str | None:
    bad = unverified_numbers(spec, source)
    if bad:
        return f"numbers not in the SOURCE: {bad}; use only numbers from the SOURCE, or drop that row"
    if mixed_units(spec):
        return "rows use different units or measure different things; keep only rows with one shared unit, or use another figure type"
    return None


_CJK = r"\u3400-\u9fff\uf900-\ufaff"


def spaced(t: str) -> str:
    """盤古之白：中文與英數之間加空格（不動網址）。"""
    if not isinstance(t, str) or "://" in t:
        return t
    t = re.sub(rf"([{_CJK}])([A-Za-z0-9$])", r"\1 \2", t)
    return re.sub(rf"([A-Za-z0-9%])([{_CJK}])", r"\1 \2", t)


def _spaced(v: Any, key: str = "") -> Any:
    if isinstance(v, dict):
        return {k: (x if k in ("url", "type") else _spaced(x, k)) for k, x in v.items()}
    if isinstance(v, list):
        return [_spaced(x, key) for x in v]
    return spaced(v) if isinstance(v, str) else v


def _numberless_figure(art: dict, template: str) -> dict | None:
    if template == "timeline" and art.get("events"):
        return {"type": "timeline", "events": [{"date": e.get("date", ""), "text": e.get("text", "")} for e in art["events"]]}
    steps = art.get("steps") or [{"title": x} for x in (art.get("points") or [])]
    nodes = [{"label": re.sub(_NUM, "", str(s.get("title") or s.get("text") or ""))[:10], "sub": ""} for s in steps[:4] if isinstance(s, dict)]
    return {"type": "flow", "nodes": nodes, "highlight": 0} if nodes else None


def _article_text(a) -> str:
    b = json.loads(a["body"]) if isinstance(a["body"], str) else a["body"]
    parts: list[str] = []
    for k in ("points", "paragraphs"):
        parts += [str(x) for x in b.get(k) or []]
    for k in ("steps", "events", "items", "sides"):
        for x in b.get(k) or []:
            if isinstance(x, dict):
                parts.append("：".join(str(x.get(f)) for f in ("title", "date", "name", "text", "desc", "display") if x.get(f)))
    for k in ("oneline", "method", "findings", "limits", "same", "diff", "why"):
        if b.get(k):
            parts.append(str(b[k]))
    return "；".join(parts)


def _clean(t: Any) -> str:
    return re.sub(r"\s+", " ", str(t or "")).strip()


def _similar(a: str, b: str) -> float:
    from .community import similar
    return similar(a, b)


WEEK = "一二三四五六日"


def _day_label(day: str) -> str:
    d = date.fromisoformat(day)
    return f"{d.month}/{d.day}（{WEEK[d.weekday()]}）"
