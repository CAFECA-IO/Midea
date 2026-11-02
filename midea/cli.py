"""Midea command line.

  midea make "製作一支 60 秒解釋神經網路的動畫"          # 互動核准（在看板或 CLI）
  midea make "二戰後的台北" --real-only --duration 90   # 只用真實素材
  midea make "咖啡沖煮技巧" --ref https://youtube.com/shorts/xxxx
  midea serve                                          # 開啟分鏡看板 http://127.0.0.1:7788
  midea approve <project> scene_plan [--reject --note "..."]
  midea services status | up qwen | down h3
  midea tools | pipelines | doctor | qa video.mp4
  midea actors new "32 歲台灣女記者，俐落短髮" [--handle mei]   # AI 補完設定 + 定妝照 + 聲音
  midea actors list | show @mei | portraits @mei [--reseed] | voice @mei
  midea make "@mei 走訪台南老街的一天" --pipeline cinematic   # @ 指定演員演出
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys


def _brief(a: argparse.Namespace) -> dict:
    b = {"prompt": a.prompt, "pipeline": a.pipeline, "duration_s": a.duration, "language": a.language,
         "real_only": a.real_only, "reference_url": a.ref, "user_media": a.media or [], "voice": a.voice,
         "music": not a.no_music, "subtitles": not a.no_subs}
    if a.aspect:
        b["aspect"], b["aspect_locked"] = a.aspect, True
    return b


def cmd_make(a: argparse.Namespace) -> None:
    from .pipelines import Runner, route
    from .project import Project
    brief = _brief(a)
    pipe = a.pipeline if a.pipeline != "auto" else route(brief)
    p = Project.create(brief, pipe)
    print(f"專案 {p.id}  pipeline={pipe}\n資料夾 {p.dir}")
    if not a.yes:
        print("關卡會暫停等待核准：另開終端執行 `midea serve` 用看板核准，或 `midea approve <project> <gate>`")
    Runner(p, auto_approve=a.yes).run()
    d = p.load()
    print(json.dumps({"status": d["status"], "deliverables": d.get("deliverables"), "cost": d["cost"]["actual"]},
                     ensure_ascii=False, indent=1))


def cmd_serve(a: argparse.Namespace) -> None:
    import uvicorn
    from .config import settings
    from .web.app import app
    uvicorn.run(app, host=a.host or settings().get("server.host", "127.0.0.1"),
                port=a.port or int(settings().get("server.port", 7788)), log_level="warning")


def cmd_approve(a: argparse.Namespace) -> None:
    from .project import Project
    Project(a.project).decide_gate(a.gate, not a.reject, a.note or "", by="cli")
    print("rejected" if a.reject else "approved", a.gate)


def cmd_services(a: argparse.Namespace) -> None:
    from .gpu import scheduler
    s = scheduler()
    if a.action == "status":
        print(json.dumps(s.status(), ensure_ascii=False, indent=1))
    elif a.action == "up":
        with s.lease(a.name):
            print(f"{a.name} is up (Ctrl+C to stop)")
            try:
                while True:
                    import time; time.sleep(3600)
            except KeyboardInterrupt:
                pass
        s.services[a.name].stop()
    elif a.action == "down":
        s.services[a.name].stop()


def cmd_tools(a: argparse.Namespace) -> None:
    from .tools import catalog
    cat = catalog()
    for t in cat:
        if not a.category or t["category"] == a.category:
            print(f"{t['name']:<28} {t['category']:<10} {t['summary']}")
    print(f"\n{len(cat)} tools")


def cmd_pipelines(a: argparse.Namespace) -> None:
    from .pipelines import load_defs
    for k, d in load_defs().items():
        print(f"{k:<22} {d['title']:<14} gates={','.join(d['gates'])}\n{'':<22} {d['description']}")


def cmd_qa(a: argparse.Namespace) -> None:
    from pathlib import Path
    from . import qa
    from .media import ff
    v = ff.video_stream(a.file) or {}
    n, d = (v.get("avg_frame_rate") or "24/1").split("/")
    rep = qa.run_all(a.file, promise={"duration_s": a.duration, "aspect": a.aspect}, w=int(v.get("width", 0)),
                     h=int(v.get("height", 0)), fps=float(n) / float(d), workdir=Path(a.file).with_suffix(".qa"))
    for r in rep["results"]:
        print(f"[{r['status'].upper():4}] {r['check']:<10} {r['message']}")
    sys.exit(1 if rep["status"] == "fail" else 0)


def cmd_doctor(a: argparse.Namespace) -> None:
    from .config import settings
    from .gpu import nvidia_smi, scheduler
    from .tools.motion_engine import default_font
    ok = lambda b: "OK " if b else "-- "  # noqa: E731
    ffm = shutil.which("ffmpeg")
    filt = subprocess.run([ffm, "-hide_banner", "-filters"], capture_output=True, text=True).stdout if ffm else ""
    print(ok(ffm), "ffmpeg", ffm or "missing")
    for f in ("subtitles", "drawtext", "xfade", "loudnorm", "zoompan", "freezedetect", "sidechaincompress"):
        print(ok(f" {f} " in filt), f"  filter {f}")
    try:
        import playwright  # noqa: F401
        print(ok(True), "playwright (motion engine)  — run `playwright install chromium` once")
    except ImportError:
        print(ok(False), "playwright missing: pip install playwright && playwright install chromium")
    print(ok(shutil.which("yt-dlp")), "yt-dlp (reference links)")
    print(ok("CJK" in default_font() or "Noto" in default_font()), "font", default_font())
    g = nvidia_smi()
    print(ok(bool(g)), "GPU", g[0]["name"] + f" {g[0]['total_mb']/1024:.0f} GB" if g else "nvidia-smi not found")
    print("mode:", settings().mode, "| budget VRAM:", scheduler().budget_gb, "GB")
    for n, sv in scheduler().services.items():
        print(ok(sv.healthy(1.0)), f"service {n:<8} {sv.cfg.get('model')} ({sv.vram} GB{', exclusive' if sv.exclusive else ''})")
    for k in ("PEXELS_API_KEY", "PIXABAY_API_KEY"):
        print(ok(bool(os.environ.get(k))), k, "(optional)")


def cmd_actors(a: argparse.Namespace) -> None:
    from . import actors as AC
    if a.action == "list":
        for x in AC.list_all():
            films = AC.filmography(x.id)
            print(f"@{x.handle:<16} {x.name:<8} {x.age:>3} {x.gender:<9} portraits={len(x.portraits)} "
                  f"voice={'yes' if x.voice.sample else 'no'} films={len(films)}  [{x.id}]")
        return
    if a.action == "new":
        if not a.ref:
            sys.exit("usage: midea actors new \"一句話描述\"")
        d = AC.draft(a.ref, a.language)
        if a.handle:
            d["handle"] = a.handle
        x = AC.create(d)
        print(f"建立 @{x.handle}（{x.name}）[{x.id}]，生成定妝照與聲音中…")
        if not a.no_gen:
            AC.generate_portraits(x.id)
            AC.generate_voice(x.id)
        print(json.dumps(AC.summary(AC.load(x.id)), ensure_ascii=False, indent=1))
        return
    x = AC.find(a.ref or "")
    if not x:
        sys.exit(f"找不到演員 {a.ref}")
    if a.action == "portraits":
        AC.generate_portraits(x.id, reseed=a.reseed)
    elif a.action == "voice":
        AC.generate_voice(x.id)
    x = AC.load(x.id)
    out = x.model_dump(exclude={"jobs"})
    out["films"] = [{k: f[k] for k in ("project", "title", "status", "role", "lines")} for f in AC.filmography(x.id)]
    out["folder"] = str(AC.adir(x.id))
    print(json.dumps(out, ensure_ascii=False, indent=1))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="midea", description="Local-GPU AI video studio")
    ap.add_argument("--mock", action="store_true", help="run without GPU models (placeholders)")
    ap.add_argument("--config")
    sp = ap.add_subparsers(dest="cmd", required=True)
    m = sp.add_parser("make", help="text → finished video")
    m.add_argument("prompt")
    m.add_argument("--pipeline", default="auto")
    m.add_argument("--duration", type=float, default=60)
    m.add_argument("--aspect")
    m.add_argument("--language", default="zh-TW")
    m.add_argument("--real-only", action="store_true")
    m.add_argument("--ref", help="YouTube Shorts / Reels / TikTok reference link")
    m.add_argument("--media", nargs="*", help="your own footage (clip-factory / localization-dub / product refs)")
    m.add_argument("--voice", help="VoxCPM2 voice description, or a reference .wav to clone")
    m.add_argument("--no-music", action="store_true")
    m.add_argument("--no-subs", action="store_true")
    m.add_argument("-y", "--yes", action="store_true", help="auto-approve all gates")
    m.set_defaults(fn=cmd_make)
    s = sp.add_parser("serve"); s.add_argument("--host"); s.add_argument("--port", type=int); s.set_defaults(fn=cmd_serve)
    g = sp.add_parser("approve"); g.add_argument("project"); g.add_argument("gate")
    g.add_argument("--reject", action="store_true"); g.add_argument("--note"); g.set_defaults(fn=cmd_approve)
    v = sp.add_parser("services"); v.add_argument("action", choices=["status", "up", "down"]); v.add_argument("name", nargs="?")
    v.set_defaults(fn=cmd_services)
    t = sp.add_parser("tools"); t.add_argument("--category"); t.set_defaults(fn=cmd_tools)
    sp.add_parser("pipelines").set_defaults(fn=cmd_pipelines)
    q = sp.add_parser("qa"); q.add_argument("file"); q.add_argument("--duration", type=float); q.add_argument("--aspect")
    q.set_defaults(fn=cmd_qa)
    sp.add_parser("doctor").set_defaults(fn=cmd_doctor)
    ac = sp.add_parser("actors", help="virtual actors (@handle)")
    ac.add_argument("action", choices=["list", "new", "show", "portraits", "voice"])
    ac.add_argument("ref", nargs="?", help="描述（new）或 @handle")
    ac.add_argument("--handle"); ac.add_argument("--language", default="zh-TW")
    ac.add_argument("--reseed", action="store_true"); ac.add_argument("--no-gen", action="store_true")
    ac.set_defaults(fn=cmd_actors)
    a = ap.parse_args(argv)
    if a.mock:
        os.environ["MIDEA_MODE"] = "mock"
    if a.config:
        os.environ["MIDEA_CONFIG"] = a.config
    a.fn(a)


if __name__ == "__main__":
    main()
