"""Contract tests — run without GPU: MIDEA_MODE=mock pytest -q tests"""
import os
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault("MIDEA_MODE", "mock")

from midea import qa  # noqa: E402
from midea.cost import estimate_plan  # noqa: E402
from midea.media import ff  # noqa: E402
from midea.pipelines import load_defs, route  # noqa: E402
from midea.schemas import ScenePlan  # noqa: E402
from midea.tools import registry  # noqa: E402
from midea.tools import audio as au  # noqa: E402
from midea.tools import subtitles as sub  # noqa: E402
from midea.tools import video as vt  # noqa: E402


def test_registry_has_100_plus_tools():
    tools = registry.discover()
    assert len(tools) >= 100
    assert {"video", "audio", "subtitle", "motion", "generate", "stock", "analysis", "reference"} <= {t.category for t in tools.values()}


def test_twelve_pipelines_and_gates():
    defs = load_defs()
    assert len(defs) == 12
    for name, d in defs.items():
        assert set(d["gates"]) <= set(d["stages"]), name
        assert d["stages"][-1] == "publish" and "qa" in d["stages"], name


@pytest.mark.parametrize("brief,expected", [
    ({"prompt": "解釋神經網路"}, "animated-explainer"),
    ({"prompt": "二戰歷史", "real_only": True}, "archival-history"),
    ({"prompt": "x", "reference_url": "https://youtube.com/shorts/a"}, "reference-remix"),
    ({"prompt": "新手機 3D 產品展示"}, "product-3d"),
])
def test_router(brief, expected):
    assert route(brief) == expected


def test_subtitle_split_and_limits():
    cues = sub.cues_from_spans([{"start": 0, "end": 6, "text": "神經網路是一種模仿大腦的計算方法，它由許多層節點組成。每一層都會學習不同的特徵。"}])
    assert all(len(c["text"]) <= 18 for c in cues)
    assert all(c["end"] - c["start"] >= 0.8 for c in cues)
    assert cues[0]["start"] == 0 and abs(cues[-1]["end"] - 6) < 0.1
    assert not any(c["text"].strip("，。") == "" for c in cues)


def test_subtitle_alignment_snaps_to_words():
    cues = [{"start": 0.0, "end": 1.0, "text": "你好世界"}, {"start": 1.0, "end": 2.0, "text": "再見"}]
    words = [{"start": 0.3, "end": 0.6, "word": "你好"}, {"start": 0.6, "end": 1.1, "word": "世界"},
             {"start": 1.5, "end": 1.9, "word": "再見"}]
    a = sub.align_to_words(cues, words)
    assert a[0]["start"] == 0.3 and a[1]["start"] == 1.5


def test_cost_estimate_counts_h3():
    plan = ScenePlan(scenes=[{"id": "a", "duration_s": 6, "narration": "hi", "visual": {"kind": "h3_t2v", "prompt": "x"}},
                             {"id": "b", "duration_s": 4, "visual": {"kind": "motion", "template": "kinetic_text"}}]).model_dump()
    est = estimate_plan(plan, {"music": True})
    assert est["gpu_minutes"] > 0 and est["total_cost"] >= 0
    assert any(l["kind"] == "h3_t2v" for l in est["lines"])


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    a, b = d / "a.mp4", d / "b.mp4"
    for p, src in ((a, "testsrc2"), (b, "smptebars")):
        ff.run(["-f", "lavfi", "-i", f"{src}=s=640x360:r=24:d=3", "-f", "lavfi", "-i", "sine=f=440:d=3:sample_rate=48000",
                "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", p])
    return d, a, b


def test_xfade_duration(clip):
    d, a, b = clip
    na, nb = d / "na.mp4", d / "nb.mp4"
    vt.normalize(str(a), str(na), 640, 360, 24, 3)
    vt.normalize(str(b), str(nb), 640, 360, 24, 3)
    out = d / "x.mp4"
    vt.xfade_chain([str(na), str(nb)], str(out), [{"type": "dissolve", "duration": 0.5}])
    assert abs(ff.duration(out) - 5.5) < 0.15


def test_loudnorm_hits_target(clip):
    d, a, _ = clip
    out = d / "n.wav"
    au.loudnorm(str(a), str(out), target_lufs=-16)
    assert abs(au.measure_loudness(str(out))["integrated_lufs"] + 16) < 1.0


def test_qa_flags_black_video(tmp_path):
    v = tmp_path / "black.mp4"
    ff.run(["-f", "lavfi", "-i", "color=c=black:s=640x360:r=24:d=6", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", v])
    rep = qa.run_all(str(v), promise={"duration_s": 6, "aspect": "16:9"}, w=640, h=360, fps=24, workdir=tmp_path / "qa")
    checks = {r["check"]: r["status"] for r in rep["results"]}
    assert rep["status"] == "fail"
    assert checks["frames"] == "fail" and checks["black"] == "fail"
