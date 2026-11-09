"""SVG figures for the daily reports (每日報導).

Every article carries one figure. The writer (Qwen) never draws: it returns a small *spec* (numbers and labels taken
from the sources), and these functions turn the spec into SVG. Colours are design-system tokens (`var(--amber)` …),
so the figure follows the page theme. Each figure is rendered twice — `wide` (desktop, 640 units) and `narrow`
(phones, 340 units) — so text never shrinks below a readable size; the page shows one of them by CSS.

Marks that the page can make interactive carry `class="nf-mark" data-i="<n>" tabindex="0"` plus a <title>.
"""
from __future__ import annotations

import math
from html import escape
from typing import Any

WIDE, NARROW = 640, 340
FONT = "var(--font-sans)"


def _e(s: Any) -> str:
    return escape(str(s if s is not None else ""), quote=True)


def _num(v: Any) -> float | None:
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _wrap(text: str, max_chars: int) -> list[str]:
    """Break a label for SVG (no automatic wrapping there). CJK counts 1, Latin 0.55."""
    out, cur, n = [], "", 0.0
    for ch in str(text):
        w = 1.0 if ord(ch) > 0x2E80 else 0.55
        if n + w > max_chars and cur:
            out.append(cur)
            cur, n = "", 0.0
        cur += ch
        n += w
    if cur:
        out.append(cur)
    return out[:3]


def _svg(w: int, h: int, label: str, body: str) -> str:
    return (f'<svg class="nf" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{_e(label)}" '
            f'style="font-family:{FONT};display:block">{body}</svg>')


def _text(x, y, s, size=14, fill="var(--ink-muted)", anchor="start", weight=400, cls="") -> str:
    c = f' class="{cls}"' if cls else ""
    return (f'<text{c} x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}">{_e(s)}</text>')


# ------------------------------------------------------------------------------------------------ bars
def bars(spec: dict, w: int = WIDE) -> str:
    rows = [r for r in (spec.get("rows") or []) if _num(r.get("value")) is not None][:8]
    if not rows:
        return ""
    narrow = w < 500
    fs = 13 if narrow else 14
    hi = spec.get("highlight", 0)
    neg = any(_num(r["value"]) < 0 for r in rows)
    mx = max(abs(_num(r["value"])) for r in rows) or 1
    def _w(t: str) -> float:
        return sum(1.0 if ord(ch) > 0x2E80 else 0.58 for ch in str(t)) * fs
    label_w = 0 if narrow else int(min(260, max(110, max(_w(r.get("label", "")) for r in rows) + 18)))
    top = 26
    rh = 46 if narrow else 40
    h = top + rh * len(rows) + 6
    body = _text(0, 14, spec.get("title") or "", 12, "var(--ink-subtle)")
    for i, r in enumerate(rows):
        v = abs(_num(r["value"]))
        y = top + i * rh
        on = i == hi
        col = ("var(--rank-down)" if neg else "var(--amber)") if on else "var(--ink-subtle)"
        if narrow:
            body += _text(0, y + 13, r.get("label", ""), fs, "var(--ink)" if on else "var(--ink-muted)", weight=700 if on else 400)
            by, bh, x0, avail = y + 19, 16, 0, w - 78
        else:
            body += _text(label_w - 10, y + rh / 2 + 5, _short(r.get("label", ""), (label_w - 14) / fs), fs,
                          "var(--ink)" if on else "var(--ink-muted)", "end", 700 if on else 400)
            by, bh, x0, avail = y + 9, rh - 18, label_w, w - label_w - 84
        bw = max(3, avail * v / mx)
        disp = r.get("display") or _fmt(r["value"], spec.get("unit"))
        body += (f'<g class="nf-mark{" is-on" if on else ""}" data-i="{i}" tabindex="0"><title>{_e(r.get("label"))}：{_e(disp)}</title>'
                 f'<rect x="{x0}" y="{by:.1f}" width="{bw:.1f}" height="{bh}" rx="3" fill="{col}" fill-opacity="{1 if on else .45}"/>'
                 f'{_text(x0 + bw + 6, by + bh / 2 + 5, disp, fs, "var(--ink)", weight=800)}</g>')
    return _svg(w, int(h), spec.get("alt") or spec.get("title") or "長條圖", body)


def _fmt(v: Any, unit: str | None) -> str:
    f = _num(v)
    if f is None:
        return str(v)
    s = f"{f:,.0f}" if abs(f) >= 100 or f == int(f) else f"{f:,.1f}"
    if f < 0:
        s = "−" + s.lstrip("-")
    return s + (unit or "")


