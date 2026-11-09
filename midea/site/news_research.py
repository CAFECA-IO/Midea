"""Research for the daily reports: each picked topic gets a *dossier* — the material Qwen writes the deep analysis from.

- news:   the story itself + related coverage of the same event (other feeds collected today, and stories linked
          from Hacker News in the last 14 days), so the article can follow how the story developed and who is involved.
- GitHub: the repository as a project and as code — metadata, README, the file tree, two or three key source files,
          the commit history (first commit, pace, contributors), and the author (profile and other projects).
- paper:  the abstract plus the paper's full HTML text from arxiv.org/html when it exists.

Every part is labelled `[n] <source>` so the writer can cite it; the list of sources is returned with the text.
Set `GITHUB_TOKEN` to raise GitHub's anonymous limit (60 requests an hour; one repository uses about 9).
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any
from urllib.parse import quote

from ..log import get_logger

log = get_logger("site.news.research")

CODE_EXT = (".py", ".ts", ".tsx", ".js", ".mjs", ".go", ".rs", ".java", ".kt", ".swift", ".c", ".cc", ".cpp", ".h", ".rb",
            ".php", ".cs", ".scala", ".zig", ".lua", ".sh")
SKIP_DIR = re.compile(r"(^|/)(node_modules|vendor|dist|build|\.github|tests?|docs?|examples?|assets?|static|third_party)(/|$)", re.I)
STOP = {"the", "and", "for", "with", "from", "that", "this", "into", "over", "after", "about", "their", "what", "will", "your",
        "says", "said", "new", "how", "why", "are", "its", "has", "have", "now", "more", "than", "just", "report", "reportedly"}


def _get(url: str, *, accept: str | None = None, timeout: float = 20, github: bool = False) -> Any:
    import httpx
    h = {"User-Agent": "MideaNews/1.0 (+https://midea.cafeca.io)"}
    if accept:
        h["Accept"] = accept
    if github and os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    r = httpx.get(url, headers=h, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return r


def _gh(path: str, raw: bool = False) -> Any:
    r = _get("https://api.github.com" + path, accept="application/vnd.github.raw" if raw else "application/vnd.github+json", github=True)
    return r.text if raw else r.json()


class Pack:
    """Labelled source parts with a size budget."""

    def __init__(self, budget: int = 22000):
        self.parts: list[str] = []
        self.sources: list[dict] = []
        self.left = budget

    def add(self, label: str, text: str, url: str = "", limit: int = 6000, cite: bool = True) -> None:
        text = (text or "").strip()
        if not text or self.left <= 200:
            return
        text = text[:min(limit, self.left)]
        n = len(self.sources) + 1 if cite else None
        head = f"[{n}] {label}" + (f" <{url}>" if url else "") if n else f"[背景] {label}"
        self.parts.append(f"{head}\n{text}")
        self.left -= len(text)
        if n:
            self.sources.append({"n": n, "source": label, "url": url})

    def text(self) -> str:
        return "\n\n".join(self.parts)


# ------------------------------------------------------------------------------------------------ news
def keywords(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9.+-]{2,}", text or "")
    out = []
    for w in words:
        lw = w.lower().strip(".")
        if lw not in STOP and lw not in out:
            out.append(lw)
    return out[:6]


def related_news(c: dict, pool: list[dict], query: str | None, strip, limit: int = 4) -> list[dict]:
    """Other coverage of the same event: today's feed items sharing keywords, then Hacker News stories."""
    kw = keywords(query or "") or keywords(c.get("title", "") + " " + c.get("summary", ""))
    found: list[dict] = []
    seen = {c.get("url")}
    for x in pool:
        if x.get("url") in seen or x.get("kind") != "news":
            continue
        hay = (x.get("title", "") + " " + x.get("summary", "")).lower()
        if len(kw) >= 2 and sum(k in hay for k in kw) >= 2:
            found.append({"title": x["title"], "url": x["url"], "source": x.get("source", "")})
            seen.add(x["url"])
    if kw:
        try:
            since = int(time.time()) - 14 * 86400
            j = _get("https://hn.algolia.com/api/v1/search?tags=story&numericFilters=created_at_i>" + str(since) +
                     "&query=" + quote(" ".join(kw[:4]))).json()
            for h in sorted(j.get("hits", []), key=lambda h: -(h.get("points") or 0)):
                if h.get("url") and h["url"] not in seen:
                    found.append({"title": h.get("title", ""), "url": h["url"], "source": re.sub(r"^www\.", "", h["url"].split("/")[2]),
                                  "hn": f"https://news.ycombinator.com/item?id={h['objectID']}", "points": h.get("points")})
                    seen.add(h["url"])
        except Exception as e:  # noqa: BLE001
            log.info("hn search: %s", e)
    out = []
    for f in found:
        if len(out) >= limit:
            break
        try:
            t = strip(_get(f["url"]).text)
        except Exception:  # noqa: BLE001
            continue
        if len(t) > 400:
            out.append(f | {"text": t})
    return out


def news_dossier(c: dict, pool: list[dict], query: str | None, strip) -> Pack:
    p = Pack()
    main = c.get("text") or ""
    if not main:
        try:
            main = c.get("summary", "") + "\n\n" + strip(_get(c["url"]).text)
        except Exception as e:  # noqa: BLE001
            log.info("story text %s: %s", c.get("url"), e)
            main = c.get("summary", "")
    p.add(c.get("source") or "原始報導", main, c.get("url", ""), limit=7000)
    for r in related_news(c, pool, query, strip):
        p.add(r["source"] or r["title"], f"{r['title']}\n{r['text']}", r["url"], limit=3500)
    return p


