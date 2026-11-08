"""Public site (midea.cafeca.io) — phase 1 of the audience-feedback plan. Runs without GPU or network."""
import importlib
import json
import os
import subprocess
import time
from datetime import timedelta
from pathlib import Path

import pytest

os.environ.setdefault("MIDEA_MODE", "mock")
H = {"X-Midea": "1"}


def _video(path: Path, seconds: float = 2.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s=64x36:d={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)


@pytest.fixture()
def site(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    for i, (pid, title) in enumerate([("20261101-000000-aaaaaa", "第一部"), ("20261102-000000-bbbbbb", "第二部"),
                                      ("20261103-000000-cccccc", "第三部")]):
        d = ws / pid
        _video(d / "final" / f"{title}.mp4")
        (d / "final" / f"{title}.jpg").write_bytes(b"\xff\xd8\xff")
        (d / "final" / "README.md").write_text(f"# {title}\n\n說明 {i}\n\n- Pipeline: cinematic\n", encoding="utf-8")
        (d / "stages").mkdir()
        (d / "stages" / "publish.json").write_text("{}")
        (d / "project.json").write_text(json.dumps({
            "id": pid, "created": time.time() - i * 3600, "pipeline": "cinematic", "status": "done",
            "brief": {"prompt": title, "actors": []},
            "deliverables": {"items": [{"video": f"final/{title}.mp4", "thumbnail": f"final/{title}.jpg"}]}}), encoding="utf-8")
    # an unpublished project must never show up
    (ws / "20261104-000000-dddddd").mkdir()
    (ws / "20261104-000000-dddddd" / "project.json").write_text(json.dumps({"id": "x", "status": "running", "brief": {}}))
    monkeypatch.setenv("MIDEA_WORKSPACE", str(ws))
    monkeypatch.setenv("MIDEA_SITE_DATA", str(tmp_path / "site"))
    monkeypatch.setenv("MIDEA_SITE_DEV_LOGIN", "1")
    monkeypatch.setenv("MIDEA_SITE_ORIGIN", "http://testserver")
    from midea import config
    config.load()
    from midea.site import catalog as cat_mod
    cat_mod._catalog = None
    from midea.site import app as app_mod
    importlib.reload(app_mod)
    from fastapi.testclient import TestClient
    with TestClient(app_mod.app) as c:
        yield c, app_mod
    from midea.web import app as board
    board.AUTH.update(mode="basic", resolve=None)      # the standalone board keeps HTTP Basic


def _login(c, handle="alice", kyc=None):
    r = c.post("/api/public/v1/auth/dev", json={"handle": handle, "kyc_level": kyc}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["me"]


def test_catalog_lists_only_published_final_files(site):
    c, m = site
    vids = m.st().cat.refresh(force=True).videos
    assert {v.title for v in vids.values()} == {"第一部", "第二部", "第三部"}
    assert all(round(v.duration) == 2 for v in vids.values())
    vid = next(iter(vids))
    assert c.get(f"/media/v/{vid}.mp4").status_code == 200
    assert c.get("/media/v/../../project.mp4").status_code == 404
    assert c.get("/media/v/deadbeef0000.mp4").status_code == 404
    home = c.get("/api/public/v1/home").json()
    assert home["live"]["item"] and home["live"]["slot"]["range"]


def test_state_changes_need_header_and_login(site):
    c, m = site
    vid = next(iter(m.st().cat.videos))
    assert c.post(f"/api/public/v1/videos/{vid}/reaction", json={"kind": "like"}).status_code == 403
    assert c.post(f"/api/public/v1/videos/{vid}/reaction", json={"kind": "like"}, headers=H).status_code == 200   # anonymous is fine
    assert c.post(f"/api/public/v1/videos/{vid}/favorite", headers=H).status_code == 401                        # favorites need CAFECA
    _login(c)
    assert c.post(f"/api/public/v1/videos/{vid}/favorite", headers=H).json() == {"favorite": True}


def test_login_merges_anonymous_reactions(site):
    c, m = site
    vid = next(iter(m.st().cat.videos))
    c.post(f"/api/public/v1/videos/{vid}/reaction", json={"kind": "more"}, headers=H)
    me = _login(c, "bob", 2)
    assert me["kyc_level"] == 2
    assert c.get(f"/api/public/v1/videos/{vid}").json()["reaction"] == "more"
    rows = m.st().store.q("SELECT * FROM reaction")
    assert len(rows) == 1 and rows[0]["anon"] == 0


def test_anonymous_share_capped_and_bursts_ignored(site):
    c, m = site
    from midea.site.programming import video_scores
    s = m.st()
    a, b = list(s.cat.videos)[:2]
    for i in range(40):                                   # 40 anonymous browsers, same network source
        dv = s.store.device_viewer(f"device-{i:02d}-xxxxxxxx")
        s.store.set_reaction(dv, a, "more", None, anon=True, src="same-ip")
    assert s.store.one("SELECT COUNT(*) n FROM reaction WHERE counted=0")["n"] == 10   # over 30 in 10 min → not scored
    sc = video_scores(s.store, s.cat)
    assert sc[a] == 0                                      # no views, no signed-in reactions → anonymous share is capped to 0
    s.store.record_view(s.store.device_viewer("viewer-x-aaaaaaaaaa"), a, 2, True, "2026-11-08")
    sc = video_scores(s.store, s.cat)
    assert sc[a] == pytest.approx(1 + 3 / 7)               # 30 % of the total at most
    assert sc[b] == 0


def test_completed_views_once_per_day(site):
    c, m = site
    vid = next(iter(m.st().cat.videos))
    for _ in range(3):
        assert c.post(f"/api/public/v1/videos/{vid}/view", json={"seconds": 2, "completed": True}, headers=H).json()["completed"]
    assert not c.post(f"/api/public/v1/videos/{vid}/view", json={"seconds": 0.5, "completed": True}, headers=H).json()["completed"]
    assert m.st().store.completed_views(0) == {vid: 1}


def test_poll_votes_without_kyc_and_tallies_per_level(site):
    c, m = site
    poll = m.st().store.latest_poll()
    assert poll, "next week's schedule opens the 「觀眾決定」 poll"
    opts = [o["id"] for o in json.loads(poll["options"])]
    url = f"/api/public/v1/polls/{poll['id']}/vote"
    assert c.post(url, json={"option": opts[0]}, headers=H).status_code == 401
    for i, (kyc, opt) in enumerate([(None, 0), (0, 0), (2, 1), (3, 0)]):
        c.cookies.clear()
        _login(c, f"user{i}", kyc)
        r = c.post(url, json={"option": opts[opt]}, headers=H)
        assert r.status_code == 200, r.text
    p = r.json()["poll"]
    assert p["votes"] == 4 and p["mine"] == opts[0]
    assert p["by_kyc"] == {"unknown": {opts[0]: 1}, "0": {opts[0]: 1}, "2": {opts[1]: 1}, "3+": {opts[0]: 1}}
    # closing fills the slot with the winner and the fixed influence wording
    s = m.st()
    s.store.db.execute("UPDATE poll SET closes=? WHERE id=?", (time.time() - 1, poll["id"]))
    s.prog.close_due_polls()
    from datetime import date
    plan = s.prog.week(date.fromisoformat(poll["id"].split("poll-")[1]))
    slot = next(x for x in plan["slots"] if x["id"] == poll["slot"])
    assert slot["program"] == opts[0] and slot["influence"] == "poll" and "3 票" in slot["reason"]
    assert c.post(url, json={"option": opts[1]}, headers=H).status_code == 409


def test_slot_end_votes_rerun_next_week(site):
    c, m = site
    from midea.site.programming import now_local, week_start
    s = m.st()
    mon = week_start(now_local().date())
    plan = s.prog.week(mon)
    prog = next(x for x in plan["slots"] if x["prime"] and x["program"] not in ("rotation", "audience"))
    for i, want in enumerate([True, True, False]):
        s.store.slot_vote(prog["id"], prog["program"], 100 + i, want, None)
    nxt = s.prog.plan_week(mon + timedelta(days=7), with_poll=False)
    rerun = [x for x in nxt["slots"] if x.get("influence") == "rerun"]
    assert rerun and rerun[0]["program"] == prog["program"] and "3 位觀眾中有 2 位" in rerun[0]["reason"]


def test_live_reactions_rate_limit_viewers_and_highlights(site):
    c, m = site
    s = m.st()
    room = s.live
    assert room.press("a", "like", "slot", "v1", 12.0)
    assert not room.press("a", "funny", "slot", "v1", 12.5)          # 每人每 2 秒 1 次
    for i in range(30):
        room.press(f"p{i}", "moving", "slot", "v1", 13.0)
    sec = room.take_second()
    assert sum(sec["counts"].values()) == 31 and sum(sec["show"].values()) <= 21
    room.flush()
    assert s.store.live_buckets("v1") == {2: 31}
    from midea.site.live import LiveRoom
    fresh = LiveRoom(s.store)
    for i in range(9):
        fresh.heartbeat(f"w{i}")
    assert fresh.viewers() is None                                   # under 10: no number
    fresh.heartbeat("w9")
    fresh._viewers_at = 0
    assert fresh.viewers() == 10
    with pytest.raises(ValueError):
        room.press("z", "angry", "slot", "v1", 0)
    vid = next(iter(s.cat.videos))
    s.store.add_live_buckets([("slot", vid, 0, "like", 9)])
    hl = s.prog.highlights(vid)
    assert hl and hl[0]["label"] == "觀眾最有反應的片段" and hl[0]["start"] == 0


def test_cafeca_eip712_hash_matches_reference():
    eth = pytest.importorskip("eth_account.messages")
    from eth_utils import keccak  # noqa: F401
    from midea.site.cafeca import signin_hash
    acct = "0x" + "ab" * 20
    msg = {"domain": "https://midea.cafeca.io", "uri": "https://midea.cafeca.io/", "nonce": "abcdefgh12345678",
           "issuedAt": 1794120000, "expiresAt": 1794120300, "statement": "登入 Midea", "claims": "handle,kyc_level", "channel": ""}
    ref = eth.encode_typed_data(full_message={
        "types": {"EIP712Domain": [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                                   {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"}],
                  "SignIn": [{"name": n, "type": t} for n, t in [("domain", "string"), ("uri", "string"), ("nonce", "string"),
                             ("issuedAt", "uint256"), ("expiresAt", "uint256"), ("statement", "string"), ("claims", "string"), ("channel", "string")]]},
        "primaryType": "SignIn", "domain": {"name": "CAFECA Sign-In", "version": "1", "chainId": 8018, "verifyingContract": acct},
        "message": msg})
    from eth_utils import keccak as k
    assert signin_hash(msg, 8018, acct) == k(b"\x19" + ref.version + ref.header + ref.body)


def test_cafeca_verify_checks(monkeypatch):
    from midea.site import cafeca
    monkeypatch.setattr(cafeca, "configuration", lambda: {"chain": {"id": 8018, "rpc": "x"}, "contracts": {"identityRegistry": "0x" + "11" * 20}})
    monkeypatch.setattr(cafeca, "is_valid_signature", lambda rpc, a, hsh, sig: sig == "0xgood")
    monkeypatch.setattr(cafeca, "identity_status", lambda rpc, reg, a: {"status": "active", "effectiveLevel": 2})
    monkeypatch.setattr(cafeca, "lookup_handle", lambda a: "alice")
    now = time.time()
    used = set()

    def nonce_ok(n):
        if n in used:
            return False
        used.add(n)
        return True

    def res(**kw):
        m = {"domain": "https://midea.cafeca.io", "uri": "https://midea.cafeca.io/", "nonce": kw.pop("nonce", "n1234567"),
             "issuedAt": int(now), "expiresAt": int(now) + 300, "statement": "", "claims": "handle,kyc_level", "channel": ""}
        m.update(kw.pop("m", {}))
        return {"type": "cafeca:auth", "v": 1, "account": "0x" + "AB" * 20, "chainId": 8018, "message": m,
                "signature": kw.pop("sig", "0xgood"), **kw}

    ok = cafeca.verify(res(), origin="https://midea.cafeca.io", nonce_ok=nonce_ok)
    assert ok == {"account": "0x" + "ab" * 20, "handle": "alice", "kyc_level": 2, "claims": ["handle", "kyc_level"]}
    bad = [(res(nonce="n1234567"), "nonce"),                                   # replay
           (res(nonce="n2", m={"domain": "https://evil.example"}), "網域"),
           (res(nonce="n3", chainId=1), "鏈 ID"),
           (res(nonce="n4", m={"expiresAt": int(now) - 1}), "過期"),
           (res(nonce="n5", sig="0xbad"), "簽章"),
           ({"type": "other"}, "不是")]
    for r, why in bad:
        with pytest.raises(cafeca.SignInError, match=why):
            cafeca.verify(r, origin="https://midea.cafeca.io", nonce_ok=nonce_ok)
    # claims the user did not approve are not used
    r = res(nonce="n6", m={"claims": ""})
    assert cafeca.verify(r, origin="https://midea.cafeca.io", nonce_ok=nonce_ok)["kyc_level"] is None


# ------------------------------------------------------------------------------------------------ phase 2 + studio
def _user(c, handle, kyc=1, nick=None):
    from fastapi.testclient import TestClient
    u = TestClient(c.app)
    _login(u, handle, kyc)
    if nick:
        assert u.post("/api/public/v1/me/nickname", json={"nickname": nick}, headers=H).status_code == 200
    return u


def test_chat_rules_rate_and_nickname(site):
    c, m = site
    u = _user(c, "chatter", nick="小魚")
    r = u.post("/api/public/v1/live/chat", json={"text": "晚安"}, headers=H).json()
    assert r["status"] == "shown"
    assert u.post("/api/public/v1/live/chat", json={"text": "再一則"}, headers=H).status_code == 429     # 每 5 秒 1 則
    m.st().com._last_chat.clear()
    r = u.post("/api/public/v1/live/chat", json={"text": "加 line 領優惠 0912-345-678"}, headers=H).json()
    assert r["status"] == "rejected" and r["reason"] in ("個資", "廣告")
    assert u.post("/api/public/v1/live/chat", json={"text": "x" * 101}, headers=H).status_code == 400
    for bad in ("Midea 小編", "官方帳號", "@yuqing", "a", "智障"):
        assert u.post("/api/public/v1/me/nickname", json={"nickname": bad}, headers=H).status_code == 400
    msgs = c.get("/api/public/v1/live/chat").json()["messages"]
    assert [x["text"] for x in msgs] == ["晚安"] and msgs[0]["nickname"] == "小魚"


def test_wishes_merge_threshold_and_weekly_limit(site, monkeypatch):
    c, m = site
    from midea import config
    monkeypatch.setitem(config.settings().raw.setdefault("site", {}), "wish_threshold", 3)
    a, b, d = _user(c, "w1"), _user(c, "w2"), _user(c, "w3")
    assert a.post("/api/public/v1/wishes", json={"kind": "topic", "text": "下雨天的城市"}, headers=H).json()["merged"] is False
    r = b.post("/api/public/v1/wishes", json={"kind": "topic", "text": "雨天的城市街景"}, headers=H).json()
    assert r["merged"] is True                                           # 相近的許願合併成同一張卡
    card = r["card"]
    assert d.post(f"/api/public/v1/wishes/{card}/support", headers=H).json()["supporters"] == 3
    assert m.st().store.one("SELECT * FROM review WHERE kind='wish'")["target"] == str(card)   # 達門檻 → 待核准製作
    for t in ("夜班", "清晨"):
        a.post("/api/public/v1/wishes", json={"kind": "topic", "text": t + "的工作"}, headers=H)
    assert a.post("/api/public/v1/wishes", json={"kind": "topic", "text": "第四個"}, headers=H).status_code == 429
    assert a.post("/api/public/v1/wishes", json={"kind": "topic", "text": "https://spam.example"}, headers=H).status_code in (400, 429)


def test_reports_hide_and_penalties_escalate(site):
    c, m = site
    s = m.st()
    author = _user(c, "author", nick="作者")
    for k in range(3):
        s.com._last_chat.clear()
        author.post("/api/public/v1/live/chat", json={"text": f"訊息 {k}"}, headers=H)
    ids = [r["id"] for r in s.store.q("SELECT id FROM chat ORDER BY id")]
    viewer_id = s.store.one("SELECT viewer FROM chat WHERE id=?", (ids[0],))["viewer"]
    for i, cid in enumerate(ids):
        for j in range(3):
            _user(c, f"rep{i}{j}").post("/api/public/v1/reports", json={"kind": "chat", "id": cid, "reason": "騷擾"}, headers=H)
        assert s.store.one("SELECT status FROM chat WHERE id=?", (cid,))["status"] == "hidden"      # 3 個不同身分 → 隱藏
        rv = s.store.one("SELECT id FROM review WHERE target=?", (f"chat:{cid}",))["id"]
        out = s.com.resolve(rv, "violation", by="admin")
        assert out["penalty"]["level"] == ["warning", "mute", "ban"][i]
    v = s.store.one("SELECT * FROM viewer WHERE id=?", (viewer_id,))
    assert v["banned_until"] > time.time() + 29 * 86400
    assert c.get("/api/public/v1/live/chat").json()["messages"] == []


def test_questions_reply_only_to_asker(site):
    c, m = site
    s = m.st()
    from midea.site.community import Worker
    asker, other = _user(c, "asker", nick="提問者"), _user(c, "other", nick="路人")
    s.com.s.db.execute("INSERT OR IGNORE INTO viewer(kind, account, handle, created) VALUES('cafeca','0x1','x',0)")
    w = Worker(s.com, lambda hd: {"name": "林予晴", "handle": hd})
    s.com.ask(s.store.one("SELECT * FROM viewer WHERE handle='asker'"), "yuqing", "你第一次自己煮的咖啡是什麼味道？")
    w.run_once()      # AI moderation (mock: clean)
    w.run_once()      # text reply
    mine = s.com.questions("yuqing", s.store.one("SELECT id FROM viewer WHERE handle='asker'")["id"])[0]
    theirs = s.com.questions("yuqing", s.store.one("SELECT id FROM viewer WHERE handle='other'")["id"])[0]
    assert mine["reply"] and theirs["reply"] is None                  # 只有提問者看得到
    for _ in range(2):
        s.com.ask(s.store.one("SELECT * FROM viewer WHERE handle='asker'"), "yuqing", "還有一題")
    with pytest.raises(OverflowError):
        s.com.ask(s.store.one("SELECT * FROM viewer WHERE handle='asker'"), "yuqing", "第四題")


def test_studio_isolation_and_guards(site):
    c, m = site
    alice, bob = _user(c, "alice"), _user(c, "bob")
    assert c.get("/studio/", follow_redirects=False).status_code in (302, 307)
    assert alice.get("/studio/api/meta").json()["me"]["admin"] is False
    assert alice.post("/studio/api/projects", json={"prompt": "x", "user_media": ["/etc/passwd"]}, headers=H).status_code == 400
    assert alice.post("/studio/api/ads", json={"lead": "x", "product_url": "http://127.0.0.1:8780/"}, headers=H).status_code == 400
    assert alice.post("/studio/api/projects", json={"prompt": "x"}).status_code == 403                    # X-Midea header
    from midea.project import Project
    p = Project.create({"prompt": "alice 的片"}, "cinematic", owner=alice.get("/studio/api/meta").json()["me"]["account"])
    assert [x["id"] for x in alice.get("/studio/api/projects").json()] == [p.id]
    assert bob.get("/studio/api/projects").json() == []
    assert bob.get(f"/studio/api/projects/{p.id}").status_code == 404
    assert bob.get(f"/studio/files/{p.id}/project.json").status_code == 404
    assert bob.post("/studio/api/services/qwen/stop", headers=H).status_code == 403


def test_creator_work_needs_listing_review(site):
    c, m = site
    s = m.st()
    alice = _user(c, "alice2")
    acct = alice.get("/studio/api/meta").json()["me"]["account"]
    ws = Path(os.environ["MIDEA_WORKSPACE"])
    d = ws / "20261105-000000-eeeeee"
    _video(d / "final" / "創作者.mp4")
    (d / "stages").mkdir(parents=True)
    (d / "stages" / "publish.json").write_text("{}")
    (d / "project.json").write_text(json.dumps({"id": d.name, "owner": acct, "created": time.time(), "pipeline": "cinematic",
        "status": "done", "brief": {"prompt": "創作者"}, "deliverables": {"items": [{"video": "final/創作者.mp4"}]}}), encoding="utf-8")
    from midea.site import studio
    assert studio.queue_listings(s) == 1
    titles = {v.title for v in s.cat.refresh(force=True).videos.values()}
    assert "創作者" not in titles                                              # 上架審核前不出現在公開網站
    s.com.grant_admin(acct)
    admin = alice
    items = admin.get("/studio/api/review").json()["items"]
    rid = next(i["id"] for i in items if i["kind"] == "listing")
    s.com.s.db.execute("DELETE FROM role")                                    # review as another admin
    boss = _user(c, "boss")
    s.com.grant_admin("boss")
    assert boss.post(f"/studio/api/review/{rid}", json={"decision": "approve"}, headers=H).status_code == 200
    assert "創作者" in {v.title for v in s.cat.refresh(force=True).videos.values()}
    fb = alice.get("/studio/api/feedback").json()
    assert fb["works"][0]["listing"] == "approved"


def test_clean_thumbnail_avoids_text():
    from midea.tools.video import clean_frame_time
    t = clean_frame_time(60, [(0, 3.5), (54, 60), (10, 20), (22, 40), (41, 50)])
    assert 9 <= t <= 10 or 20 <= t <= 22 or 50 <= t <= 51
    assert clean_frame_time(10, [(0, 10)]) == pytest.approx(5)