# ------------------------------------------------------------------------------------------------ one number
def number(spec: dict, w: int = WIDE) -> str:
    narrow = w < 500
    h = 150 if narrow else 170
    big = _text(w / 2, 86 if narrow else 96, spec.get("display") or spec.get("value") or "", 58 if narrow else 72,
                "var(--rank-down)" if str(spec.get("display", "")).startswith(("−", "-")) else "var(--amber)", "middle", 900)
    lab = "".join(_text(w / 2, (118 if narrow else 132) + i * 18, ln, 14, "var(--ink-muted)", "middle")
                  for i, ln in enumerate(_wrap(spec.get("label") or "", 22 if narrow else 40)))
    return _svg(w, h, f'{spec.get("display", "")} {spec.get("label", "")}', big + lab)


# ------------------------------------------------------------------------------------------------ flow (圖解)
def flow(spec: dict, w: int = WIDE) -> str:
    nodes = (spec.get("nodes") or [])[:5]
    if not nodes:
        return ""
    hi = spec.get("highlight", -1)
    branch = spec.get("branch")
    narrow = w < 500
    body = ""
    if narrow:
        bw, bh, gap = w - 40, 58, 22
        y = 0
        for i, n in enumerate(nodes):
            on = i == hi
            body += (f'<g class="nf-mark{" is-on" if on else ""}" data-i="{i}" tabindex="0"><title>{_e(n.get("label"))}</title>'
                     f'<rect x="20" y="{y}" width="{bw}" height="{bh}" rx="10" fill="{"var(--amber-soft)" if on else "var(--surface-raised)"}" '
                     f'stroke="{"var(--amber)" if on else "var(--line)"}"/>'
                     f'{_text(w / 2, y + 25, n.get("label", ""), 15, "var(--amber-text)" if on else "var(--ink)", "middle", 800)}'
                     f'{_text(w / 2, y + 44, _short(n.get("sub", ""), (bw - 16) / 12), 12, "var(--ink-subtle)", "middle")}</g>')
            if i < len(nodes) - 1:
                body += (f'<path d="M{w / 2} {y + bh + 3}V{y + bh + gap - 5}" stroke="var(--amber)" stroke-width="2"/>'
                         f'<path d="M{w / 2 - 5} {y + bh + gap - 10}l5 6 5-6" stroke="var(--amber)" stroke-width="2" fill="none"/>')
            y += bh + gap
        if branch:
            body += (f'<rect x="20" y="{y}" width="{bw}" height="44" rx="10" fill="var(--surface)" stroke="var(--rank-up)" stroke-dasharray="4 4"/>'
                     f'{_text(w / 2, y + 27, branch.get("label", ""), 14, "var(--rank-up)", "middle", 800)}')
            y += 44
        return _svg(w, int(y + 4), spec.get("alt") or "流程圖", body)
    n = len(nodes)
    gap = 34
    bw = (w - gap * (n - 1)) / n
    bh, y = 76, 8
    for i, nd in enumerate(nodes):
        x = i * (bw + gap)
        on = i == hi
        lines = _wrap(nd.get("label", ""), int(bw / 15))
        body += (f'<g class="nf-mark{" is-on" if on else ""}" data-i="{i}" tabindex="0"><title>{_e(nd.get("label"))}</title>'
                 f'<rect x="{x:.1f}" y="{y}" width="{bw:.1f}" height="{bh}" rx="12" fill="{"var(--amber-soft)" if on else "var(--surface-raised)"}" '
                 f'stroke="{"var(--amber)" if on else "var(--line)"}"/>')
        for j, ln in enumerate(lines):
            body += _text(x + bw / 2, y + 30 + j * 18 - (len(lines) - 1) * 6, ln, 15, "var(--amber-text)" if on else "var(--ink)", "middle", 800)
        body += _text(x + bw / 2, y + bh - 12, _short(nd.get("sub", ""), (bw - 12) / 12), 12, "var(--ink-subtle)", "middle") + "</g>"
        if i < n - 1:
            ax = x + bw
            body += (f'<path d="M{ax + 4:.1f} {y + bh / 2}H{ax + gap - 6:.1f}" stroke="var(--amber)" stroke-width="2"/>'
                     f'<path d="M{ax + gap - 11:.1f} {y + bh / 2 - 5}l6 5-6 5" stroke="var(--amber)" stroke-width="2" fill="none"/>')
    h = y + bh + 8
    if branch:
        bi = int(branch.get("from", max(0, hi)))
        bx = bi * (bw + gap) + bw / 2
        body += (f'<path d="M{bx:.1f} {y + bh + 2}V{y + bh + 26}" stroke="var(--rank-up)" stroke-width="2" stroke-dasharray="4 4"/>'
                 f'<rect x="{bx - bw / 2:.1f}" y="{y + bh + 28}" width="{bw:.1f}" height="44" rx="10" fill="var(--surface)" stroke="var(--rank-up)"/>'
                 f'{_text(bx, y + bh + 55, branch.get("label", ""), 14, "var(--rank-up)", "middle", 800)}')
        h = y + bh + 80
    return _svg(w, int(h), spec.get("alt") or "流程圖", body)