# ------------------------------------------------------------------------------------------------ GitHub
def _key_files(tree: list[dict], lang: str) -> list[str]:
    files = [t for t in tree if t.get("type") == "blob" and t["path"].endswith(CODE_EXT) and not SKIP_DIR.search(t["path"])
             and 400 < (t.get("size") or 0) < 60000]

    def score(t: dict) -> float:
        path, name = t["path"], t["path"].rsplit("/", 1)[-1].lower()
        s = 0.0
        if re.match(r"(main|index|app|cli|server|core|engine|lib|agent|run|__main__)\.", name):
            s += 3
        s -= path.count("/") * 0.7
        s += min(t.get("size", 0), 20000) / 10000
        if "test" in path.lower() or "spec" in name:
            s -= 4
        return s
    return [t["path"] for t in sorted(files, key=score, reverse=True)[:3]]


def github_dossier(full: str) -> Pack:
    p = Pack(budget=24000)
    repo = _gh(f"/repos/{full}")
    owner = repo["owner"]["login"]
    meta = {k: repo.get(k) for k in ("full_name", "description", "homepage", "language", "stargazers_count", "forks_count",
                                     "open_issues_count", "created_at", "pushed_at", "topics")}
    meta["license"] = (repo.get("license") or {}).get("spdx_id")
    p.add(f"GitHub {full}（專案資料）", json.dumps(meta, ensure_ascii=False), repo["html_url"], limit=1200)
    try:
        p.add(f"{full} README", re.sub(r"<[^>]+>", "", _gh(f"/repos/{full}/readme", raw=True)), repo["html_url"] + "#readme", limit=7000)
    except Exception as e:  # noqa: BLE001
        log.info("readme %s: %s", full, e)
    tree: list[dict] = []
    try:
        tree = _gh(f"/repos/{full}/git/trees/{repo['default_branch']}?recursive=1").get("tree", [])
        paths = [t["path"] + ("/" if t["type"] == "tree" else "") for t in tree if t["path"].count("/") <= 2][:160]
        p.add(f"{full} 檔案結構", "\n".join(paths), repo["html_url"], limit=2500, cite=False)
    except Exception as e:  # noqa: BLE001
        log.info("tree %s: %s", full, e)
    for path in _key_files(tree, repo.get("language") or ""):
        try:
            code = _gh(f"/repos/{full}/contents/{quote(path)}?ref={repo['default_branch']}", raw=True)
            p.add(f"{full}/{path}（原始碼）", code, f"{repo['html_url']}/blob/{repo['default_branch']}/{path}", limit=3500)
        except Exception as e:  # noqa: BLE001
            log.info("file %s/%s: %s", full, path, e)
    try:
        commits = _gh(f"/repos/{full}/commits?per_page=30")
        lines = [f"{c['commit']['author']['date'][:10]} {c['commit']['author']['name']}: {c['commit']['message'].splitlines()[0][:100]}" for c in commits]
        p.add(f"{full} 最近的提交", "\n".join(lines), repo["html_url"] + "/commits", limit=2500)
    except Exception as e:  # noqa: BLE001
        log.info("commits %s: %s", full, e)
    try:
        contrib = _gh(f"/repos/{full}/contributors?per_page=6")
        p.add(f"{full} 貢獻者", ", ".join(f"{c['login']}（{c['contributions']} 次提交）" for c in contrib), repo["html_url"] + "/graphs/contributors", limit=600)
    except Exception as e:  # noqa: BLE001
        log.info("contributors %s: %s", full, e)
    try:
        u = _gh(f"/users/{owner}")
        prof = {k: u.get(k) for k in ("login", "name", "type", "bio", "company", "location", "blog", "public_repos", "followers", "created_at")}
        repos = _gh(f"/users/{owner}/repos?per_page=60&sort=updated")
        top = sorted(repos, key=lambda r: -r.get("stargazers_count", 0))[:6]
        prof["other_projects"] = [f"{r['name']}（{r['stargazers_count']} 星，{(r.get('description') or '')[:80]}）" for r in top if r["full_name"] != full]
        p.add(f"作者 {owner}", json.dumps(prof, ensure_ascii=False), u.get("html_url", ""), limit=2000)
    except Exception as e:  # noqa: BLE001
        log.info("owner %s: %s", owner, e)
    return p


# ------------------------------------------------------------------------------------------------ papers
def paper_dossier(c: dict, strip) -> Pack:
    p = Pack(budget=22000)
    p.add(f"{c.get('source')} 摘要", c.get("text") or c.get("summary", ""), c.get("url", ""), limit=3000)
    aid = c.get("url", "").rsplit("/", 1)[-1]
    try:
        html = _get(f"https://arxiv.org/html/{aid}", timeout=30).text
        body = re.sub(r"(?is)<(script|style|math|nav|header|footer)[^>]*>.*?</\1>", " ", html)
        text = strip(body)
        p.add(f"{c.get('source')} 全文", text, f"https://arxiv.org/html/{aid}", limit=16000)
    except Exception as e:  # noqa: BLE001
        log.info("arxiv html %s: %s", aid, e)
    if c.get("authors"):
        p.add("作者", "、".join(c["authors"]) + (f" 等 {c.get('n_authors')} 位" if c.get("n_authors", 0) > len(c["authors"]) else ""),
              c.get("url", ""), limit=400, cite=False)
    return p
