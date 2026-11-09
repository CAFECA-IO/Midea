"""每日報導: template choice, fact check, figures, the mock daily run, feedback, sequels and the weekly video pick."""
import json
import random
from collections import Counter
from datetime import date, datetime

import pytest

from tests.test_site import H, _user, site  # noqa: F401  (fixture)

DAY = date(2026, 11, 9)          # a Monday


def test_choose_template_rules():
    from midea.site.news import choose_template
    rng = random.Random(1)
    sc = {"brief": 0.9, "howto": 0.6, "ranking": 0.2}
    picks = Counter(choose_template(sc, "news", Counter(), {}, rng) for _ in range(400))
    assert set(picks) == {"brief", "howto"}                       # 只從 ≥ 0.5 的模板抽
    assert picks["brief"] > picks["howto"]                        # 分數越高越容易抽中
    assert choose_template(sc, "news", Counter({"brief": 2}), {}, rng) == "howto"          # 同模板一天最多 2 篇
    assert choose_template(sc, "news", Counter(), {"news": "brief"}, rng) == "howto"       # 同類型不連續兩天
    assert choose_template({"brief": 0.9}, "news", Counter(), {"news": "brief"}, rng) == "brief"   # 沒有別的選擇時放寬
    assert choose_template({}, "paper", Counter(), {}, rng) == "paper"


def test_fact_check_numbers_must_come_from_source():
    from midea.site.news import unverified_numbers
    spec = {"type": "bars", "title": "11/5 單日跌幅", "rows": [{"label": "SOX", "value": -12, "display": "−12%"},
                                                         {"label": "Nasdaq 100", "value": 6.4, "display": "−6.4%"}]}
    assert unverified_numbers(spec, "The SOX dropped 12%, the Nasdaq 100 fell 6.4% on 11/5") == []
    spec["rows"].append({"label": "Nvidia", "value": 77, "display": "−77%"})
    assert unverified_numbers(spec, "The SOX dropped 12%, the Nasdaq 100 fell 6.4% on 11/5") == ["77", "77"]
    assert unverified_numbers({"type": "bars", "rows": [{"label": "rea", "value": 201065}]}, "rea +201,065") == []


def test_mixed_units_and_spacing():
    from midea.site.news import mixed_units, spaced
    bad = {"type": "bars", "unit": "依各行標示", "rows": [{"label": "AI代理同時作業（個）", "value": 5000}, {"label": "每月提交量（億次）", "value": 14}]}
    assert mixed_units(bad)
    assert mixed_units({"type": "bars", "unit": "數值", "rows": [{"label": "速度提升", "value": 50, "display": "50%"}, {"label": "秒數", "value": 6, "display": "6 秒"}]})
    assert not mixed_units({"type": "bars", "unit": "%", "rows": [{"label": "SOX", "value": -12, "display": "−12%"}, {"label": "Nvidia", "value": -9, "display": "逾 −9%"}]})
    from midea.site.news_fixtures import ARTICLES
    assert not any(mixed_units(a["figure"]) for a in ARTICLES.values())
    assert spaced("OpenAI傳以1.25兆美元估值") == "OpenAI 傳以 1.25 兆美元估值"
    assert spaced("https://x.com/中文") == "https://x.com/中文"


def test_pick_keeps_one_repo_and_one_paper(monkeypatch):
    from midea.site import news
    monkeypatch.setattr(news, "is_mock", lambda: False)
    cands = [{"kind": "news", "title": f"n{i}"} for i in range(6)] + [{"kind": "repo", "title": "r"}, {"kind": "paper", "title": "p"}]

    class L:
        def json(self, *a, **k):
            return {"picks": [{"index": i, "fit": {"brief": 0.9}} for i in range(5)]}
    monkeypatch.setattr("midea.providers.llm.llm", lambda: L())
    room = news.Newsroom.__new__(news.Newsroom)
    kinds = [cands[p["index"]]["kind"] for p in room.pick(cands, 5)]
    assert len(kinds) == 5 and "repo" in kinds and "paper" in kinds


def test_every_fixture_figure_renders():
    from midea.site import news_svg
    from midea.site.news_fixtures import ARTICLES
    for t, art in ARTICLES.items():
        out = news_svg.render(art["figure"])
        assert out["wide"].startswith("<svg") and out["narrow"].startswith("<svg"), t
        assert 'viewBox="0 0 640' in out["wide"] and 'viewBox="0 0 340' in out["narrow"]
        assert "<script" not in out["wide"] and "#" not in out["wide"].split("viewBox")[0]      # 只用 token，不寫死色碼
        assert news_svg.mini(art["figure"]).startswith("<svg"), t
    assert news_svg.render({"type": "bars", "rows": [{"label": "<b>x</b>", "value": 1}]})["wide"].count("<b>") == 0   # 文字有跳脫
    assert news_svg.render({"type": "nope"}) == {"wide": "", "narrow": ""}