# ------------------------------------------------------------------------------------------------ timeline (時間軸)
def timeline(spec: dict, w: int = WIDE) -> str:
    ev = (spec.get("events") or [])[:7]
    if not ev:
        return ""
    hi = spec.get("highlight", len(ev) - 1)
    narrow = w < 500
    body = ""
    if narrow:
        y = 10
        rows = []
        for i, e in enumerate(ev):
            lines = _wrap(e.get("text", ""), 18)
            rows.append((i, e, lines, y))
            y += 30 + 19 * len(lines)
        body += f'<line x1="10" y1="12" x2="10" y2="{y - 24}" stroke="var(--line)" stroke-width="2"/>'
        for i, e, lines, y0 in rows:
            on = i == hi
            body += (f'<g class="nf-mark{" is-on" if on else ""}" data-i="{i}" tabindex="0"><title>{_e(e.get("date"))}</title>'
                     f'<circle cx="10" cy="{y0 + 6}" r="7" fill="{"var(--amber)" if on else "var(--surface-raised)"}" stroke="var(--ground)" stroke-width="3"/>'
                     f'{_text(28, y0 + 11, e.get("date", ""), 13, "var(--amber-text)" if on else "var(--ink-subtle)", weight=800)}')
            for j, ln in enumerate(lines):
                body += _text(28, y0 + 31 + j * 19, ln, 14, "var(--ink)")
            body += "</g>"
        return _svg(w, int(y), spec.get("alt") or "時間軸", body)
    n = len(ev)
    step = (w - 40) / max(1, n - 1) if n > 1 else 0
    body += f'<line x1="20" y1="40" x2="{w - 20}" y2="40" stroke="var(--line)" stroke-width="2"/>'
    maxl = 1
    for i, e in enumerate(ev):
        x = 20 + i * step if n > 1 else w / 2
        on = i == hi
        anchor = "start" if i == 0 else ("end" if i == n - 1 and n > 1 else "middle")
        lines = _wrap(e.get("text", ""), max(6, int(step / 15)) if n > 1 else 30)
        maxl = max(maxl, len(lines))
        body += (f'<g class="nf-mark{" is-on" if on else ""}" data-i="{i}" tabindex="0"><title>{_e(e.get("date"))}：{_e(e.get("text"))}</title>'
                 f'{_text(x, 22, e.get("date", ""), 13, "var(--amber-text)" if on else "var(--ink-subtle)", anchor, 800)}'
                 f'<circle cx="{x:.1f}" cy="40" r="8" fill="{"var(--amber)" if on else "var(--surface-raised)"}" stroke="var(--ground)" stroke-width="3"/>')
        for j, ln in enumerate(lines):
            body += _text(x, 70 + j * 19, ln, 14, "var(--ink)" if on else "var(--ink-muted)", anchor)
        body += "</g>"
    return _svg(w, int(76 + maxl * 19), spec.get("alt") or "時間軸", body)


