"""Product page ingestion for ad production: structured data, images, logo, colours and a grounded fact table.

Sources, in order of trust: JSON-LD Product (schema.org) → Open Graph / meta tags → visible page text.
Every fact carries the exact source snippet so ad copy can be checked against it. Pages that block plain
HTTP clients are rendered with Playwright; if that fails too, the caller asks the user to upload material.
"""
from __future__ import annotations

import hashlib
import html as htmllib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from ..config import settings
from ..log import get_logger

log = get_logger("product")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 Midea/1.0"
NOT_FOR_SALE = re.compile(r"(demo price|not (a )?selling price|sample product|not available to order|示範價|非售價|不開放訂購|僅供展示)", re.I)


def fetch(url: str) -> tuple[str, str]:
    """Return (html, method). Tries a plain request first, then a headless browser."""
    try:
        r = httpx.get(url, headers={"User-Agent": UA, "Accept-Language": "en,zh-TW;q=0.8"}, timeout=30, follow_redirects=True)
        if r.status_code == 200 and len(r.text) > 500 and not re.search(r"captcha|access denied|cf-chl", r.text[:4000], re.I):
            return r.text, "http"
        log.info("plain fetch of %s gave %s (%d bytes); trying a browser", url, r.status_code, len(r.text))
    except Exception as e:  # noqa: BLE001
        log.info("plain fetch failed (%s); trying a browser", e)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(user_agent=UA)
        pg.goto(url, wait_until="networkidle", timeout=60000)
        out = pg.content()
        b.close()
    return out, "browser"


def _jsonld(doc: str) -> list[dict]:
    out = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', doc, re.S | re.I):
        try:
            d = json.loads(htmllib.unescape(m.group(1)).strip())
        except Exception:  # noqa: BLE001
            continue
        stack = d if isinstance(d, list) else [d]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                if "@graph" in x:
                    stack.extend(x["@graph"])
                out.append(x)
            elif isinstance(x, list):
                stack.extend(x)
    return out


def _meta(doc: str) -> dict:
    meta = {}
    for m in re.finditer(r"<meta\s+([^>]+)>", doc, re.I):
        attrs = dict(re.findall(r'([\w:-]+)\s*=\s*"([^"]*)"', m.group(1)))
        k = attrs.get("property") or attrs.get("name")
        if k and "content" in attrs:
            meta.setdefault(k.lower(), htmllib.unescape(attrs["content"]))
    t = re.search(r"<title[^>]*>(.*?)</title>", doc, re.S | re.I)
    if t:
        meta["title"] = htmllib.unescape(re.sub(r"\s+", " ", t.group(1))).strip()
    return meta


def visible_text(doc: str, limit: int = 6000) -> str:
    doc = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", doc, flags=re.S | re.I)
    doc = re.sub(r"<(br|p|div|li|h\d|tr|section|footer|header)[^>]*>", "\n", doc, flags=re.I)
    txt = htmllib.unescape(re.sub(r"<[^>]+>", " ", doc))
    lines = [re.sub(r"\s+", " ", l).strip() for l in txt.splitlines()]
    return "\n".join(l for l in lines if l)[:limit]


