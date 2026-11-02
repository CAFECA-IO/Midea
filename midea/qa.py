"""Self-review: nothing is presented as finished until it passes these checks.

Checks (each returns pass / warn / fail with evidence):
 1. container   – ffprobe: H.264/AAC, yuv420p, 48 kHz stereo, expected WxH and fps, A/V duration drift
 2. delivery    – duration within ±5 % of the promise, aspect matches, subtitles present when promised
 3. frames      – frames at 4 positions: not black, not blown out, not blank/flat (broken overlay)
 4. black       – no black spans beyond the allowed ratio (excluding the fade-in/out)
 5. freeze      – no frozen picture longer than qa.freeze_max_s (stalled render / accidental still)
 6. slideshow   – motion profile: static ratio below threshold
 7. loudness    – integrated LUFS within ±1 LU of target, true peak ≤ limit, LRA ≤ max
 8. clipping    – no clipped samples
 9. dead_air    – no silence > 2 s inside the programme
10. subtitles   – cps / chars-per-line / overlap / gaps / coverage of narration, ASR sync error
11. vision      – (optional) Qwen reviews sampled frames vs. the scene plan
"""
from __future__ import annotations

import re
from pathlib import Path

from .config import settings
from .tools import analysis, audio
from .tools import subtitles as subs


def _r(name: str, status: str, msg: str, **ev) -> dict:
    return {"check": name, "status": status, "message": msg, "evidence": ev}


def check_container(src: str, w: int, h: int, fps: float) -> list[dict]:
    p = analysis.probe(src)
    out = []
    v, a = p.get("video"), p.get("audio")
    if not v:
        return [_r("container", "fail", "no video stream")]
    errs = []
    if v["codec"] != "h264":
        errs.append(f"video codec {v['codec']}")
    if v["pix_fmt"] != "yuv420p":
        errs.append(f"pix_fmt {v['pix_fmt']}")
    if (v["width"], v["height"]) != (w, h):
        errs.append(f"resolution {v['width']}x{v['height']} ≠ {w}x{h}")
    if abs(v["fps"] - fps) > 0.05:
        errs.append(f"fps {v['fps']} ≠ {fps}")
    if not a:
        errs.append("no audio stream")
    else:
        if a["codec"] != "aac":
            errs.append(f"audio codec {a['codec']}")
        if a["sample_rate"] != 48000:
            errs.append(f"sample rate {a['sample_rate']}")
        if a["channels"] != 2:
            errs.append(f"{a['channels']} channels")
        drift = abs((v.get("duration") or p["duration"]) - (a.get("duration") or p["duration"]))
        if drift > 0.1:
            errs.append(f"A/V duration drift {drift:.2f}s")
    out.append(_r("container", "fail" if errs else "pass", "; ".join(errs) or "H.264/AAC 48k stereo, spec OK", probe=p))
    return out


def check_delivery(src: str, promise: dict, has_subs: bool) -> dict:
    p = analysis.probe(src)
    d, target = p["duration"], float(promise.get("duration_s", 0) or 0)
    d_prog = d - float(promise.get("extra_s", 0) or 0)       # e.g. end-credits are not part of the promised runtime
    errs, warns = [], []
    if target:
        dev = abs(d_prog - target) / target
        (errs if dev > 0.10 else warns if dev > 0.05 else []).append(f"duration {d_prog:.1f}s vs promised {target:.0f}s ({dev:.0%})")
    asp = analysis.aspect(src)
    if promise.get("aspect") and asp != promise["aspect"]:
        errs.append(f"aspect {asp} ≠ {promise['aspect']}")
    if promise.get("subtitles") and not has_subs:
        errs.append("subtitles were promised but are missing")
    st = "fail" if errs else "warn" if warns else "pass"
    return _r("delivery", st, "; ".join(errs + warns) or f"{d:.1f}s, {asp}", duration=d, aspect=asp)


def check_frames(src: str, workdir: Path) -> dict:
    frames = analysis.sample_frames(src, str(workdir / "frames"))
    bad = []
    stats = []
    for f in frames:
        s = analysis.frame_stats(f)
        stats.append({"frame": f, **s})
        if s["luma_max"] < 40:          # nothing bright anywhere → black (dark-themed graphics still pass)
            bad.append(f"{Path(f).name}: black (max luma {s['luma_max']:.0f})")
        elif s["luma"] > 240:
            bad.append(f"{Path(f).name}: blown out")
        elif s["luma_max"] - s["luma_min"] < 12:
            bad.append(f"{Path(f).name}: flat/blank frame")
    return _r("frames", "fail" if bad else "pass", "; ".join(bad) or "4/4 sampled frames look valid",
              frames=frames, stats=stats)


def check_black_freeze_motion(src: str, duration: float) -> list[dict]:
    q = settings().get("qa", {}) or {}
    lo, hi = 0.6, max(0.6, duration - 0.8)          # ignore intentional fade-in / fade-out
    blacks = []
    for b in analysis.black_frames(src, pix_th=0.04):
        s, e = max(b["start"], lo), min(b["end"], hi)
        if e > s:
            blacks.append({"start": s, "end": e, "duration": round(e - s, 3)})
    ratio = sum(b["duration"] for b in blacks) / max(duration, 0.1)
    out = [_r("black", "fail" if ratio > float(q.get("black_frame_ratio_max", 0.02)) else "pass",
              f"black inside programme: {ratio:.1%}", spans=blacks)]
    fr = analysis.freezes(src, min_d=float(q.get("freeze_max_s", 2.5)))
    out.append(_r("freeze", "warn" if fr else "pass", f"{len(fr)} frozen spans ≥ {q.get('freeze_max_s', 2.5)}s", spans=fr))
    mp = analysis.motion_profile(src)
    st = "fail" if mp["static_ratio"] > 0.6 else "warn" if mp["static_ratio"] > 0.35 else "pass"
    out.append(_r("slideshow", st, f"static ratio {mp['static_ratio']:.0%} (mean motion {mp['mean']})", **mp))
    return out


