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


def test_motion_params_are_normalized():
    from midea.tools.motion_engine import normalize_params as n
    assert n("neural_net", {"layers": 3, "nodes": [4, 6, 2]})["layers"] == [4, 6, 2]
    assert n("neural_net", {"layers": "deep"})["layers"] == [4, 6, 6, 3]
    lc = n("line_chart", {"points": [[0, 1], [1, 0.5]]})
    assert lc["values"] == [1.0, 0.5] and lc["labels"] == ["0", "1"]
    assert n("timeline", {"events": ["a", "b"]})["events"][1] == {"date": "2", "label": "b"}


def test_h3_prompt_drops_text_inviting_style():
    from midea.pipelines.runner import _h3_prompt
    p = _h3_prompt("macro shot of neurons, no text", "slow dolly-in", "slate palette, kinetic typography, clean burned subtitles")
    assert "typography" not in p and "subtitles" not in p and "slate palette" in p and "dolly" in p


# ---------------------------------------------------------------- virtual actors
@pytest.fixture()
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("MIDEA_WORKSPACE", str(tmp_path / "ws"))
    return tmp_path / "ws"


def test_actor_create_mentions_and_prompt(ws):
    from midea import actors as AC
    a = AC.create(AC.draft("30歲台灣女記者，幹練短髮"))
    b = AC.create({**AC.draft("40歲男廚師"), "handle": "chef_wang", "name": "王大廚"})
    assert a.handle and b.handle == "chef_wang"
    assert AC.mentions(f"讓 @{a.handle} 採訪 @王大廚走進廚房") == [a.id, b.id]
    assert AC.mentions("@nobody here") == []
    p = AC.portrait_prompt(a, "full_body")
    assert "year-old" in p and "full-body" in p and a.name not in p
    dup = AC.create({**AC.draft("x"), "handle": a.handle})
    assert dup.handle != a.handle                      # handles stay unique


def test_actor_generation_and_filmography(ws):
    from midea import actors as AC
    from midea.pipelines.runner import Runner, cast_prompt
    from midea.project import Project
    a = AC.create(AC.draft("28歲女生，咖啡師"))
    AC.generate_portraits(a.id)
    AC.generate_voice(a.id)
    a = AC.load(a.id)
    assert {p.view for p in a.portraits} == set(AC.DEFAULT_VIEWS)
    assert (AC.adir(a.id) / a.voice.sample).exists() and len(AC.ref_images(a)) == 2
    prompt, refs = cast_prompt(f"@{a.handle} pours latte art, close-up", [a])
    assert "<Picture 1>" in prompt and "@" not in prompt and len(refs) == 2
    assert a.name not in prompt and a.name_en not in prompt          # names would be painted onto signage
    p = Project.create({"prompt": f"@{a.handle} 介紹一杯好咖啡", "duration_s": 20, "music": False}, "cinematic")
    r = Runner(p, auto_approve=True)
    assert r.brief["actors"] == [a.id]
    for st in ("proposal", "script", "scene_plan"):
        r._run_stage(st)
    plan = p.stage_data("scene_plan")
    on = [s for s in plan["scenes"] if a.id in s.get("actors", [])]
    assert on and all(s["visual"]["kind"] == "h3_r2v" for s in on)
    films = AC.filmography(a.id)
    assert films and films[0]["project"] == p.id and films[0]["role"] == "主演"


def test_actor_upload_requires_consent(ws, tmp_path):
    from midea import actors as AC
    from midea.media import ff
    a = AC.create(AC.draft("真人授權演員"))
    img = tmp_path / "face.png"
    ff.run(["-f", "lavfi", "-i", "color=c=gray:s=256x256:d=1", "-frames:v", "1", img])
    with pytest.raises(PermissionError):
        AC.add_upload(a.id, "portrait", img, consent=False)
    a = AC.add_upload(a.id, "portrait", img, consent=True, note="授權書 #42")
    assert a.consent.real_person and a.consent.attested and "portrait" in a.consent.scope
