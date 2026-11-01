"""Cost model for local GPU work: GPU-seconds → kWh → money (plus any paid API lines).

Estimates are shown on the board before the assets gate; actuals are reconciled
from the GPU scheduler's lease timings.
"""
from __future__ import annotations

from .config import settings

# Rough wall-clock seconds on one 48 GB card (scaled ×1.8 for 24 GB with offload).
EST = {
    "h3_t2v": lambda s: 90 + 40 * s, "h3_i2v": lambda s: 90 + 40 * s, "h3_r2v": lambda s: 100 + 45 * s,
    "tts": lambda s: 2 + 0.5 * s, "music": lambda s: 10 + 0.15 * s, "sfx": lambda s: 15.0,
    "foley": lambda s: 40 + 8 * s, "llm": lambda s: 30.0, "motion": lambda s: 3.0 * s,
    "stock": lambda s: 6.0, "encode": lambda s: 0.6 * s,
}
GPU_TOOLS = {"h3_t2v", "h3_i2v", "h3_r2v", "tts", "music", "sfx", "foley", "llm"}


def _scale() -> float:
    return 1.8 if float(settings().get("gpu.vram_gb", 48)) < 40 else 1.0


def money_for_gpu_seconds(sec: float) -> float:
    kw = float(settings().get("gpu.power_watts", 450)) / 1000
    return round(sec / 3600 * kw * float(settings().get("gpu.electricity_per_kwh", 4.5)), 4)


def estimate_line(kind: str, seconds: float, label: str = "") -> dict:
    wall = EST.get(kind, lambda s: 5.0)(float(seconds)) * (_scale() if kind in GPU_TOOLS else 1.0)
    gpu = wall if kind in GPU_TOOLS else 0.0
    return {"kind": kind, "label": label, "seconds": float(seconds), "wall_s": round(wall, 1), "gpu_s": round(gpu, 1),
            "cost": money_for_gpu_seconds(gpu), "currency": settings().get("gpu.currency", "TWD")}


def estimate_plan(plan: dict, brief: dict) -> dict:
    lines = []
    for sc in plan.get("scenes", []):
        v = sc.get("visual", {})
        kind = v.get("kind", "")
        d = float(sc.get("duration_s", 5))
        if kind.startswith("h3"):
            lines.append(estimate_line(kind, d, sc["id"]))
        elif kind in ("motion", "title_card"):
            lines.append(estimate_line("motion", d, sc["id"]))
        elif kind.startswith("stock"):
            lines.append(estimate_line("stock", d, sc["id"]))
        if sc.get("narration"):
            lines.append(estimate_line("tts", d, f"{sc['id']} voice"))
        for _ in sc.get("sfx", []):
            lines.append(estimate_line("sfx", 2, f"{sc['id']} sfx"))
        if sc.get("foley"):
            lines.append(estimate_line("foley", d, f"{sc['id']} foley"))
    total_d = sum(float(s.get("duration_s", 0)) for s in plan.get("scenes", []))
    if brief.get("music", True):
        lines.append(estimate_line("music", total_d, "music bed"))
    lines.append(estimate_line("encode", total_d, "edit + encode + QA"))
    return summarize(lines)


def summarize(lines: list[dict]) -> dict:
    return {"lines": lines, "total_cost": round(sum(l["cost"] for l in lines), 3),
            "gpu_minutes": round(sum(l["gpu_s"] for l in lines) / 60, 1),
            "wall_minutes": round(sum(l["wall_s"] for l in lines) / 60, 1),
            "currency": settings().get("gpu.currency", "TWD")}


def check_budget(estimate_total: float, spent: float = 0.0) -> dict:
    mode = settings().get("budget.mode", "warn")
    cap = float(settings().get("budget.total_cap", 300))
    over = spent + estimate_total > cap
    return {"mode": mode, "cap": cap, "over": over, "blocked": over and mode == "cap",
            "message": f"預估 {spent + estimate_total:.2f} / 上限 {cap:.2f}" + (" — 超出預算" if over else "")}
