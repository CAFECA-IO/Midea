"""Built-in motion-graphics engine.

Each template is an HTML page (SVG / Canvas / three.js) that exposes a pure
`window.render(t)` function. Midea drives headless Chromium frame by frame
(deterministic — no wall-clock animation), screenshots each frame and pipes the
PNG stream into FFmpeg. This yields frame-exact kinetic typography, data
graphics, SVG character-rig animation and 3D product turntables.
"""
from __future__ import annotations

import functools
import json
import shutil
import subprocess
from pathlib import Path

from ..config import settings
from ..log import get_logger
from ..media import ff
from .registry import tool

log = get_logger("motion")
TPL_DIR = Path(__file__).resolve().parent.parent / "motion" / "templates"
VENDOR = Path(__file__).resolve().parent.parent / "motion" / "vendor"

PALETTES = {
    # default — matches docs/style-reference.png: slate navy, amber highlight, lavender secondary, coral alert
    "slate": {"bg": "#1a1e29", "bg2": "#262b3a", "fg": "#eef0f6", "accent": "#f5a524", "accent2": "#8b90c8",
              "muted": "#7d849a", "alert": "#e5534b", "ok": "#3fb984", "line": "#343a4d"},
    "midnight": {"bg": "#0b1020", "bg2": "#18213f", "fg": "#f4f6ff", "accent": "#6ea8ff", "accent2": "#ffb86b", "muted": "#8a93b8"},
    "paper": {"bg": "#f6f1e7", "bg2": "#e9dfcc", "fg": "#1d1a16", "accent": "#d0452f", "accent2": "#2f6fd0", "muted": "#7b705f"},
    "neon": {"bg": "#14112a", "bg2": "#241a45", "fg": "#ffffff", "accent": "#00f0ff", "accent2": "#ff2bd6", "muted": "#7c7aa0"},
    "forest": {"bg": "#0f1a14", "bg2": "#1d3326", "fg": "#eef6ee", "accent": "#7bd88f", "accent2": "#f2c14e", "muted": "#88a493"},
}


@functools.lru_cache
def default_font() -> str:
    """Path to a font with CJK coverage (Noto Sans CJK / Source Han), falling back to DejaVu."""
    for q in ("Noto Sans CJK TC:style=Bold", "Noto Sans CJK TC", "Noto Sans TC", "Source Han Sans TC",
              "Noto Sans CJK SC", "PingFang TC", "Microsoft JhengHei", "DejaVu Sans"):
        if shutil.which("fc-match"):
            p = subprocess.run(["fc-match", "-f", "%{file}", q], capture_output=True, text=True).stdout.strip()
            if p and Path(p).exists() and (q.split(":")[0].split()[0].lower() in p.lower() or "dejavu" in q.lower()
                                           or "cjk" in p.lower()):
                return p
    for p in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(p).exists():
            return p
    return "DejaVuSans.ttf"


@functools.lru_cache
def default_font_name() -> str:
    if shutil.which("fc-query"):
        out = subprocess.run(["fc-query", "-f", "%{family[0]}\n", default_font()], capture_output=True, text=True).stdout
        if out.strip():
            return out.strip().splitlines()[0]
    return "Noto Sans CJK TC"


def fonts_dir() -> str:
    return str(Path(default_font()).parent)


def _html(template: str, params: dict, w: int, h: int, palette: str) -> str:
    src = (TPL_DIR / f"{template}.html").read_text(encoding="utf-8")
    lib = (TPL_DIR / "_lib.js").read_text(encoding="utf-8")
    three = VENDOR / "three.module.js"
    three_url = three.as_uri() if three.exists() else "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js"
    addons = VENDOR / "addons"
    addons_url = addons.as_uri() + "/" if addons.exists() else "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
    pal = PALETTES.get(palette, PALETTES["slate"])
    return (src.replace("/*LIB*/", lib)
               .replace("__PARAMS__", json.dumps(params, ensure_ascii=False))
               .replace("__PALETTE__", json.dumps(pal))
               .replace("__W__", str(w)).replace("__H__", str(h))
               .replace("__FONT__", default_font_name())
               .replace("__THREE__", three_url).replace("__ADDONS__", addons_url))


