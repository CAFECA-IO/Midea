"""Automatic acceptance checks for actor photos.

Uses RTMW whole-body pose (rtmlib + onnxruntime on CPU, Apache-2.0): 133 keypoints = COCO body,
feet (toes / heels), 68 face points and hands, each with a confidence. No GPU, no system GL libraries.

check(view, path) -> {"status": "pass"|"fail"|"skip", "score": 0..1, "issues": [...], "metrics": {...}}
"skip" = checker unavailable (mock mode, rtmlib missing) — callers treat it as pass.
Thresholds live in config.yaml → verify.* so they can be tuned without code changes.
"""
from __future__ import annotations

import threading
from pathlib import Path

from .config import settings
from .log import get_logger

log = get_logger("vision_check")
_lock = threading.Lock()
_model = None

NOSE, L_EYE, R_EYE = 0, 1, 2
L_SH, R_SH, L_HIP, R_HIP, L_ANK, R_ANK = 5, 6, 11, 12, 15, 16
FEET = list(range(17, 23))           # big toe, small toe, heel × 2
FACE = list(range(23, 91))


def _t(key: str, default: float) -> float:
    return float(settings().get(f"verify.{key}", default))


def _load():
    global _model
    if _model is None:
        from rtmlib import Wholebody
        _model = Wholebody(mode=str(settings().get("verify.mode", "balanced")), backend="onnxruntime", device="cpu")
    return _model


def analyze(path: str | Path) -> dict | None:
    """Keypoints of every detected person (normalised x/y + score); None when the checker is unavailable."""
    if settings().mode == "mock":
        return None
    try:
        import cv2
        import numpy as np
        with _lock:
            model = _load()
            img = cv2.imread(str(path))
            if img is None:
                raise ValueError(f"cannot read {path}")
            kpts, scores = model(img)
    except Exception as e:  # noqa: BLE001 — never block generation on the checker
        log.warning("vision check unavailable: %s", e)
        return None
    h, w = img.shape[:2]
    people = []
    for k, s in zip(kpts, scores):
        if float(np.mean(s[:17])) < 0.25:             # spurious detections
            continue
        people.append([{"x": float(x) / w, "y": float(y) / h, "s": float(c)} for (x, y), c in zip(k, s)])
    return {"poses": people, "w": w, "h": h}


def _mean(lm, idx) -> float:
    return sum(lm[i]["s"] for i in idx) / len(idx)


def check(view: str, path: str | Path) -> dict:
    a = analyze(path)
    if a is None:
        return {"status": "skip", "score": 1.0, "issues": [], "metrics": {}}
    issues: list[str] = []
    m: dict = {"people": len(a["poses"])}
    if len(a["poses"]) != 1:
        issues.append("畫面中不是剛好一個人" if a["poses"] else "偵測不到人物")
        return {"status": "fail", "score": 0.0, "issues": issues, "metrics": m}
    lm = a["poses"][0]
    full = view.startswith("full_")
    face = _mean(lm, FACE)
    m["face"] = round(face, 2)
    if full:
        sh_y = (lm[L_SH]["y"] + lm[R_SH]["y"]) / 2
        hip_y = (lm[L_HIP]["y"] + lm[R_HIP]["y"]) / 2
        torso = max(1e-3, hip_y - sh_y)
        sw = abs(lm[L_SH]["x"] - lm[R_SH]["x"]) / torso
        ank = min(lm[L_ANK]["s"], lm[R_ANK]["s"])
        feet = _mean(lm, FEET)
        bottom = max(lm[i]["y"] for i in FEET + [L_ANK, R_ANK])
        top = min(lm[i]["y"] for i in [NOSE, L_EYE, R_EYE]) - max(0.03, (sh_y - lm[NOSE]["y"]) * 0.9)
        # facing: seen from the front the person's left shoulder is on the image's right (x_L > x_R);
        # seen from behind it flips. Face keypoint confidences are unreliable for back views (the model
        # hallucinates a face on the back of the head), the left/right order is not.
        facing = (lm[L_SH]["x"] - lm[R_SH]["x"]) + (lm[L_HIP]["x"] - lm[R_HIP]["x"])
        m["facing"] = round(facing, 3)
        m.update(shoulder_ratio=round(sw, 3), ankles=round(ank, 2), feet=round(feet, 2), feet_bottom=round(bottom, 3),
                 head_top=round(top, 3))
        if ank < _t("ankle_min", 0.5) or feet < _t("feet_min", 0.45):
            issues.append("看不到腳踝或鞋子")
        elif bottom > _t("bottom_max", 0.985):
            issues.append("腳底貼齊或超出畫面下緣")
        if top < 0:
            issues.append("頭頂被裁切")
        if view == "full_front":
            if face < _t("face_min", 0.6):
                issues.append("看不清楚正面的臉")
            if sw < _t("front_shoulder_min", 0.45) or facing <= 0:
                issues.append("身體沒有正對鏡頭")
        if view == "full_side" and sw > _t("side_shoulder_max", 0.35):
            issues.append("不是正側面（兩肩仍然展開）")
        if view == "full_back" and (facing > -_t("back_facing_min", 0.05) or sw < _t("front_shoulder_min", 0.45)):
            issues.append("不是背面（仍朝向鏡頭或側身）")
    else:
        if face < _t("face_min", 0.6):
            issues.append("看不清楚臉")
        eye_d = abs(lm[L_EYE]["x"] - lm[R_EYE]["x"]) or 1e-3
        yaw = abs(lm[NOSE]["x"] - (lm[L_EYE]["x"] + lm[R_EYE]["x"]) / 2) / eye_d
        m["yaw_ratio"] = round(yaw, 3)
        if view == "three_quarter" and yaw < _t("three_quarter_yaw_min", 0.15):
            issues.append("臉幾乎是正面，不是四分之三側臉")
        if view == "headshot" and yaw > _t("headshot_yaw_max", 0.2):
            issues.append("臉沒有正對鏡頭")
    score = max(0.0, 1.0 - 0.34 * len(issues))
    return {"status": "pass" if not issues else "fail", "score": round(score, 2), "issues": issues, "metrics": m}