# ------------------------------------------------------------------------------------------------ compare (對照)
def compare(spec: dict, w: int = WIDE) -> str:
    sides = (spec.get("sides") or [])[:2]
    if len(sides) < 2:
        return ""
    narrow = w < 500
    vals = [_num(s.get("value")) for s in sides]
    mx = max([abs(v) for v in vals if v is not None] or [1]) or 1
    colw = (w - 16) / 2
    body = ""
    h = 0
    for i, s in enumerate(sides):
        x = i * (colw + 16)
        lines = _wrap(s.get("name", ""), int(colw / 16))
        y = 22
        for ln in lines:
            body += _text(x, y, ln, 16 if not narrow else 14, "var(--ink)", weight=800)
            y += 20
        v = vals[i]
        if v is not None:
            bh = 90 if not narrow else 70
            hh = max(4, bh * abs(v) / mx)
            body += (f'<g class="nf-mark" data-i="{i}" tabindex="0"><title>{_e(s.get("name"))}：{_e(s.get("display") or v)}</title>'
                     f'<rect x="{x}" y="{y + 10 + bh - hh:.1f}" width="{colw * (0.3 if narrow else 0.5):.1f}" height="{hh:.1f}" rx="4" fill="{"var(--amber)" if i == 0 else "var(--ink-subtle)"}" fill-opacity="{1 if i == 0 else .45}"/>'
                     f'{_text(x + colw * (0.3 if narrow else 0.5) + 8, y + 10 + bh, _short(s.get("display") or _fmt(v, spec.get("unit")), (colw * 0.7 - 12) / 15), 18 if not narrow else 15, "var(--ink)", weight=900)}</g>')
            y += bh + 26
            if spec.get("value_label"):
                body += _text(x, y, spec["value_label"], 12, "var(--ink-subtle)")
                y += 18
        h = max(h, y)
    body += f'<line x1="{colw + 8}" y1="4" x2="{colw + 8}" y2="{h}" stroke="var(--line)"/>'
    return _svg(w, int(h + 6), spec.get("alt") or "對照圖", body)


# ------------------------------------------------------------------------------------------------ categories (論文、分類)
def categories(spec: dict, w: int = WIDE) -> str:
    items = (spec.get("items") or [])[:6]
    if not items:
        return ""
    hi = spec.get("highlight", -1)
    narrow = w < 500
    center = spec.get("center") or ""
    body = ""
    if narrow or len(items) > 4:
        cols = 2
        rows = math.ceil(len(items) / cols)
        cw, ch, gap = (w - 12) / 2, 64, 12
        top = 70
        body += (f'<rect x="{w / 2 - 110}" y="6" width="220" height="44" rx="22" fill="var(--surface)" stroke="var(--amber)" stroke-width="2"/>'
                 f'{_text(w / 2, 34, center, 15, "var(--ink)", "middle", 800)}')
        for i, it in enumerate(items):
            r, c = divmod(i, cols)
            x, y = c * (cw + gap), top + r * (ch + gap)
            on = i == hi
            body += (f'<g class="nf-mark{" is-on" if on else ""}" data-i="{i}" tabindex="0"><title>{_e(it.get("label"))}</title>'
                     f'<rect x="{x:.1f}" y="{y}" width="{cw:.1f}" height="{ch}" rx="10" fill="{"var(--amber-soft)" if on else "var(--surface-raised)"}" stroke="{"var(--amber)" if on else "var(--line)"}"/>'
                     f'{_text(x + cw / 2, y + 28, it.get("label", ""), 14, "var(--amber-text)" if on else "var(--ink)", "middle", 800)}'
                     f'{_text(x + cw / 2, y + 47, it.get("sub", ""), 11, "var(--ink-subtle)", "middle")}</g>')
        return _svg(w, int(top + rows * (ch + gap)), spec.get("alt") or center, body)
    h = 280
    bw, bh = w * 0.34, 74
    pos = [(0, 0), (w - bw, 0), (0, h - bh), (w - bw, h - bh)]
    cx, cy, r = w / 2, h / 2, 58
    for i, it in enumerate(items):
        x, y = pos[i]
        on = i == hi
        body += f'<line x1="{x + bw / 2:.1f}" y1="{y + bh / 2}" x2="{cx}" y2="{cy}" stroke="{"var(--amber)" if on else "var(--line)"}" stroke-width="{2 if on else 1.5}"/>'
    for i, it in enumerate(items):
        x, y = pos[i]
        on = i == hi
        body += (f'<g class="nf-mark{" is-on" if on else ""}" data-i="{i}" tabindex="0"><title>{_e(it.get("label"))}</title>'
                 f'<rect x="{x:.1f}" y="{y}" width="{bw:.1f}" height="{bh}" rx="12" fill="{"var(--amber-soft)" if on else "var(--surface-raised)"}" stroke="{"var(--amber)" if on else "var(--line)"}"/>'
                 f'{_text(x + bw / 2, y + 33, it.get("label", ""), 16, "var(--amber-text)" if on else "var(--ink)", "middle", 800)}'
                 f'{_text(x + bw / 2, y + 54, it.get("sub", ""), 12, "var(--ink-subtle)", "middle")}</g>')
    lines = _wrap(center, 6)
    body += f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="var(--surface)" stroke="var(--amber)" stroke-width="2"/>'
    for j, ln in enumerate(lines):
        body += _text(cx, cy + 5 + (j - (len(lines) - 1) / 2) * 19, ln, 15, "var(--ink)", "middle", 800)
    return _svg(w, h, spec.get("alt") or center, body)