def _num(x, default=0.0):
    try:
        return float(str(x).replace(",", "").rstrip("%"))
    except (TypeError, ValueError):
        return default


def _series(p: dict) -> tuple[list, list]:
    """Accept values/labels, points [[x,y]] / [{x,y}], data [{label,value}], x+y arrays."""
    if isinstance(p.get("values"), list) and p["values"]:
        vals = [_num(v) for v in p["values"]]
        labels = [str(l) for l in (p.get("labels") or [])][:len(vals)]
        return vals, labels + [str(i + 1) for i in range(len(labels), len(vals))]
    for key in ("points", "data", "series"):
        pts = p.get(key)
        if isinstance(pts, list) and pts:
            vals, labels = [], []
            for i, q in enumerate(pts):
                if isinstance(q, (list, tuple)) and len(q) >= 2:
                    labels.append(str(q[0])); vals.append(_num(q[1]))
                elif isinstance(q, dict):
                    labels.append(str(q.get("label", q.get("x", q.get("name", i + 1)))))
                    vals.append(_num(q.get("value", q.get("y", 0))))
                else:
                    labels.append(str(i + 1)); vals.append(_num(q))
            return vals, labels
    if isinstance(p.get("y"), list):
        ys = [_num(v) for v in p["y"]]
        xs = [str(x) for x in (p.get("x") or range(1, len(ys) + 1))]
        return ys, xs
    return [3, 5, 2, 7, 4], ["A", "B", "C", "D", "E"]