def fix_floor_margin(path: str | Path, feet_bottom: float, target: float | None = None) -> bool:
    """Studio photos whose shoes touch the bottom edge: shrink the frame and extend the seamless backdrop /
    floor (backdrop colour from the bottom corners) so the feet sit at `target` of the height; the person is not re-generated."""
    target = target or _t("bottom_target", 0.93)
    if feet_bottom <= target or feet_bottom > 1.05:
        return False
    try:
        import cv2
        img = cv2.imread(str(path))
        h, w = img.shape[:2]
        k = target / feet_bottom
        nw, nh = int(round(w * k)), int(round(h * k))
        small = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
        import numpy as np
        left = (w - nw) // 2
        out = cv2.copyMakeBorder(small, 0, 0, left, w - nw - left, cv2.BORDER_REPLICATE)  # side columns: pure backdrop
        if h - nh > 0:
            # the new floor strip: never replicate the bottom row (it contains the shoes) — blend the backdrop
            # colours of the bottom-left and bottom-right corners across the width, plus a little film grain
            strip = out[-8:]
            cl = strip[:, : max(4, w // 20)].reshape(-1, 3).mean(0)
            cr = strip[:, -max(4, w // 20):].reshape(-1, 3).mean(0)
            t = np.linspace(0, 1, w)[None, :, None]
            row = (cl[None, None, :] * (1 - t) + cr[None, None, :] * t)
            pad = np.repeat(row, h - nh, axis=0) + np.random.default_rng(0).normal(0, 1.2, (h - nh, w, 3))
            out = np.concatenate([out, np.clip(pad, 0, 255).astype(out.dtype)], axis=0)
        cv2.imwrite(str(path), out)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("floor margin fix failed: %s", e)
        return False


def framing_jumps(video: str | Path, threshold: float | None = None, fps: int = 4) -> list[float]:
    """Times where the picture changes far more within one second than a talking person can move:
    hard cuts AND slow dissolves (which ffmpeg's per-frame scene score misses). Measured as the mean
    absolute difference of 64×80 grey thumbnails one second apart (talking / waving ≈ 4–22, a dissolve
    to a new framing ≈ 35–50)."""
    import subprocess
    import numpy as np
    from .media import ff
    threshold = threshold or _t("jump_threshold", 30.0)
    raw = subprocess.run([ff.FFMPEG, "-v", "error", "-i", str(video), "-vf", f"fps={fps},scale=64:80,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 80, 64).astype(np.float32)
    if len(fr) <= fps:
        return []
    d = np.abs(fr[fps:] - fr[:-fps]).mean(axis=(1, 2))
    out: list[float] = []
    for i in np.where(d > threshold)[0]:
        t = round(float(i + fps / 2) / fps, 2)
        if not out or t - out[-1] > 1.0:
            out.append(t)
    return out