def test_daily_run_publishes_five_and_is_idempotent(site):
    c, m = site
    n = m.st().news
    out = n.run_daily(DAY)
    assert len(out["articles"]) == 5 and len(set(out["templates"])) == 5
    assert n.run_daily(DAY) == {"skipped": True}
    today = c.get("/api/public/v1/news/today").json()
    assert today["day"] == "2026-11-09" and len(today["articles"]) == 5
    assert all(a["mini"].startswith("<svg") for a in today["articles"])
    a = c.get(f"/api/public/v1/news/{today['articles'][0]['slug']}").json()
    assert a["figure"]["wide"] and a["sources"][0]["url"].startswith("https://") and len(a["related"]) == 4
    nxt = n.run_daily(date(2026, 11, 10))                       # 已寫過的來源不再寫
    assert set(nxt["templates"]) == {"timeline", "versus"}
    assert c.get("/news").status_code == 200 and c.get(f"/news/{a['slug']}").status_code == 200


def test_reactions_quiz_questions_and_hiding(site):
    c, m = site
    n = m.st().news
    n.run_daily(DAY)
    slug = n.today()["articles"][0]["slug"]
    base = f"/api/public/v1/news/{slug}"
    r = c.post(base + "/react", json={"kind": "sequel", "on": True}, headers=H).json()          # 不用登入
    assert r["counts"]["sequel"] == 1 and r["mine"] == ["sequel"]
    c.post(base + "/react", json={"kind": "helpful", "on": True}, headers=H)
    assert set(c.get(base).json()["mine"]) == {"sequel", "helpful"}                              # 可以同時按幾種
    assert c.post(base + "/react", json={"kind": "sequel", "on": False}, headers=H).json()["counts"]["sequel"] == 0
    assert c.post(base + "/react", json={"kind": "bogus"}, headers=H).status_code == 400
    q = c.post(base + "/quiz", json={"choice": 1}, headers=H).json()
    assert q["mine"] == 1 and q["answer"] == 1 and q["right"] == 100
    assert c.post(base + "/questions", json={"text": "為什麼是半導體跌最多？"}, headers=H).status_code == 401
    u = _user(c, "reader", nick="讀者甲")
    j = u.post(base + "/questions", json={"text": "為什麼是半導體跌最多？", "para": 2, "quote": "費城半導體指數單日下跌 12%"}, headers=H).json()
    assert j["questions"][0]["quote"].startswith("費城") and j["left"] == 4
    qid = j["questions"][0]["id"]
    assert _user(c, "fan", nick="讀者乙").post(f"/api/public/v1/news/questions/{qid}/support", headers=H).json()["supporters"] == 1
    assert u.post(base + "/questions", json={"text": "加 line 0912-345-678"}, headers=H).status_code == 400
    for i in range(3):
        _user(c, f"r{i}").post("/api/public/v1/reports", json={"kind": "article_q", "id": qid, "reason": "其他"}, headers=H)
    assert c.get(base).json()["questions"] == []                                                 # 3 人檢舉 → 隱藏
    n.set_status(slug, "hidden")
    assert c.get(base).status_code == 404 and len(c.get("/api/public/v1/news/today").json()["articles"]) == 4


def test_feedback_score_caps_anonymous(site):
    c, m = site
    s = m.st()
    n = s.news
    n.run_daily(DAY)
    aid = s.store.one("SELECT id FROM article WHERE rank=0")["id"]
    for i in range(10):
        n.react(aid, s.store.device_viewer(f"anon-device-{i:02d}-xxxxxxxx"), "video", True, anon=True)
    assert n.feedback_score(aid)["score"] == 0                    # 只有匿名 → 不計分
    for i in range(7):
        v = s.store.sign_in(f"0x{i:040x}", handle=f"s{i}", kyc_level=1, device=None)[0]
        n.react(aid, v, "video", True, anon=False)
    fb = n.feedback_score(aid)
    assert fb["video"] == 17 and fb["score"] == 3 * (7 + 3)      # 匿名最多佔 30%：7 位登入 → 最多算 3 位匿名


