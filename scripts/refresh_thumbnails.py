#!/usr/bin/env python3
"""Re-pick the thumbnails of published projects so tiles never show burned-in subtitles, supers or titles.

Usage (on the server, in app/):  ../venv/bin/python scripts/refresh_thumbnails.py [project-id ...]
Old thumbnails are kept next to the new ones as <name>.old.jpg.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from midea.config import settings  # noqa: E402
from midea.tools import video as vt  # noqa: E402


def windows(pdir: Path, tag: str) -> list:
    if "15s" in tag:
        return []
    f = pdir / "stages" / "copy.json"
    if not f.exists():
        return []
    copy = json.loads(f.read_text(encoding="utf-8"))
    beats = {b.get("beat"): (float(b.get("start", 0)), float(b.get("end", 0))) for b in copy.get("outline") or []}
    return [beats[s["beat"]] for s in copy.get("supers") or [] if s.get("beat") in beats]


def main(ids: list[str]) -> None:
    ws = settings().workspace
    for pj in sorted(ws.glob("*/project.json")):
        d = json.loads(pj.read_text(encoding="utf-8"))
        if ids and d["id"] not in ids or d.get("status") != "done":
            continue
        for it in (d.get("deliverables") or {}).get("items") or []:
            v, th = pj.parent / it["video"], pj.parent / (it.get("thumbnail") or "")
            if not v.exists() or not it.get("thumbnail"):
                continue
            if th.exists() and not th.with_suffix(".old.jpg").exists():
                shutil.copy(th, th.with_suffix(".old.jpg"))
            tag = v.stem.rsplit("_", 2)[-2] + "_" + v.stem.rsplit("_", 1)[-1] if v.stem.count("_") >= 2 else ""
            vt.clean_thumbnail(str(v), str(th), srt=str(pj.parent / it["srt"]) if it.get("srt") else None, extra=windows(pj.parent, tag))
            print("✓", th.relative_to(ws))


if __name__ == "__main__":
    main(sys.argv[1:])
