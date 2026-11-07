"""Video editing tools (FFmpeg)."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..config import settings
from ..media import ff
from .registry import tool

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
XFADE = {"fade", "dissolve", "wipeleft", "wiperight", "wipeup", "wipedown", "slideleft", "slideright", "slideup",
         "slidedown", "circleopen", "circleclose", "radial", "smoothleft", "smoothright", "zoomin", "fadeblack",
         "fadewhite", "pixelize", "hblur", "distance", "squeezeh", "squeezev"}


def _enc(crf: int | None = None, preset: str | None = None) -> list[str]:
    r = settings().get("render", {}) or {}
    return ["-c:v", r.get("video_codec", "libx264"), "-crf", str(crf or r.get("crf", 18)),
            "-preset", preset or r.get("preset", "medium"), "-pix_fmt", r.get("pix_fmt", "yuv420p")]


def _aenc() -> list[str]:
    r = settings().get("render", {}) or {}
    return ["-c:a", r.get("audio_codec", "aac"), "-b:a", r.get("audio_bitrate", "192k"), "-ar", "48000", "-ac", "2"]


def _fit(w: int, h: int, fit: str) -> str:
    if fit == "contain":
        return f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"
    if fit == "blur":   # vertical-friendly: blurred fill behind the contained image
        return (f"split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=30:3[bg];"
                f"[b]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"


@tool("video.normalize", "video")
def normalize(src: str, out: str, w: int, h: int, fps: int = 24, seconds: float | None = None,
              fit: str = "cover", keep_audio: bool = True, start: float = 0.0) -> str:
    """Conform any clip or still to WxH@fps, exact duration, with a stereo 48 kHz audio track."""
    src_p = Path(src)
    is_img = src_p.suffix.lower() in IMG_EXT
    if is_img:
        return ken_burns(src, out, seconds or 5, w, h, fps)
    has_a = keep_audio and ff.has_audio(src)
    src_dur = ff.duration(src)
    loop = seconds is not None and src_dur - start < seconds - 0.05
    args = (["-stream_loop", "-1"] if loop else []) + (["-ss", f"{start:.3f}"] if start else []) + ["-i", src]
    args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    vf = f"[0:v]{_fit(w, h, fit)},fps={fps},setsar=1,format=yuv420p[v]"
    af = "[0:a]aresample=48000,aformat=channel_layouts=stereo[a]" if has_a else "[1:a]anull[a]"
    args += ["-filter_complex", f"{vf};{af}", "-map", "[v]", "-map", "[a]"]
    if seconds:
        args += ["-t", f"{seconds:.3f}"]
    else:
        args += ["-shortest"]
    ff.run([*args, *_enc(preset="veryfast"), *_aenc(), out])
    return out


@tool("video.ken_burns", "video", tags=["documentary"])
def ken_burns(image: str, out: str, seconds: float, w: int = 1920, h: int = 1080, fps: int = 24,
              direction: str = "in", focus: tuple[float, float] = (0.5, 0.5)) -> str:
    """Animate a still with a slow Ken Burns zoom/pan (documentary style)."""
    frames = max(1, int(round(seconds * fps)))
    fx, fy = focus
    z = "min(1+0.0009*on,1.15)" if direction == "in" else "max(1.15-0.0009*on,1.0)"
    pan = {"left": f"iw*on/{frames}*0.1", "right": f"iw*(1-on/{frames})*0.1"}.get(direction)
    x = pan or f"(iw-iw/zoom)*{fx}"
    vf = (f"scale={w*2}:{h*2}:force_original_aspect_ratio=increase,crop={w*2}:{h*2},"
          f"zoompan=z='{z if not pan else 1.1}':x='{x}':y='(ih-ih/zoom)*{fy}':d={frames}:s={w}x{h}:fps={fps},"
          f"format=yuv420p,setsar=1")
    ff.run(["-loop", "1", "-i", image, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-vf", vf,
            "-t", f"{seconds:.3f}", "-map", "0:v", "-map", "1:a", *_enc(preset="veryfast"), *_aenc(), out])
    return out


@tool("video.trim", "video")
def trim(src: str, out: str, start: float, end: float) -> str:
    """Frame-accurate trim (re-encodes)."""
    ff.run(["-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", src, *_enc(), *_aenc(), out])
    return out


@tool("video.concat", "video")
def concat(clips: Sequence[str], out: str) -> str:
    """Hard-cut concatenation of conformed clips (same size/fps/audio layout)."""
    n = len(clips)
    ins: list[str] = []
    for c in clips:
        ins += ["-i", c]
    fc = "".join(f"[{i}:v][{i}:a]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]"
    ff.run([*ins, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", *_enc(), *_aenc(), out])
    return out


@tool("video.xfade_chain", "video", tags=["edit"])
def xfade_chain(clips: Sequence[str], out: str, transitions: Sequence[dict] | None = None, fps: int = 24) -> str:
    """Join clips with per-cut transitions (xfade + acrossfade). transitions[i] joins clip i and i+1."""
    if len(clips) == 1:
        Path(out).write_bytes(Path(clips[0]).read_bytes())
        return out
    durs = [ff.duration(c) for c in clips]
    trans = list(transitions or [])
    ins: list[str] = []
    for c in clips:
        ins += ["-i", c]
    # common timebase / fps / format so concat and xfade can be chained freely
    vparts = [f"[{i}:v]fps={fps},format=yuv420p,setsar=1,settb=AVTB[s{i}]" for i in range(len(clips))]
    aparts = [f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo:sample_fmts=fltp[t{i}]" for i in range(len(clips))]
    vlast, alast = "[s0]", "[t0]"
    t_acc = durs[0]
    for i in range(1, len(clips)):
        tr = trans[i - 1] if i - 1 < len(trans) else {"type": "fade", "duration": 0.4}
        typ = tr.get("type", "fade")
        d = float(tr.get("duration", 0.4))
        if typ == "cut" or d < 2.0 / fps:          # hard cut: concat (xfade needs ≥ 2 frames)
            vparts.append(f"{vlast}[s{i}]concat=n=2:v=1:a=0,settb=AVTB[v{i}]")
            aparts.append(f"{alast}[t{i}]concat=n=2:v=0:a=1[a{i}]")
            vlast, alast = f"[v{i}]", f"[a{i}]"
            t_acc += durs[i]
            continue
        typ = typ if typ in XFADE else "fade"
        d = min(d, durs[i - 1] / 2, durs[i] / 2)
        off = t_acc - d
        vparts.append(f"{vlast}[s{i}]xfade=transition={typ}:duration={d:.3f}:offset={off:.3f},settb=AVTB[v{i}]")
        aparts.append(f"{alast}[t{i}]acrossfade=d={d:.3f}:c1=tri:c2=tri[a{i}]")
        vlast, alast = f"[v{i}]", f"[a{i}]"
        t_acc = off + durs[i]
    fc = ";".join(vparts + aparts)
    ff.run([*ins, "-filter_complex", fc, "-map", vlast, "-map", alast, *_enc(), *_aenc(), out])
    return out


@tool("video.reframe", "video", tags=["social"])
def reframe(src: str, out: str, aspect: str = "9:16", mode: str = "blur") -> str:
    """Convert between aspect ratios (center crop, contain, or blurred-fill)."""
    a, b = (int(x) for x in aspect.split(":"))
    vs = ff.video_stream(src) or {}
    h = int(vs.get("height", 1080))
    h = 1920 if a < b else h
    w = int(round(h * a / b / 2) * 2)
    fit = {"crop": "cover", "contain": "contain", "blur": "blur"}[mode]
    ff.run(["-i", src, "-filter_complex", f"[0:v]{_fit(w, h, fit)},setsar=1[v]", "-map", "[v]", "-map", "0:a?",
            *_enc(), "-c:a", "copy", out])
    return out


def _vf_tool(name: str, summary: str, vf: str, category: str = "video", **defaults):
    def fn(src: str, out: str, **kw) -> str:
        params = {**defaults, **kw}
        ff.run(["-i", src, "-vf", vf.format(**params), "-map", "0:v", "-map", "0:a?", *_enc(), "-c:a", "copy", out])
        return out
    fn.__doc__ = summary
    fn.__name__ = name.split(".")[-1]
    tool(name, category)(fn)
    return fn


# --- one-filter tools ---------------------------------------------------------
_vf_tool("video.stabilize", "Stabilise shaky footage (deshake).", "deshake")
_vf_tool("video.denoise", "Temporal/spatial denoise (hqdn3d).", "hqdn3d={strength}", strength=4)
_vf_tool("video.sharpen", "Unsharp mask.", "unsharp=5:5:{amount}:5:5:0", amount=0.8)
_vf_tool("video.deinterlace", "Deinterlace archival/broadcast footage (yadif).", "yadif")
_vf_tool("video.flip_h", "Mirror horizontally.", "hflip")
_vf_tool("video.flip_v", "Flip vertically.", "vflip")
_vf_tool("video.rotate", "Rotate by degrees.", "rotate={deg}*PI/180:fillcolor=black", deg=90)
_vf_tool("video.speed", "Change playback speed (video only; pair with audio.tempo).", "setpts=PTS/{factor}", factor=1.5)
_vf_tool("video.reverse", "Reverse a short clip.", "reverse")
_vf_tool("video.fps_convert", "Change frame rate by dropping/duplicating.", "fps={fps}", fps=24)
_vf_tool("video.interpolate", "Motion-interpolated frame rate (smooth slow-mo source).", "minterpolate=fps={fps}:mi_mode=mci", fps=48)
_vf_tool("video.vignette", "Add a vignette.", "vignette=PI/{k}", k=5)
_vf_tool("video.film_grain", "Add animated film grain.", "noise=alls={amount}:allf=t+u", amount=12)
_vf_tool("video.black_white", "Convert to monochrome.", "hue=s=0")
_vf_tool("video.sepia", "Sepia tone.", "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131")
_vf_tool("video.blur", "Gaussian blur.", "gblur=sigma={sigma}", sigma=8)
_vf_tool("video.pixelate", "Pixelate (anonymise).", "scale=iw/{block}:ih/{block},scale=iw*{block}:ih*{block}:flags=neighbor", block=16)
_vf_tool("video.letterbox", "Cinematic letterbox bars.", "drawbox=y=0:h=ih*{bar}:color=black:t=fill,drawbox=y=ih*(1-{bar}):h=ih*{bar}:color=black:t=fill", bar=0.12)
_vf_tool("video.crop", "Crop to w:h:x:y.", "crop={w}:{h}:{x}:{y}", w="iw", h="ih", x=0, y=0)
_vf_tool("video.scale", "Scale to WxH.", "scale={w}:{h}:flags=lanczos", w=1920, h=1080)
_vf_tool("video.pad", "Pad to WxH (centered).", "pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={color}", w=1920, h=1080, color="black")
_vf_tool("video.fade", "Fade video in/out.", "fade=t=in:d={d_in},fade=t=out:st={out_start}:d={d_out}", d_in=0.5, d_out=0.5, out_start=0)
_vf_tool("video.chroma_key", "Remove a green-screen colour (outputs with alpha via overlay tools).", "chromakey={color}:{similarity}:{blend}", color="0x00FF00", similarity=0.15, blend=0.05)
_vf_tool("video.timecode", "Burn running timecode (review copies).", "drawtext=timecode='00\\:00\\:00\\:00':rate={fps}:fontcolor=white:fontsize=28:box=1:boxcolor=black@0.5:x=20:y=20", fps=24)
_vf_tool("video.punch_in", "Punch-in zoom for emphasis.", "scale=iw*{z}:ih*{z},crop=iw/{z}:ih/{z}", z=1.15)
_vf_tool("video.shake", "Handheld camera shake.", "crop=iw-40:ih-40:20+15*sin(t*7):20+12*cos(t*9),scale=iw+40:ih+40", )
_vf_tool("video.glitch", "Digital glitch accent.", "rgbashift=rh={px}:bh=-{px},noise=alls=20:allf=t", px=6)
_vf_tool("video.old_film", "Archival film look (sepia, grain, flicker, vignette).",
         "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131,noise=alls=18:allf=t,"
         "eq=brightness='0.03*sin(t*25)',vignette=PI/4")
_vf_tool("video.lut", "Apply a .cube 3D LUT.", "lut3d=file='{lut}'", lut="look.cube")


GRADES = {
    "neutral": "eq=contrast=1.03:saturation=1.05",
    "teal_orange": "colorbalance=rs=.06:gs=-.02:bs=-.08:rh=-.05:bh=.08,eq=contrast=1.08:saturation=1.15",
    "archival": "eq=contrast=1.1:saturation=0.75:gamma=0.95,curves=preset=vintage",
    "documentary": "eq=contrast=1.06:saturation=0.92,curves=preset=medium_contrast",
    "vibrant": "eq=contrast=1.08:saturation=1.35,unsharp=3:3:0.4",
    "noir": "hue=s=0,eq=contrast=1.35:brightness=-0.03,vignette=PI/4",
    "warm": "colortemperature=temperature=4800,eq=saturation=1.08",
    "cool": "colortemperature=temperature=7600,eq=saturation=0.98",
    # luxury fashion film: muted colour, lifted blacks, a little teal in the shadows, fine grain, soft vignette
    "fashion_film": "eq=contrast=1.04:saturation=0.8:gamma=1.02,colorbalance=bs=.04:gs=.015:rh=.03:bh=-.02,"
                    "curves=all='0/0.03 0.5/0.5 1/0.97',noise=alls=5:allf=t+u,vignette=PI/5",
}


@tool("video.color_grade", "video", tags=["finishing"])
def color_grade(src: str, out: str, preset: str = "neutral") -> str:
    """Apply a named grade: neutral, teal_orange, archival, documentary, vibrant, noir, warm, cool."""
    ff.run(["-i", src, "-vf", GRADES.get(preset, GRADES["neutral"]), "-map", "0:v", "-map", "0:a?", *_enc(),
            "-c:a", "copy", out])
    return out


@tool("video.overlay", "video")
def overlay(src: str, layer: str, out: str, x: str = "W-w-40", y: str = "40", start: float = 0, end: float = 1e9,
            scale: float = 1.0) -> str:
    """Overlay an image/video layer (logo, PiP, graphic) during [start, end]."""
    fc = (f"[1:v]scale=iw*{scale}:ih*{scale}[l];[0:v][l]overlay={x}:{y}:enable='between(t,{start},{end})':"
          f"eof_action=pass[v]")
    ff.run(["-i", src, "-i", layer, "-filter_complex", fc, "-map", "[v]", "-map", "0:a?", *_enc(), "-c:a", "copy", out])
    return out


@tool("video.picture_in_picture", "video")
def picture_in_picture(src: str, pip: str, out: str, corner: str = "br", size: float = 0.3) -> str:
    """Inset a second video in a corner."""
    pos = {"br": ("W-w-40", "H-h-40"), "bl": ("40", "H-h-40"), "tr": ("W-w-40", "40"), "tl": ("40", "40")}[corner]
    fc = f"[1:v]scale=iw*{size}:-2[p];[0:v][p]overlay={pos[0]}:{pos[1]}:shortest=1[v]"
    ff.run(["-i", src, "-i", pip, "-filter_complex", fc, "-map", "[v]", "-map", "0:a?", *_enc(), "-c:a", "copy", out])
    return out


@tool("video.split_screen", "video")
def split_screen(left: str, right: str, out: str, w: int = 1920, h: int = 1080) -> str:
    """Side-by-side comparison."""
    fc = (f"[0:v]scale={w//2}:{h}:force_original_aspect_ratio=increase,crop={w//2}:{h}[l];"
          f"[1:v]scale={w//2}:{h}:force_original_aspect_ratio=increase,crop={w//2}:{h}[r];[l][r]hstack[v]")
    ff.run(["-i", left, "-i", right, "-filter_complex", fc, "-map", "[v]", "-map", "0:a?", "-shortest", *_enc(), *_aenc(), out])
    return out


@tool("video.grid", "video")
def grid(clips: Sequence[str], out: str, cols: int = 2, cell_w: int = 960, cell_h: int = 540) -> str:
    """Mosaic of N clips (xstack)."""
    ins: list[str] = []
    for c in clips:
        ins += ["-i", c]
    n = len(clips)
    pre = ";".join(f"[{i}:v]scale={cell_w}:{cell_h}:force_original_aspect_ratio=increase,crop={cell_w}:{cell_h}[c{i}]"
                   for i in range(n))
    layout = "|".join(f"{(i % cols) * cell_w}_{(i // cols) * cell_h}" for i in range(n))
    fc = f"{pre};{''.join(f'[c{i}]' for i in range(n))}xstack=inputs={n}:layout={layout}:shortest=1[v]"
    ff.run([*ins, "-filter_complex", fc, "-map", "[v]", *_enc(), out])
    return out


@tool("video.text", "video", tags=["typography"])
def text(src: str, out: str, text: str, x: str = "(w-text_w)/2", y: str = "h*0.8", size: int = 56,
         color: str = "white", start: float = 0, end: float = 1e9, box: bool = True, font: str | None = None) -> str:
    """Draw text on video (titles, labels)."""
    from .motion_engine import default_font
    fontfile = ff.esc_filter_path(font or default_font())
    dt = (f"drawtext=fontfile='{fontfile}':text='{ff.esc_text(text)}':x={x}:y={y}:fontsize={size}:fontcolor={color}:"
          f"enable='between(t,{start},{end})'" + (":box=1:boxcolor=black@0.45:boxborderw=18" if box else ""))
    ff.run(["-i", src, "-vf", dt, "-map", "0:v", "-map", "0:a?", *_enc(), "-c:a", "copy", out])
    return out


@tool("video.freeze_frame", "video")
def freeze_frame(src: str, out: str, at: float, hold: float = 1.5) -> str:
    """Freeze a frame for `hold` seconds at time `at` (emphasis beat)."""
    ff.run(["-i", src, "-vf", f"tpad=stop_mode=clone:stop_duration=0,loop=loop={int(hold*24)}:size=1:start={int(at*24)}",
            "-an", *_enc(), out])
    return out


@tool("video.loop_to", "video")
def loop_to(src: str, out: str, seconds: float) -> str:
    """Loop a clip to an exact duration."""
    ff.run(["-stream_loop", "-1", "-i", src, "-t", f"{seconds:.3f}", *_enc(), *_aenc(), out])
    return out


@tool("video.extract_audio", "video")
def extract_audio(src: str, out: str) -> str:
    """Extract the audio track as 48 kHz WAV."""
    ff.run(["-i", src, "-vn", "-ar", "48000", "-ac", "2", out])
    return out


@tool("video.replace_audio", "video")
def replace_audio(src: str, audio: str, out: str) -> str:
    """Replace a video's audio with another track (trimmed to the video)."""
    ff.run(["-i", src, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", *_aenc(), "-shortest", out])
    return out


@tool("video.mute", "video")
def mute(src: str, out: str) -> str:
    """Drop audio."""
    ff.run(["-i", src, "-an", "-c:v", "copy", out])
    return out


@tool("video.thumbnail", "video")
def thumbnail(src: str, out: str, at: float | None = None) -> str:
    """Pick a representative frame (or the frame at `at`)."""
    if at is None:
        ff.run(["-i", src, "-vf", "thumbnail=120,scale=1280:-2", "-frames:v", "1", out])
    else:
        ff.run(["-ss", f"{at:.3f}", "-i", src, "-frames:v", "1", "-vf", "scale=1280:-2", out])
    return out


@tool("video.contact_sheet", "video", tags=["review"])
def contact_sheet(src: str, out: str, cols: int = 4, rows: int = 3, width: int = 1600) -> str:
    """Grid of evenly spaced frames for storyboard review."""
    n = cols * rows
    d = max(0.1, ff.duration(src))
    ff.run(["-i", src, "-vf", f"fps={n}/{d:.3f},scale={width//cols}:-2,tile={cols}x{rows}:padding=4:margin=4",
            "-frames:v", "1", out])
    return out


@tool("video.gif_preview", "video")
def gif_preview(src: str, out: str, width: int = 480, fps: int = 10) -> str:
    """Palette-optimised GIF preview."""
    ff.run(["-i", src, "-vf", f"fps={fps},scale={width}:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse",
            out])
    return out


@tool("video.extract_frames", "video")
def extract_frames(src: str, out_dir: str, every: float = 1.0) -> list[str]:
    """Dump frames every N seconds as JPEG."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    ff.run(["-i", src, "-vf", f"fps=1/{every}", "-q:v", "3", str(Path(out_dir) / "f_%05d.jpg")])
    return sorted(str(p) for p in Path(out_dir).glob("f_*.jpg"))


@tool("video.last_frame", "video", tags=["continuity"])
def last_frame(src: str, out: str) -> str:
    """Grab the final frame (feeds H3 first-frame continuity between shots)."""
    ff.run(["-sseof", "-0.1", "-i", src, "-frames:v", "1", "-update", "1", out])
    return out


@tool("video.scroll_credits", "video")
def scroll_credits(lines: Sequence[str], out: str, seconds: float = 8, w: int = 1920, h: int = 1080) -> str:
    """Rolling end-credits card (source attributions)."""
    from .motion_engine import default_font
    txt = Path(out).with_suffix(".txt")
    txt.write_text("\n".join(lines), encoding="utf-8")
    fontfile = ff.esc_filter_path(default_font())
    vf = (f"drawtext=fontfile='{fontfile}':textfile='{ff.esc_filter_path(txt)}':fontcolor=white:fontsize={h//36}:"
          f"line_spacing=12:x=(w-text_w)/2:y=max((h-text_h)/2\\,h*0.55-t*(h*0.55)/{max(1.0, seconds * 0.6):.2f})")
    ff.run(["-f", "lavfi", "-i", f"color=c=0x1a1e29:s={w}x{h}:r=24:d={seconds}", "-f", "lavfi", "-i",
            "anullsrc=r=48000:cl=stereo", "-vf", vf, "-t", str(seconds), *_enc(), *_aenc(), out])
    return out


DELIVERY = {
    "youtube": {"w": 1920, "h": 1080, "crf": 18, "fps": 24},
    "youtube_4k": {"w": 3840, "h": 2160, "crf": 18, "fps": 24},
    "shorts": {"w": 1080, "h": 1920, "crf": 19, "fps": 30},
    "reels": {"w": 1080, "h": 1920, "crf": 19, "fps": 30},
    "tiktok": {"w": 1080, "h": 1920, "crf": 20, "fps": 30},
    "square": {"w": 1080, "h": 1080, "crf": 19, "fps": 30},
    "broadcast": {"w": 1920, "h": 1080, "crf": 16, "fps": 25},
}


@tool("video.encode_delivery", "video", tags=["delivery"])
def encode_delivery(src: str, out: str, target: str = "youtube") -> str:
    """Final encode for a platform preset (H.264 High, AAC 48k, faststart)."""
    p = DELIVERY[target]
    ff.run(["-i", src, "-vf", f"{_fit(p['w'], p['h'], 'contain')},fps={p['fps']},setsar=1",
            *_enc(crf=p["crf"], preset="slow"), "-profile:v", "high", "-movflags", "+faststart", *_aenc(), out])
    return out


@tool("video.proxy", "video")
def proxy(src: str, out: str, height: int = 540) -> str:
    """Low-res proxy for fast board previews."""
    ff.run(["-i", src, "-vf", f"scale=-2:{height}", "-c:v", "libx264", "-crf", "28", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "96k", out])
    return out


@tool("video.master_prores", "video", tags=["delivery"])
def master_prores(src: str, out: str) -> str:
    """ProRes 422 HQ mezzanine master (.mov) for further grading."""
    ff.run(["-i", src, "-c:v", "prores_ks", "-profile:v", "3", "-c:a", "pcm_s24le", out])
    return out