def parse(url: str, doc: str) -> dict:
    """Structured product data (no LLM)."""
    ld = [x for x in _jsonld(doc) if "product" in str(x.get("@type", "")).lower()]
    p = ld[0] if ld else {}
    meta = _meta(doc)
    imgs: list[str] = []
    for v in (p.get("image") or []) if isinstance(p.get("image"), list) else [p.get("image")]:
        if isinstance(v, dict):
            v = v.get("url")
        if v:
            imgs.append(urljoin(url, v))
    for k in ("og:image", "twitter:image"):
        if meta.get(k):
            imgs.append(urljoin(url, meta[k]))
    imgs = list(dict.fromkeys(imgs))
    offers = p.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    brand = p.get("brand")
    brand_name = brand.get("name") if isinstance(brand, dict) else brand
    logo = None
    for m in re.finditer(r'<img[^>]+>', doc, re.I):
        tag = m.group(0)
        if re.search(r'(logo|brand)', tag, re.I):
            s = re.search(r'src="([^"]+)"', tag)
            if s:
                logo = urljoin(url, s.group(1))
                break
    if not logo:
        ic = re.search(r'<link[^>]+rel="[^"]*(apple-touch-icon|icon)[^"]*"[^>]+href="([^"]+)"', doc, re.I)
        logo = urljoin(url, ic.group(2)) if ic else None
    text = visible_text(doc)
    price = offers.get("price") or meta.get("product:price:amount")
    currency = offers.get("priceCurrency") or meta.get("product:price:currency")
    if not price:
        pm = re.search(r"(HK\$|NT\$|US\$|\$|€|£|¥)\s?([0-9][0-9,]*(?:\.\d{1,2})?)", text)
        if pm:
            currency, price = pm.group(1), pm.group(2)
    ctx = text[max(0, text.find(str(price)) - 200): text.find(str(price)) + 200] if price else ""
    not_for_sale = bool(NOT_FOR_SALE.search(ctx) or NOT_FOR_SALE.search(text))
    site = (meta.get("og:site_name") or urlparse(url).hostname or "").strip()
    return {"url": url, "name": p.get("name") or meta.get("og:title") or meta.get("title", ""),
            "description": p.get("description") or meta.get("og:description") or meta.get("description", ""),
            "brand": brand_name or site, "site": site, "sku": p.get("sku", ""), "images": imgs[:8], "logo": logo,
            "price": {"value": str(price) if price else "", "currency": currency or "", "display": bool(price) and not not_for_sale,
                      "reason": "頁面標示為示範價／非售價" if not_for_sale and price else ""},
            "theme_color": meta.get("theme-color", ""), "jsonld": p, "meta": {k: v for k, v in meta.items() if len(v) < 400},
            "text": text}


def download(url: str, dest: Path) -> Path | None:
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=60, follow_redirects=True)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        log.warning("image download failed %s: %s", url, e)
        return None
    ext = {"image/png": ".png", "image/webp": ".webp", "image/svg+xml": ".svg", "image/gif": ".gif"}.get(
        r.headers.get("content-type", "").split(";")[0], Path(urlparse(url).path).suffix or ".jpg")
    dest.parent.mkdir(parents=True, exist_ok=True)
    f = dest.with_suffix(ext.lower())
    f.write_bytes(r.content)
    return f


# ---------------------------------------------------------------- image processing (OpenCV, CPU)
def cutout(src: Path, out: Path) -> Path | None:
    """Remove a plain studio / white background (GrabCut seeded from the border colour) → RGBA PNG."""
    try:
        import cv2
        import numpy as np
        img = cv2.imread(str(src), cv2.IMREAD_COLOR)
        if img is None:
            return None
        h, w = img.shape[:2]
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
        bl = np.median(np.concatenate([lab[:4].reshape(-1, 3), lab[-4:].reshape(-1, 3), lab[:, :4].reshape(-1, 3),
                                       lab[:, -4:].reshape(-1, 3)]), axis=0)
        d_l = np.abs(lab[:, :, 0] - bl[0])
        d_ab = np.linalg.norm(lab[:, :, 1:] - bl[1:], axis=2)
        # soft cast shadows on a studio sweep differ from the backdrop in lightness only, not in colour
        fg = (d_ab > 10) | (d_l > 70)
        maybe = (d_l > 25) & ~fg
        mask = np.full(img.shape[:2], cv2.GC_PR_BGD, np.uint8)
        mask[maybe] = cv2.GC_PR_BGD
        mask[fg] = cv2.GC_PR_FGD
        mask[:3], mask[-3:], mask[:, :3], mask[:, -3:] = cv2.GC_BGD, cv2.GC_BGD, cv2.GC_BGD, cv2.GC_BGD
        bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
        cv2.grabCut(img, mask, None, bgd, fgd, 4, cv2.GC_INIT_WITH_MASK)
        alpha = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
        alpha = cv2.GaussianBlur(cv2.morphologyEx(alpha, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)), (3, 3), 0)
        ys, xs = np.where(alpha > 128)
        if len(xs) < 0.02 * w * h:
            return None
        y0, y1, x0, x1 = max(0, ys.min() - 8), min(h, ys.max() + 9), max(0, xs.min() - 8), min(w, xs.max() + 9)
        rgba = np.dstack([img, alpha])[y0:y1, x0:x1]
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), rgba)
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("cutout failed for %s: %s", src, e)
        return None