def test_sequel_is_written_and_answers_questions(site, monkeypatch):
    c, m = site
    from midea import config
    monkeypatch.setitem(config.settings().raw.setdefault("site", {}).setdefault("news", {}), "sequel_threshold", 2)
    s = m.st()
    n = s.news
    n.run_daily(DAY)
    a = s.store.one("SELECT * FROM article WHERE rank=1")
    for i in range(2):
        n.react(a["id"], s.store.device_viewer(f"seq-device-{i:02d}-xxxxxxxx"), "sequel", True, anon=True)
    u = _user(c, "curious", nick="好奇")
    qid = u.post(f"/api/public/v1/news/{a['slug']}/questions", json={"text": "rea 實際怎麼用？"}, headers=H).json()["id"]
    monkeypatch.setattr("midea.site.news.now_local", lambda ts=None: datetime(2026, 11, 10, 7, 0))
    out = n.run_daily(date(2026, 11, 10))
    seq = s.store.one("SELECT * FROM article WHERE sequel_of=?", (a["id"],))
    assert seq and seq["day"] == "2026-11-10" and seq["slug"] in out["articles"]
    assert s.store.one("SELECT answered_in FROM article_question WHERE id=?", (qid,))["answered_in"] == seq["id"]
    assert n.sequel_requests() == []                               # 已寫過續作不再要求
    d = c.get(f"/api/public/v1/news/{a['slug']}").json()
    assert d["sequels"][0]["slug"] == seq["slug"]


def test_weekly_picks_editor_and_audience(site):
    c, m = site
    s = m.st()
    n = s.news
    n.run_daily(date(2026, 11, 3))
    n.run_daily(date(2026, 11, 4))
    made = []
    n.make_video_hook = lambda brief, who: (made.append((who, brief)), f"proj-{who}")[1]
    top = s.store.one("SELECT * FROM article WHERE template='brief'")
    for i in range(3):
        v = s.store.sign_in(f"0x{i + 100:040x}", handle=f"v{i}", kyc_level=1, device=None)[0]
        n.react(top["id"], v, "video", True, anon=False)
    out = n.run_weekly(DAY)
    picks = {p["pick"]: p for p in out["picks"]}
    assert picks["audience"]["slug"] == top["slug"] and picks["editor"]["slug"] != top["slug"]
    assert picks["editor"]["title"] and "3 位讀者" in picks["audience"]["note"]
    assert {w for w, _ in made} == {"editor", "audience"}
    brief = dict(made)["editor"]
    assert "@yen_lin" in brief["prompt"] and brief["source_article"] == picks["editor"]["slug"]
    assert s.store.one("SELECT video_project FROM article WHERE slug=?", (top["slug"],))["video_project"] == "proj-audience"
    assert n.run_weekly(DAY) == {"skipped": True}
    vid = c.get(f"/api/public/v1/news/{top['slug']}").json()["video"]
    assert vid["label"] == "觀眾選" and vid["status"] == "producing"


def test_tick_schedule(site, monkeypatch):
    c, m = site
    n = m.st().news
    calls = []
    monkeypatch.setattr(n, "run_daily", lambda d=None, **k: (calls.append(("daily", d)), n._start("daily", d.isoformat())))
    monkeypatch.setattr(n, "run_weekly", lambda d=None, **k: (calls.append(("weekly", d)), n._start("weekly", "2026-11-09")))
    assert n.tick(datetime(2026, 11, 9, 5, 59)) is None
    assert n.tick(datetime(2026, 11, 9, 6, 0)) == "daily"
    assert n.tick(datetime(2026, 11, 9, 6, 10)) is None             # 06:30 前不做影片
    assert n.tick(datetime(2026, 11, 9, 6, 31)) == "weekly"
    assert n.tick(datetime(2026, 11, 9, 7, 0)) is None
    assert n.tick(datetime(2026, 11, 10, 6, 1)) == "daily"          # 週二只有每日報導
    assert [k for k, _ in calls] == ["daily", "weekly", "daily"]


def test_depth_rules_code_excerpts_and_key_files():
    from midea.site.news import _verbatim, validate
    from midea.site.news_research import Pack, _key_files
    thin = {"title": "t", "dek": "d", "points": ["a"], "paragraphs": ["b"], "sections": [{"heading": "h", "paragraphs": ["短"]}]}
    assert any("3 analysis sections" in x for x in validate(thin, "brief"))
    deep = dict(thin, sections=[{"heading": f"h{i}", "paragraphs": ["字" * 600]} for i in range(4)])
    assert validate(deep, "brief") == []
    src = "[3] repo/main.py\ndef run(x):\n    return loop(x)  # 每輪結束就退出\n"
    assert _verbatim("def run(x):\n  return loop(x)  # 每輪結束就退出", src) and not _verbatim("def run(y): pass", src)
    tree = [{"type": "blob", "path": "src/agent.py", "size": 9000}, {"type": "blob", "path": "tests/test_agent.py", "size": 9000},
            {"type": "blob", "path": "node_modules/x/index.js", "size": 9000}, {"type": "blob", "path": "src/util/helpers.py", "size": 3000}]
    assert _key_files(tree, "Python")[0] == "src/agent.py" and "tests/test_agent.py" not in _key_files(tree, "Python")
    p = Pack(budget=700)
    p.add("A", "x" * 300, "https://a")
    p.add("B", "y" * 300, "https://b")
    p.add("C", "z" * 300, "https://c")                     # over budget → left out
    assert [s["n"] for s in p.sources] == [1, 2] and "[2] B <https://b>" in p.text()