def normalize_params(template: str, params: dict) -> dict:
    """Coerce free-form LLM params into the shapes each template expects (never crash a render)."""
    p = dict(params or {})
    for k in ("text", "title", "subtitle", "label", "unit", "author", "cta"):
        if k in p and p[k] is not None and not isinstance(p[k], str):
            p[k] = str(p[k])
    if template in ("bar_chart", "line_chart"):
        p["values"], p["labels"] = _series(p)
        p.setdefault("unit", p.get("y_unit", "") or "")
        p["title"] = p.get("title") or p.get("y_label") or ""
    elif template == "neural_net":
        layers = p.get("layers")
        nodes = p.get("nodes") or p.get("neurons") or p.get("layer_sizes")
        if isinstance(nodes, list) and all(isinstance(_num(n, None), float) for n in nodes):
            layers = nodes
        if isinstance(layers, list):
            sizes = [int(_num(x, 4)) if not isinstance(x, dict) else int(_num(x.get("nodes", x.get("size", 4)), 4)) for x in layers]
            if isinstance(layers[0], str) and not nodes:
                sizes = [3] + [5] * max(0, len(layers) - 2) + [2] if len(layers) > 1 else [4]
                p.setdefault("labels", layers)
        elif isinstance(layers, (int, float)):
            n = max(2, min(7, int(layers)))
            sizes = [4] + [6] * (n - 2) + [2]
        else:
            sizes = [4, 6, 6, 3]
        p["layers"] = [max(1, min(9, s)) for s in sizes][:8]
        labels = p.get("labels")
        if not (isinstance(labels, list) and len(labels) == len(p["layers"])):
            p.pop("labels", None)
    elif template == "timeline":
        ev = p.get("events") or p.get("items") or p.get("milestones") or []
        out = []
        for i, e in enumerate(ev if isinstance(ev, list) else []):
            if isinstance(e, dict):
                out.append({"date": str(e.get("date", e.get("year", e.get("time", i + 1)))),
                            "label": str(e.get("label", e.get("text", e.get("event", e.get("title", "")))))})
            else:
                out.append({"date": str(i + 1), "label": str(e)})
        if out:
            p["events"] = out[:8]
        else:
            p.pop("events", None)
    elif template == "map_route":
        pts = p.get("points") or p.get("stops") or []
        out = []
        for i, q in enumerate(pts if isinstance(pts, list) else []):
            n = max(1, len(pts) - 1)
            if isinstance(q, dict):
                out.append({"x": _num(q.get("x"), 0.12 + 0.76 * i / n), "y": _num(q.get("y"), 0.55 - 0.15 * (i % 2)),
                            "label": str(q.get("label", q.get("name", "")))})
            else:
                out.append({"x": 0.12 + 0.76 * i / n, "y": 0.55 - 0.15 * (i % 2), "label": str(q)})
        for q in out:                            # tolerate 0–100 coordinates
            q["x"] = q["x"] / 100 if q["x"] > 1 else q["x"]
            q["y"] = q["y"] / 100 if q["y"] > 1 else q["y"]
        if out:
            p["points"] = out[:8]
        else:
            p.pop("points", None)
    elif template == "gauge":
        p["value"] = _num(p.get("value", p.get("score", 42)), 42)
        p["max"] = _num(p.get("max", 100), 100) or 100
        if not isinstance(p.get("items"), list):
            p.pop("items", None)
        else:
            p["items"] = [{"label": str(i.get("label", i.get("name", ""))), "value": _num(i.get("value"))}
                          for i in p["items"] if isinstance(i, dict)][:5]
    elif template == "kpi_board":
        items = p.get("items") or p.get("metrics") or []
        if isinstance(items, list) and items:
            p["items"] = [{"label": str(i.get("label", i.get("name", ""))), "value": _num(i.get("value")),
                           "unit": str(i.get("unit", "")), "delta": _num(i.get("delta", i.get("change", 0))),
                           "bar": min(1.0, max(0.0, _num(i.get("bar", 0.5), 0.5)))} for i in items if isinstance(i, dict)][:4]
        else:
            p.pop("items", None)
    elif template == "product_turntable":
        if not isinstance(p.get("features"), list):
            p["features"] = [str(p["features"])] if p.get("features") else []
        p["features"] = [str(f) for f in p["features"]][:5]
        if p.get("model") and not str(p["model"]).lower().endswith((".glb", ".gltf")):
            p.pop("model")
    elif template == "svg_character":
        if p.get("action") not in ("idle", "wave", "walk", "talk", "point", "jump"):
            p.pop("action", None)
    elif template == "kinetic_text":
        if isinstance(p.get("emphasis"), str):
            p["emphasis"] = [p["emphasis"]]
    p.pop("colors", None)                        # keep the house palette consistent across scenes
    return p