# ------------------------------------------------------------------------------------------------ ranking (排行榜)
def ranking(spec: dict, w: int = WIDE) -> str:
    items = [x for x in (spec.get("items") or []) if _num(x.get("value")) is not None][:10]
    if not items:
        return ""
    mx = max(_num(x["value"]) for x in items) or 1
    narrow = w < 500
    rh = 50 if narrow else 44
    body = _text(0, 14, spec.get("title") or "", 12, "var(--ink-subtle)")
    for i, it in enumerate(items):
        y = 26 + i * rh
        on = i == spec.get("highlight", 0)
        v = _num(it["value"])
        avail = w - 130
        bw = max(3, avail * v / mx)
        disp = it.get("display") or _fmt(v, spec.get("unit"))
        body += (f'<g class="nf-mark{" is-on" if on else ""}" data-i="{i}" tabindex="0"><title>{_e(it.get("name"))}：{_e(disp)}</title>'
                 f'{_text(0, y + 22, str(i + 1), 20, "var(--amber)" if on else "var(--ink-subtle)", weight=900)}'
                 f'{_text(30, y + 12, it.get("name", ""), 13, "var(--ink)" if on else "var(--ink-muted)", weight=700 if on else 400)}'
                 f'<rect x="30" y="{y + 19}" width="{bw:.1f}" height="{rh - 30}" rx="3" fill="{"var(--amber)" if on else "var(--ink-subtle)"}" fill-opacity="{1 if on else .45}"/>'
                 f'{_text(36 + bw, y + 19 + (rh - 30) / 2 + 5, disp, 13, "var(--ink)", weight=800)}</g>')
    return _svg(w, int(26 + rh * len(items)), spec.get("alt") or spec.get("title") or "排行榜", body)


RENDER = {"bars": bars, "number": number, "flow": flow, "timeline": timeline, "compare": compare,
          "categories": categories, "ranking": ranking}


def render(spec: dict | None) -> dict:
    """{"wide": svg, "narrow": svg} — empty strings when the spec cannot be drawn."""
    if not spec or spec.get("type") not in RENDER:
        return {"wide": "", "narrow": ""}
    fn = RENDER[spec["type"]]
    try:
        return {"wide": fn(spec, WIDE), "narrow": fn(spec, NARROW)}
    except Exception:  # noqa: BLE001 — a bad spec must never break the page
        return {"wide": "", "narrow": ""}


def _short(t: Any, n: int) -> str:
    t = str(t or "")
    out, w = "", 0.0
    for ch in t:
        w += 1.0 if ord(ch) > 0x2E80 else 0.55
        if w > n:
            return out + "…"
        out += ch
    return out


