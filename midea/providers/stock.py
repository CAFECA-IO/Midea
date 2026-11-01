"""Real-footage search across open / free libraries.

Sources: Archive.org (public-domain film & newsreels), NASA Image & Video Library,
Wikimedia Commons, Pexels, Pixabay. Each returns normalised `Candidate`s with licence
and attribution so the edit can print accurate credits.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import httpx

from ..config import settings
from ..log import get_logger
from ..media import ff

log = get_logger("stock")
UA = {"User-Agent": "Midea/0.1 (local video studio; contact: see README)"}


@dataclass
class Candidate:
    id: str
    source: str
    kind: str                       # video | image
    title: str
    url: str                        # direct download URL
    page_url: str = ""
    description: str = ""
    license: str = "unknown"
    author: str = ""
    width: int = 0
    height: int = 0
    duration: float = 0.0
    thumb: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def credit(self) -> str:
        who = f" — {self.author}" if self.author else ""
        return f"{self.title}{who} ({self.source}, {self.license}) {self.page_url}".strip()


def _get(url: str, **kw) -> httpx.Response:
    r = httpx.get(url, headers={**UA, **kw.pop("headers", {})}, timeout=30, follow_redirects=True, **kw)
    r.raise_for_status()
    return r


# ---------------------------------------------------------------- Archive.org
def search_archive_org(query: str, kind: str = "video", limit: int = 8) -> list[Candidate]:
    mt = "movies" if kind == "video" else "image"
    r = _get("https://archive.org/advancedsearch.php", params={
        "q": f"({query}) AND mediatype:({mt})", "fl[]": ["identifier", "title", "description", "licenseurl", "year",
                                                           "creator"], "rows": limit * 2, "output": "json",
        "sort[]": "downloads desc"})
    out: list[Candidate] = []
    for d in r.json().get("response", {}).get("docs", []):
        ident = d["identifier"]
        try:
            files = _get(f"https://archive.org/metadata/{ident}").json().get("files", [])
        except Exception:  # noqa: BLE001
            continue
        exts = (".mp4",) if kind == "video" else (".jpg", ".jpeg", ".png")
        pick = [f for f in files if f.get("name", "").lower().endswith(exts) and f.get("source") != "metadata"]
        if not pick:
            continue
        f = sorted(pick, key=lambda f: int(f.get("size", 0) or 0))[len(pick) // 2]  # mid-size: skip thumbs & huge masters
        lic = d.get("licenseurl") or "public-domain (verify)"
        desc = d.get("description", "")
        out.append(Candidate(id=f"ia:{ident}:{f['name']}", source="archive.org", kind=kind,
                             title=str(d.get("title", ident))[:200], url=f"https://archive.org/download/{ident}/{f['name']}",
                             page_url=f"https://archive.org/details/{ident}",
                             description=(desc if isinstance(desc, str) else " ".join(desc))[:500],
                             license=lic, author=str(d.get("creator", "")),
                             width=int(f.get("width", 0) or 0), height=int(f.get("height", 0) or 0),
                             duration=float(f.get("length", 0) or 0) if str(f.get("length", "")).replace(".", "").isdigit() else 0))
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- NASA
def search_nasa(query: str, kind: str = "video", limit: int = 8) -> list[Candidate]:
    r = _get("https://images-api.nasa.gov/search", params={"q": query, "media_type": kind})
    out: list[Candidate] = []
    for item in r.json().get("collection", {}).get("items", [])[: limit * 2]:
        data = item.get("data", [{}])[0]
        try:
            assets = _get(item["href"]).json()
        except Exception:  # noqa: BLE001
            continue
        if kind == "video":
            pref = [a for a in assets if a.endswith("~orig.mp4")] or [a for a in assets if a.endswith("~large.mp4")] \
                or [a for a in assets if a.endswith(".mp4")]
        else:
            pref = [a for a in assets if "~orig." in a and a.endswith((".jpg", ".png"))] or \
                   [a for a in assets if a.endswith((".jpg", ".png"))]
        if not pref:
            continue
        nid = data.get("nasa_id", "")
        out.append(Candidate(id=f"nasa:{nid}", source="NASA", kind=kind, title=data.get("title", nid),
                             url=pref[0].replace("http://", "https://"),
                             page_url=f"https://images.nasa.gov/details/{nid}",
                             description=data.get("description", "")[:500],
                             license="nasa (public domain, no endorsement)", author=data.get("center", "NASA")))
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- Wikimedia Commons
def search_wikimedia(query: str, kind: str = "video", limit: int = 8) -> list[Candidate]:
    ft = "video" if kind == "video" else "bitmap"
    r = _get("https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"filetype:{ft} {query}", "gsrlimit": limit, "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1920})
    out: list[Candidate] = []
    for p in r.json().get("query", {}).get("pages", {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "unknown")
        out.append(Candidate(id=f"wm:{p['pageid']}", source="Wikimedia Commons", kind=kind,
                             title=p.get("title", "").removeprefix("File:"), url=ii.get("url", ""),
                             page_url=ii.get("descriptionurl", ""),
                             description=meta.get("ImageDescription", {}).get("value", "")[:500],
                             license=lic, author=meta.get("Artist", {}).get("value", "")[:120],
                             width=int(ii.get("width", 0)), height=int(ii.get("height", 0)),
                             duration=float(ii.get("duration", 0) or 0), thumb=ii.get("thumburl", "")))
    return out


# ---------------------------------------------------------------- Pexels
def search_pexels(query: str, kind: str = "video", limit: int = 8) -> list[Candidate]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return []
    hdr = {"Authorization": key}
    out: list[Candidate] = []
    if kind == "video":
        r = _get("https://api.pexels.com/videos/search", params={"query": query, "per_page": limit}, headers=hdr)
        for v in r.json().get("videos", []):
            files = sorted([f for f in v.get("video_files", []) if f.get("height")], key=lambda f: f["height"])
            best = next((f for f in files if f["height"] >= 1080), files[-1] if files else None)
            if not best:
                continue
            out.append(Candidate(id=f"pexels:{v['id']}", source="Pexels", kind="video", title=v.get("url", "").rstrip("/").split("/")[-1],
                                 url=best["link"], page_url=v.get("url", ""), license="pexels",
                                 author=v.get("user", {}).get("name", ""), width=best["width"], height=best["height"],
                                 duration=float(v.get("duration", 0)), thumb=v.get("image", "")))
    else:
        r = _get("https://api.pexels.com/v1/search", params={"query": query, "per_page": limit}, headers=hdr)
        for ph in r.json().get("photos", []):
            out.append(Candidate(id=f"pexels:{ph['id']}", source="Pexels", kind="image", title=ph.get("alt", ""),
                                 url=ph["src"]["original"], page_url=ph.get("url", ""), license="pexels",
                                 author=ph.get("photographer", ""), width=ph["width"], height=ph["height"],
                                 thumb=ph["src"].get("medium", "")))
    return out


# ---------------------------------------------------------------- Pixabay
def search_pixabay(query: str, kind: str = "video", limit: int = 8) -> list[Candidate]:
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return []
    out: list[Candidate] = []
    if kind == "video":
        r = _get("https://pixabay.com/api/videos/", params={"key": key, "q": query, "per_page": max(3, limit)})
        for h in r.json().get("hits", []):
            v = h["videos"].get("large") or h["videos"].get("medium")
            if not v or not v.get("url"):
                continue
            out.append(Candidate(id=f"pixabay:{h['id']}", source="Pixabay", kind="video", title=h.get("tags", ""),
                                 url=v["url"], page_url=h.get("pageURL", ""), license="pixabay", author=h.get("user", ""),
                                 width=v.get("width", 0), height=v.get("height", 0), duration=float(h.get("duration", 0))))
    else:
        r = _get("https://pixabay.com/api/", params={"key": key, "q": query, "per_page": max(3, limit)})
        for h in r.json().get("hits", []):
            out.append(Candidate(id=f"pixabay:{h['id']}", source="Pixabay", kind="image", title=h.get("tags", ""),
                                 url=h.get("largeImageURL", ""), page_url=h.get("pageURL", ""), license="pixabay",
                                 author=h.get("user", ""), width=h.get("imageWidth", 0), height=h.get("imageHeight", 0)))
    return out


SOURCES: dict[str, Callable[..., list[Candidate]]] = {
    "archive_org": search_archive_org, "nasa": search_nasa, "wikimedia": search_wikimedia,
    "pexels": search_pexels, "pixabay": search_pixabay,
}


def search(query: str, kind: str = "video", sources: list[str] | None = None, limit: int = 6) -> list[Candidate]:
    if settings().mode == "mock":
        return [Candidate(id=f"mock:{query}:{i}", source="mock-archive", kind=kind, title=f"{query} #{i+1}",
                          url=f"mock://{query}/{i}", license="public-domain", width=1280, height=720, duration=12)
                for i in range(3)]
    srcs = sources or settings().get("stock.sources", list(SOURCES))
    allow = [a.lower() for a in settings().get("stock.license_allow", [])]
    results: list[Candidate] = []
    for s in srcs:
        try:
            got = SOURCES[s](query, kind, limit)
        except Exception as e:  # noqa: BLE001
            log.warning("%s search failed for %r: %s", s, query, e)
            continue
        results.extend(got)
    min_h = int(settings().get("stock.min_height", 0))
    def ok(c: Candidate) -> bool:
        lic = c.license.lower()
        lic_ok = not allow or any(a.replace("-", "") in lic.replace("-", "").replace(" ", "") for a in allow) \
            or "publicdomain" in lic.replace(" ", "").replace("-", "") or "creativecommons.org" in lic
        return lic_ok and (c.height == 0 or c.height >= min_h)
    return [c for c in results if ok(c)]


def download(c: Candidate, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha1(c.url.encode()).hexdigest()[:12]
    ext = ".mp4" if c.kind == "video" else (Path(c.url.split("?")[0]).suffix or ".jpg")
    out = dest_dir / f"{c.source.replace(' ', '_').replace('.', '_')}_{h}{ext}"
    if out.exists() and out.stat().st_size > 0:
        return out
    if c.url.startswith("mock://"):
        from ..tools.motion_engine import default_font
        label = ff.esc_text(c.title) + f"':fontfile='{ff.esc_filter_path(default_font())}"
        if c.kind == "video":
            ff.run(["-f", "lavfi", "-i", f"testsrc2=s=1280x720:r=24:d={c.duration or 8}", "-vf",
                    f"format=gray,eq=contrast=1.2,noise=alls=25:allf=t,drawtext=text='{label}':fontcolor=white:"
                    "fontsize=28:x=40:y=40", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", out])
        else:
            out = out.with_suffix(".png")
            ff.run(["-f", "lavfi", "-i", "testsrc2=s=1600x900:d=1", "-vf",
                    f"format=gray,drawtext=text='{label}':fontcolor=white:fontsize=36:x=40:y=40", "-frames:v", "1", out])
        return out
    tmp = out.with_suffix(out.suffix + ".part")
    with httpx.stream("GET", c.url, headers=UA, timeout=120, follow_redirects=True) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_bytes(1 << 20):
                fh.write(chunk)
    tmp.rename(out)
    return out