def render(template: str, out: str | Path, *, seconds: float, w: int = 1920, h: int = 1080, fps: int = 24,
           params: dict | None = None, palette: str = "slate", audio: str | None = None) -> str:
    from playwright.sync_api import sync_playwright
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    page_path = out.with_suffix(".html")
    params = normalize_params(template, params or {})
    page_path.write_text(_html(template, params, w, h, palette), encoding="utf-8")
    frames = max(1, int(round(seconds * fps)))
    drift = float((params or {}).get("drift", 0.04))      # slow push-in so holds never read as frozen frames
    a_in = ["-i", audio] if audio else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    cmd = [ff.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", str(fps),
           "-c:v", "png", "-i", "-", *a_in, "-map", "0:v", "-map", "1:a", "-t", f"{seconds:.3f}",
           "-c:v", "libx264", "-crf", "16", "-preset", "veryfast", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-ar", "48000", "-ac", "2", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                                          "--ignore-gpu-blocklist", "--allow-file-access-from-files"])
        page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(page_path.as_uri())
        import time as _t
        t0 = _t.time()
        while not page.evaluate("window.__ready === true"):
            if errors:
                browser.close(); proc.kill()
                raise RuntimeError(f"motion template '{template}' failed: {errors[0]}")
            if _t.time() - t0 > 90:
                browser.close(); proc.kill()
                raise TimeoutError(f"motion template '{template}' never became ready")
            page.wait_for_timeout(100)
        page.evaluate("document.fonts.ready")
        for i in range(frames):
            page.evaluate(f"window.render({i / fps:.5f}, {seconds:.3f});window.__bg&&window.__bg({i / fps:.5f});"
                          f"if(!window.__noDrift)document.body.style.transform="
                          f"'scale('+(1+{drift}*{i}/{frames})+')';")
            assert proc.stdin is not None
            proc.stdin.write(page.screenshot(type="png", omit_background=False))
        browser.close()
    assert proc.stdin is not None
    proc.stdin.close()
    err = proc.stderr.read().decode() if proc.stderr else ""
    if proc.wait() != 0:
        raise ff.FFError(err)
    if errors:
        log.warning("template %s JS errors: %s", template, errors[:3])
    page_path.unlink(missing_ok=True)
    return str(out)


def _motion_tool(name: str, summary: str, tags: list[str] | None = None):
    def fn(out: str, seconds: float = 5.0, w: int = 1920, h: int = 1080, fps: int = 24,
           palette: str = "slate", audio: str | None = None, **params) -> str:
        return render(name, out, seconds=seconds, w=w, h=h, fps=fps, params=params, palette=palette, audio=audio)
    fn.__doc__ = summary
    fn.__name__ = name
    tool(f"motion.{name}", "motion", tags=tags or [])(fn)
    return fn


TEMPLATES = {
    "kinetic_text": "Kinetic typography: words/characters animate in with stagger, scale and blur (params: text, title, emphasis).",
    "title_card": "Opening/section title card with animated rule and subtitle (params: title, subtitle).",
    "lower_third": "Lower-third name/caption bar (params: title, text).",
    "quote_card": "Pull quote with attribution (params: text, author).",
    "bar_chart": "Animated bar chart with value counters (params: labels, values, title, unit).",
    "line_chart": "Animated line chart that draws itself (params: labels, values, title, unit).",
    "neural_net": "Neural-network diagram with signal pulses flowing through layers (params: layers, title, labels).",
    "timeline": "Horizontal timeline with dated milestones (params: events=[{date,label}], title).",
    "map_route": "Stylised route/journey map between named points (params: points=[{x,y,label}], title).",
    "svg_character": "Rigged SVG character animation — idle/wave/walk/talk/point clips, lip-flap from audio envelope "
                     "(params: action, color, skin, text, mouth=[0..1 per frame], svg=custom rig).",
    "product_turntable": "3D product turntable in three.js with studio lighting; loads a .glb or builds a procedural "
                         "product (params: model, shape=phone|bottle|box|sphere, color, title, features).",
    "gauge": "KPI ring gauge with counting number and amber arc, optional sub-metrics (params: value, max, label, unit, items=[{label,value}]).",
    "kpi_board": "Dashboard-style KPI board: big numbers, YoY deltas, paired progress bars (params: title, items=[{label,value,unit,delta,bar}]).",
    "end_card": "End card with call-to-action (params: title, text).",
}
for _n, _s in TEMPLATES.items():
    _motion_tool(_n, _s, tags=["motion"])


@tool("motion.render", "motion")
def render_any(template: str, out: str, seconds: float = 5.0, w: int = 1920, h: int = 1080, fps: int = 24,
               palette: str = "slate", params: dict | None = None, audio: str | None = None) -> str:
    """Render any motion template by name."""
    return render(template, out, seconds=seconds, w=w, h=h, fps=fps, params=params or {}, palette=palette, audio=audio)


@tool("motion.audio_envelope", "motion")
def audio_envelope(audio: str, fps: int = 24) -> list[float]:
    """Per-frame 0..1 loudness envelope (drives character lip-flap)."""
    import array
    raw = subprocess.run([ff.FFMPEG, "-v", "error", "-i", audio, "-ac", "1", "-ar", str(fps * 100), "-f", "s16le", "-"],
                         capture_output=True).stdout
    s = array.array("h", raw)
    hop = 100
    env = [max((abs(x) for x in s[i:i + hop]), default=0) / 32768 for i in range(0, len(s), hop)]
    peak = max(env) if env else 1
    return [round(min(1.0, e / (peak or 1) * 1.2), 3) for e in env]


def available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False