def mini(spec: dict | None) -> str:
    """Thumbnail for a 1×1 home tile: a 300×130 drawing made for that size (no scaling of the full figure)."""
    if not spec or spec.get("type") not in RENDER:
        return ""
    W, H = 300, 130
    t = spec["type"]
    body = ""
    try:
        if t in ("bars", "ranking"):
            rows = spec.get("rows") if t == "bars" else [{"label": x.get("name"), "value": x.get("value"), "display": x.get("display")} for x in spec.get("items") or []]
            rows = [r for r in (rows or []) if _num(r.get("value")) is not None][:3]
            if not rows:
                return ""
            mx = max(abs(_num(r["value"])) for r in rows) or 1
            neg = any(_num(r["value"]) < 0 for r in rows)
            hi = min(int(spec.get("highlight") or 0), len(rows) - 1)
            for i, r in enumerate(rows):
                y = 4 + i * 42
                bw = max(3, (W - 86) * abs(_num(r["value"])) / mx)
                col = ("var(--rank-down)" if neg else "var(--amber)") if i == hi else "var(--ink-subtle)"
                body += (_text(0, y + 13, _short(r.get("label"), 22), 12, "var(--ink-muted)") +
                         f'<rect x="0" y="{y + 19}" width="{bw:.1f}" height="14" rx="3" fill="{col}" fill-opacity="{1 if i == hi else .45}"/>' +
                         _text(bw + 6, y + 31, _short(r.get("display") or _fmt(r["value"], spec.get("unit")), 9), 13, "var(--ink)", weight=800))
        elif t == "number":
            body = _text(W / 2, 74, spec.get("display") or "", 52, "var(--amber)", "middle", 900) + _text(W / 2, 104, _short(spec.get("label"), 20), 12, "var(--ink-muted)", "middle")
        elif t == "flow":
            nodes = (spec.get("nodes") or [])[:3]
            n = len(nodes)
            gap = 18
            bw = (W - gap * (n - 1)) / max(1, n)
            hi = spec.get("highlight", -1)
            for i, nd in enumerate(nodes):
                x = i * (bw + gap)
                on = i == hi
                body += (f'<rect x="{x:.1f}" y="38" width="{bw:.1f}" height="54" rx="10" fill="{"var(--amber-soft)" if on else "var(--surface-raised)"}" stroke="{"var(--amber)" if on else "var(--line)"}"/>'
                         + _text(x + bw / 2, 70, _short(nd.get("label"), bw / 13), 12, "var(--amber-text)" if on else "var(--ink)", "middle", 800))
                if i < n - 1:
                    body += f'<path d="M{x + bw + 3:.1f} 65H{x + bw + gap - 4:.1f}" stroke="var(--amber)" stroke-width="2"/>'
        elif t == "categories":
            items = (spec.get("items") or [])[:4]
            body += (f'<rect x="{W / 2 - 70}" y="0" width="140" height="30" rx="15" fill="var(--surface)" stroke="var(--amber)" stroke-width="1.5"/>'
                     + _text(W / 2, 20, _short(spec.get("center"), 10), 12, "var(--ink)", "middle", 800))
            for i, it in enumerate(items):
                r, c = divmod(i, 2)
                x, y = c * 154, 40 + r * 46
                on = i == spec.get("highlight", -1)
                body += (f'<rect x="{x}" y="{y}" width="146" height="38" rx="8" fill="{"var(--amber-soft)" if on else "var(--surface-raised)"}" stroke="{"var(--amber)" if on else "var(--line)"}"/>'
                         + _text(x + 73, y + 24, _short(it.get("label"), 10), 12, "var(--amber-text)" if on else "var(--ink)", "middle", 700))
        elif t == "timeline":
            ev = (spec.get("events") or [])[:4]
            n = len(ev)
            step = (W - 40) / max(1, n - 1)
            hi = spec.get("highlight", n - 1)
            body += f'<line x1="20" y1="50" x2="{W - 20}" y2="50" stroke="var(--line)" stroke-width="2"/>'
            for i, e in enumerate(ev):
                x = 20 + i * step
                on = i == hi
                anchor = "start" if i == 0 else ("end" if i == n - 1 else "middle")
                body += (_text(x, 32, _short(e.get("date"), 6), 11, "var(--amber-text)" if on else "var(--ink-subtle)", anchor, 800)
                         + f'<circle cx="{x:.1f}" cy="50" r="7" fill="{"var(--amber)" if on else "var(--surface-raised)"}" stroke="var(--surface)" stroke-width="3"/>'
                         + _text(x, 78, _short(e.get("text"), 6), 12, "var(--ink)" if on else "var(--ink-muted)", anchor))
        elif t == "compare":
            sides = (spec.get("sides") or [])[:2]
            vals = [abs(_num(x.get("value")) or 0) for x in sides]
            mx = max(vals or [1]) or 1
            for i, sd in enumerate(sides):
                x = i * 154
                hh = max(4, 70 * vals[i] / mx)
                body += (_text(x, 14, _short(sd.get("name"), 12), 12, "var(--ink)", weight=800)
                         + f'<rect x="{x}" y="{104 - hh:.1f}" width="56" height="{hh:.1f}" rx="4" fill="{"var(--amber)" if i == 0 else "var(--ink-subtle)"}" fill-opacity="{1 if i == 0 else .45}"/>'
                         + _text(x + 64, 102, _short(sd.get("display") or _fmt(sd.get("value"), spec.get("unit")), 9), 14, "var(--ink)", weight=900))
        else:
            return ""
    except Exception:  # noqa: BLE001
        return ""
    return _svg(W, H, spec.get("alt") or spec.get("title") or "", body)