_NAMED = {"black": (20, 20, 20), "white": (240, 240, 240), "grey": (128, 128, 128), "navy": (25, 35, 75),
          "blue": (40, 90, 200), "light blue": (140, 180, 230), "red": (190, 40, 40), "burgundy": (110, 25, 40),
          "pink": (230, 150, 170), "orange": (230, 130, 40), "yellow": (230, 200, 60), "olive": (110, 115, 50),
          "green": (50, 140, 70), "teal": (30, 120, 120), "brown": (110, 70, 40), "beige": (215, 195, 160),
          "cream": (240, 230, 205), "purple": (110, 60, 150), "khaki": (170, 150, 100), "charcoal": (55, 58, 64)}
_ZH = {"black": "黑", "white": "白", "grey": "灰", "navy": "深藍", "blue": "藍", "light blue": "淺藍", "red": "紅", "burgundy": "酒紅",
       "pink": "粉紅", "orange": "橘", "yellow": "黃", "olive": "橄欖綠", "green": "綠", "teal": "藍綠", "brown": "棕",
       "beige": "米", "cream": "奶油白", "purple": "紫", "khaki": "卡其", "charcoal": "炭灰"}


def palette(img_path: Path, k: int = 5) -> list[dict]:
    """Dominant colours (k-means on opaque pixels) with an English + Chinese colour name."""
    try:
        import cv2
        import numpy as np
        img = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
        if img is None:
            return []
        if img.shape[2] == 4:
            px = img[img[:, :, 3] > 200][:, :3]
        else:
            px = img.reshape(-1, 3)
        px = px[:: max(1, len(px) // 20000)].astype(np.float32)
        _, labels, centers = cv2.kmeans(px, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0), 3,
                                        cv2.KMEANS_PP_CENTERS)
        counts = np.bincount(labels.ravel(), minlength=k)
        out = []
        for i in np.argsort(-counts):
            b, g, r = (int(x) for x in centers[i])
            name = min(_NAMED, key=lambda n: sum((a - c) ** 2 for a, c in zip(_NAMED[n], (r, g, b))))
            out.append({"hex": f"#{r:02x}{g:02x}{b:02x}", "share": round(float(counts[i]) / len(px), 3), "name": name,
                        "name_zh": _ZH[name]})
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("palette failed: %s", e)
        return []


# ---------------------------------------------------------------- fact table (LLM, grounded)
FACTS_SYSTEM = """You are an advertising compliance researcher. From a product page, extract ONLY facts that are
literally supported by the page. Return JSON:
{"name", "brand", "category", "product_type": "wearable"|"handheld"|"placed",
 "wearable_slot": "top"|"bottom"|"outerwear"|"dress"|"shoes"|"accessory"|"" ,
 "facts": [{"id": "f1", "fact": short statement in English, "fact_zh": 繁體中文, "kind": "claim"|"spec"|"use_case"|"price"|"brand",
            "source": the exact supporting snippet copied from the page (verbatim, ≤ 200 chars)}],
 "audience_hints": [..], "unknown": [important things a shopper would ask that the page does NOT say]}
Never infer materials, sizes, performance or benefits that the page does not state. Do not include prices that the
page marks as demo / sample / not for sale."""


def facts(data: dict, *, observed: list[dict] | None = None) -> dict:
    from .llm import llm
    if settings().mocked("qwen"):
        return _mock_facts(data, observed)
    payload = {k: data.get(k) for k in ("url", "name", "description", "brand", "sku", "price")}
    payload["page_text"] = data.get("text", "")[:5000]
    payload["structured"] = data.get("jsonld")
    r = llm().json("product_facts", FACTS_SYSTEM, json.dumps(payload, ensure_ascii=False))
    r = r if isinstance(r, dict) else {}
    page = (data.get("text", "") + " " + json.dumps(data.get("jsonld", {}), ensure_ascii=False)).lower()
    kept = []
    for i, f in enumerate(r.get("facts") or []):
        if not isinstance(f, dict) or not f.get("fact"):
            continue
        src = str(f.get("source", "")).strip()
        f["id"] = f.get("id") or f"f{i + 1}"
        f["verified"] = bool(src) and _norm(src)[:60] in _norm(page)       # the snippet really is on the page
        if f.get("kind") == "price" and not data.get("price", {}).get("display"):
            continue
        kept.append(f)
    r["facts"] = kept + _observations(observed, start=len(kept))
    for k in ("name", "brand"):
        r[k] = r.get(k) or data.get(k, "")
    if r.get("product_type") not in ("wearable", "handheld", "placed"):
        r["product_type"] = "handheld"
    return r


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()


def _observations(observed: list[dict] | None, start: int = 0) -> list[dict]:
    out = []
    for j, o in enumerate(observed or []):
        out.append({"id": f"o{j + 1}", "fact": o["fact"], "fact_zh": o.get("fact_zh", o["fact"]), "kind": "observed",
                    "source": "由商品圖片觀察", "verified": True})
    return out


def _mock_facts(data: dict, observed: list[dict] | None) -> dict:
    desc = data.get("description") or data.get("name", "")
    fs = [{"id": "f1", "fact": data.get("name", "Product"), "fact_zh": data.get("name", "商品"), "kind": "brand",
           "source": data.get("name", ""), "verified": True}]
    if desc:
        fs.append({"id": "f2", "fact": desc, "fact_zh": desc, "kind": "use_case", "source": desc, "verified": True})
    wearable = bool(re.search(r"shirt|tee|jacket|dress|trouser|pants|scarf|coat|襯衫|外套|褲|裙", data.get("name", "") + desc, re.I))
    return {"name": data.get("name", ""), "brand": data.get("brand", ""), "category": "apparel" if wearable else "goods",
            "product_type": "wearable" if wearable else "handheld", "wearable_slot": "top" if wearable else "",
            "facts": fs + _observations(observed, len(fs)), "audience_hints": [], "unknown": ["material", "sizes"]}


def ingest(url: str, dest: Path) -> dict:
    """Fetch + parse + download images/logo + cut-outs + colours + grounded facts. Paths are relative to dest."""
    dest.mkdir(parents=True, exist_ok=True)
    if settings().mocked("product") or url.startswith("mock:"):
        doc, method = _mock_page(url), "mock"
    else:
        doc, method = fetch(url)
    (dest / "page.html").write_text(doc, encoding="utf-8")
    data = parse(url, doc)
    data["fetched_with"] = method
    images = []
    for i, u in enumerate(data["images"]):
        f = _mock_image(dest / f"img_{i}.png", i) if method == "mock" else download(u, dest / f"img_{i}")
        if not f:
            continue
        cut = cutout(f, dest / f"cut_{i}.png")
        images.append({"url": u, "file": f.name, "cutout": cut.name if cut else None,
                       "sha1": hashlib.sha1(f.read_bytes()).hexdigest()[:12]})
    data["images"] = images
    if data.get("logo") and method != "mock":
        lf = download(data["logo"], dest / "logo")
        data["logo_file"] = lf.name if lf else None
    main = images[0] if images else None
    pal = palette(dest / (main["cutout"] or main["file"])) if main else []
    data["palette"] = pal
    observed = []
    if pal:
        top = pal[0]
        observed.append({"fact": f"Main colour: {top['name']}", "fact_zh": f"主色：{top['name_zh']}色"})
    data["fact_table"] = facts(data, observed=observed)
    data.pop("text", None)
    return data


def _mock_page(url: str) -> str:
    return ("<html><head><title>Travel shirt</title><meta property=\"og:image\" content=\"/shirt.jpg\">"
            "<script type=\"application/ld+json\">{\"@type\":\"Product\",\"name\":\"Travel shirt\",\"description\":"
            "\"An easy-care shirt for city days, travel and busy schedules.\",\"image\":[\"/shirt.jpg\"]}</script></head>"
            "<body><h1>Travel shirt</h1><p>HK$89.00 (demo price, not a selling price)</p></body></html>")


def _mock_image(out: Path, i: int) -> Path:
    from ..media import ff
    out.parent.mkdir(parents=True, exist_ok=True)
    ff.run(["-f", "lavfi", "-i", "color=c=0xf2f2f0:s=600x600:d=1", "-vf",
            "drawbox=x=150:y=120:w=300:h=380:color=0x1f2a4a:t=fill", "-frames:v", "1", out])
    return out