def check_audio(src: str, duration: float, target: float | None = None) -> list[dict]:
    q = settings().get("qa", {}) or {}
    target = target if target is not None else float(q.get("loudness_lufs", -14))
    out = []
    m = audio.measure_loudness(src)
    if not m:
        return [_r("loudness", "fail", "could not measure loudness")]
    errs = []
    if abs(m["integrated_lufs"] - target) > 1.0:
        errs.append(f"integrated {m['integrated_lufs']:.1f} LUFS (target {target})")
    if m["true_peak_db"] > float(q.get("true_peak_db", -1.0)) + 0.3:
        errs.append(f"true peak {m['true_peak_db']:.1f} dBTP")
    warn = m["lra"] > float(q.get("lra_max", 11))
    out.append(_r("loudness", "fail" if errs else "warn" if warn else "pass",
                  "; ".join(errs) or f"{m['integrated_lufs']:.1f} LUFS, TP {m['true_peak_db']:.1f}, LRA {m['lra']:.1f}",
                  **{k: v for k, v in m.items() if k != "_raw"}))
    c = audio.clipping(src)
    out.append(_r("clipping", "fail" if c["clipped_samples"] > 10 else "pass",
                  f"{c['clipped_samples']} clipped samples, peak {c['peak_db']:.1f} dB", **c))
    sil = [s for s in audio.detect_silence(src, -50, 2.0) if s["start"] > 0.5 and s["end"] < duration - 1.0]
    out.append(_r("dead_air", "warn" if sil else "pass", f"{len(sil)} silent gaps > 2s", spans=sil))
    return out


def check_subtitles(cues: list[dict], narration_spans: list[dict], words: list[dict] | None = None) -> dict:
    q = settings().get("qa", {}) or {}
    issues, warns = [], []
    for i, c in enumerate(cues):
        text = c["text"].replace("\n", "")
        max_line, max_cps = subs.limits(text)
        dur = c["end"] - c["start"]
        units = len(re.sub(r"\s", "", text)) if subs.is_cjk(text) else len(text)
        cps = units / max(dur, 0.01)
        if dur < 0.6:
            issues.append(f"#{i+1} too short ({dur:.2f}s)")
        if cps > max_cps * 1.15:
            issues.append(f"#{i+1} {cps:.1f} cps > {max_cps}")
        elif cps > max_cps:
            warns.append(f"#{i+1} {cps:.1f} cps")
        if any(len(line) > max_line for line in c["text"].split("\n")):
            issues.append(f"#{i+1} line > {max_line} chars")
        if i and c["start"] < cues[i - 1]["end"] - 0.01:
            issues.append(f"#{i+1} overlaps previous")
    # coverage: every narration span must have cues
    for sp in narration_spans:
        if not any(c["start"] < sp["end"] and c["end"] > sp["start"] for c in cues):
            issues.append(f"narration at {sp['start']:.1f}s has no subtitle")
    sync = None
    if words:
        tol = float(q.get("subtitle_sync_tolerance_ms", 250)) / 1000
        aligned = subs.align_to_words(cues, words)
        errs = [abs(a["start"] - c["start"]) for a, c in zip(aligned, cues) if a.get("aligned")]
        if errs:
            sync = {"mean_ms": round(sum(errs) / len(errs) * 1000), "max_ms": round(max(errs) * 1000),
                    "aligned_ratio": round(len(errs) / len(cues), 2)}
            if sync["mean_ms"] > tol * 1000:
                issues.append(f"subtitle sync mean error {sync['mean_ms']} ms > {tol*1000:.0f} ms")
            if sync["aligned_ratio"] < 0.5:
                warns.append(f"only {sync['aligned_ratio']:.0%} of cues matched the ASR words")
        else:
            warns.append("subtitle sync could not be verified against ASR (no cue matched)")
            sync = {"aligned_ratio": 0.0}
    st = "fail" if issues else "warn" if warns else "pass"
    return _r("subtitles", st, "; ".join(issues[:8] + warns[:4]) or f"{len(cues)} cues OK", sync=sync, cues=len(cues))


def run_all(src: str, *, promise: dict, w: int, h: int, fps: float, workdir: Path, cues: list[dict] | None = None,
            narration_spans: list[dict] | None = None, words: list[dict] | None = None,
            vision: callable | None = None) -> dict:
    workdir.mkdir(parents=True, exist_ok=True)
    dur = analysis.probe(src)["duration"]
    results: list[dict] = []
    results += check_container(src, w, h, fps)
    results.append(check_delivery(src, promise, bool(cues)))
    fr = check_frames(src, workdir)
    results.append(fr)
    results += check_black_freeze_motion(src, dur)
    results += check_audio(src, dur)
    if cues is not None:
        results.append(check_subtitles(cues, narration_spans or [], words))
    if vision:
        try:
            results.append(vision(fr["evidence"]["frames"]))
        except Exception as e:  # noqa: BLE001
            results.append(_r("vision", "warn", f"vision review unavailable: {e}"))
    worst = "fail" if any(r["status"] == "fail" for r in results) else "warn" if any(r["status"] == "warn" for r in results) else "pass"
    return {"status": worst, "results": results, "file": src, "duration": dur}
