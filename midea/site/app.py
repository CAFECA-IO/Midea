"""midea.cafeca.io — public pages, media and /api/public/v1 (phase 1 of the audience-feedback plan).

Run with `midea site` (default 127.0.0.1:10030; put it behind HTTPS at the site origin for CAFECA sign-in).
State-changing calls need the `X-Midea: 1` header (cross-site forms cannot send it) and same-site cookies.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..config import ROOT, settings
from ..log import get_logger
from . import cafeca
from .catalog import catalog
from .live import LIVE_KINDS, LiveRoom
from .programming import INFLUENCE, Programming, day_label, hm, now_local, slot_range, week_start
from .community import CATEGORY, Community, Worker
from .store import Store, kyc_bucket

log = get_logger("site")
STATIC = Path(__file__).parent / "static"
DS = ROOT / "docs" / "design-system"
API = "/api/public/v1"
REACTIONS = ("like", "more", "not_interested")
NOT_INTERESTED_REASONS = ("topic", "seen", "quality", "other")     # 主題不合、看過了、品質不好、其他
DEV_COOKIE, SESS_COOKIE = "mid_dev", "mid_sess"


def data_dir() -> Path:
    p = Path(os.environ.get("MIDEA_SITE_DATA") or settings().get("site.data_dir") or (settings().workspace / "_site"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def origin() -> str:
    return (os.environ.get("MIDEA_SITE_ORIGIN") or settings().get("site.origin") or "https://midea.cafeca.io").rstrip("/")


def dev_login_enabled() -> bool:
    return os.environ.get("MIDEA_SITE_DEV_LOGIN") == "1"


class State:
    def __init__(self) -> None:
        self.store = Store(data_dir() / "site.db")
        self.cat = catalog()
        self.prog = Programming(self.store, self.cat, data_dir())
        self.live = LiveRoom(self.store)
        self.com = Community(self.store)
        self.post_responses: dict[str, tuple[float, Any]] = {}     # QR (post mode): nonce → wallet response
        self.chat_seen = int((self.store.one("SELECT MAX(id) m FROM chat") or {"m": 0})["m"] or 0)
        from . import studio
        self.cat.project_ok = lambda d: studio.project_listed(self, d)
        self.cat.actor_ok = lambda d: studio.actor_listed(self, d)
        self.prog.wish_source = self.com.open_wishes_for_topics
        self.prog.on_wish_topic = lambda cid: self.com.set_card_status(cid, "topic") if (
            self.store.one("SELECT status FROM wish_card WHERE id=?", (cid,)) or {"status": ""})["status"] == "open" else None
        self.worker = Worker(self.com, actor_bible)


def actor_bible(handle: str) -> dict | None:
    from .. import actors as AC
    a = AC.find(handle)
    return AC.bible(a) | {"name": a.name, "handle": a.handle} if a else None


S: State | None = None


def st() -> State:
    global S
    if S is None:
        S = State()
    return S


from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(_app):
    task = await _start()
    try:
        yield
    finally:
        task.cancel()
        if S:
            S.live.flush()


app = FastAPI(title="Midea", docs_url=None, redoc_url=None, openapi_url=None, lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ------------------------------------------------------------------------------------------------ identity
@app.middleware("http")
async def _identity(request: Request, call_next):
    dev = request.cookies.get(DEV_COOKIE)
    new = not dev or not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", dev or "")
    if new:
        dev = secrets.token_urlsafe(18)
    request.state.device = dev
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path.startswith(API) \
            and request.url.path != f"{API}/auth/post" and request.headers.get("x-midea") != "1":
        return JSONResponse({"error": "missing X-Midea header"}, status_code=403)
    resp = await call_next(request)
    if new:
        resp.set_cookie(DEV_COOKIE, dev, max_age=400 * 86400, httponly=True, samesite="lax", secure=_secure())
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return resp


def _secure() -> bool:
    return origin().startswith("https://")


def me(request: Request):
    return st().store.session_viewer(request.cookies.get(SESS_COOKIE))


def actor_id(request: Request) -> tuple[int, bool, Any]:
    """(viewer id, anonymous?, viewer row or None) — anonymous = this browser's device viewer."""
    v = me(request)
    if v:
        return int(v["id"]), False, v
    return st().store.device_viewer(request.state.device), True, None


def need_login(request: Request):
    v = me(request)
    if not v:
        raise HTTPException(401, "以 CAFECA 登入後才能使用")
    if v["status"] == "banned":
        raise HTTPException(403, "帳戶已停權")
    return v


def me_public(v) -> dict | None:
    if not v:
        return None
    s = st()
    ok, why = s.com.writer_state(v)
    return {"account": v["account"], "handle": v["handle"], "nickname": v["nickname"] or v["handle"] or v["account"][:8],
            "has_nickname": bool(v["nickname"]), "kyc_level": v["kyc_level"], "kyc_bucket": kyc_bucket(v["kyc_level"]),
            "admin": s.com.is_admin(v["account"]), "can_write": ok, "restriction": why or None,
            "wishes_left": s.com.wishes_left(int(v["id"]))}


def src_of(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")
    import hashlib
    return hashlib.sha256(ip.encode()).hexdigest()[:16] if ip else ""


# ------------------------------------------------------------------------------------------------ background
async def _start():
    s = st()
    s.cat.refresh(force=True)
    await asyncio.to_thread(s.prog.ensure)

    async def ticker() -> None:
        n = 0
        while True:
            await asyncio.sleep(1)
            n += 1
            try:
                s.live.broadcast(live_tick())
                if n % 5 == 0:
                    await asyncio.to_thread(s.live.flush)
                if n % 30 == 0:
                    asyncio.get_running_loop().run_in_executor(None, s.worker.run_once)   # AI moderation + actor replies
                if n % 60 == 0:
                    await asyncio.to_thread(s.prog.ensure)
                    from . import studio
                    if await asyncio.to_thread(studio.queue_listings, s):
                        s.cat.refresh(force=True)
                if n % 3600 == 0:
                    await asyncio.to_thread(s.prog.write_highlights)
            except Exception as e:  # noqa: BLE001
                log.warning("live tick: %s", e)

    return asyncio.get_running_loop().create_task(ticker())


# ------------------------------------------------------------------------------------------------ pages & media
def _asset_version() -> str:
    """Changes whenever a page script, stylesheet or the design-system bundle changes — the CDN caches /static and /ds
    for hours, so every page asks for `?v=<version>` and a deploy is visible at once."""
    import hashlib
    h = hashlib.sha1()
    for f in sorted(list(STATIC.glob("*.js")) + list(STATIC.glob("*.css")) + list(_DS_FILES.values())):
        if f.exists():
            h.update(f"{f.name}:{f.stat().st_mtime_ns}:{f.stat().st_size}".encode())
    return h.hexdigest()[:10]


def _page(name: str) -> HTMLResponse:
    html = (STATIC / name).read_text(encoding="utf-8")
    v = _asset_version()
    html = re.sub(r'((?:src|href)="/(?:static|ds)/[^"?]+)"', lambda m: f'{m.group(1)}?v={v}"', html)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/", response_class=HTMLResponse)
def home_page():
    return _page("index.html")


@app.get("/live", response_class=HTMLResponse)
def live_page():
    return _page("live.html")


@app.get("/watch/{vid}", response_class=HTMLResponse)
def watch_page(vid: str):
    return _page("watch.html")


@app.get("/schedule", response_class=HTMLResponse)
def schedule_page():
    return _page("schedule.html")


@app.get("/auth/callback", response_class=HTMLResponse)
def callback_page():
    return _page("callback.html")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


_DS_FILES = {"tokens.css": DS / "tokens.css", "bundle.css": DS / "components" / "bundle.css",
             "bundle.js": DS / "components" / "bundle.js", "midea-mark.svg": DS / "assets" / "midea-mark.svg"}


@app.get("/ds/{name}")
def ds_file(name: str):
    f = _DS_FILES.get(name)
    if not f or not f.exists():
        raise HTTPException(404)
    return FileResponse(f, headers={"Cache-Control": "public, max-age=300"})


@app.get("/media/v/{vid}.mp4")
def media_video(vid: str):
    v = st().cat.get(vid)
    if not v:
        raise HTTPException(404)
    return FileResponse(v.file, media_type="video/mp4", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/media/t/{vid}.jpg")
def media_thumb(vid: str):
    v = st().cat.get(vid)
    if not v or not v.thumb:
        raise HTTPException(404)
    return FileResponse(v.thumb, headers={"Cache-Control": "public, max-age=86400"})


@app.get("/media/c/{vid}.vtt")
def media_captions(vid: str):
    v = st().cat.get(vid)
    if not v or not v.srt:
        raise HTTPException(404)
    srt = Path(v.srt).read_text(encoding="utf-8")
    vtt = "WEBVTT\n\n" + re.sub(r"(\d\d:\d\d:\d\d),(\d\d\d)", r"\1.\2", srt)
    return Response(vtt, media_type="text/vtt", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/media/a/{handle}.jpg")
def media_actor(handle: str):
    a = st().cat.refresh().actors.get(handle)
    if not a:
        raise HTTPException(404)
    return FileResponse(a.headshot, headers={"Cache-Control": "public, max-age=86400"})


# ------------------------------------------------------------------------------------------------ shaping
def vpub(vid: str) -> dict | None:
    v = st().cat.get(vid)
    return v.public(st().cat.names()) if v else None


def slot_pub(s: dict | None, *, with_videos: bool = False) -> dict | None:
    if not s:
        return None
    d = {"id": s["id"], "title": s["title"], "range": slot_range(s["start"]), "start": s["start"], "end": s["end"],
         "count": len(s["videos"]), "reason": s.get("reason", ""), "program": s.get("program"),
         "influence": INFLUENCE.get(s.get("influence") or "", None), "prime": s.get("prime", False),
         "day": day_label(now_local(s["start"])), "poll": s.get("poll")}
    first = next((vpub(v) for v in s["videos"] if st().cat.get(v)), None)
    d["image"] = first["image"] if first else None
    if with_videos:
        d["videos"] = [x for x in (vpub(v) for v in s["videos"]) if x]
    return d


def live_now() -> dict:
    s = st()
    np = s.prog.now_playing()
    if not np or not np["items"]:
        return {"slot": slot_pub(np["slot"]) if np else None, "item": None}
    item = np["items"][np["index"]]
    nxt = s.prog.slot_at(np["slot"]["end"] + 1)
    return {"slot": slot_pub(np["slot"]), "index": np["index"], "of": len(np["items"]), "offset": np["offset"],
            "item": item.public(s.cat.names()), "next": slot_pub(nxt), "server_time": time.time(),
            "playlist": [v.id for v in np["items"]],
            "highlights": s.prog.highlights(item.id)}


def live_tick() -> dict:
    s = st()
    now = time.time()
    sl = s.prog.slot_at(now)
    second = s.live.take_second()
    ev: dict = {"t": "tick", "at": now, "reactions": second["show"], "viewers": s.live.viewers()}
    new = s.com.chat_since(s.chat_seen)
    if new:
        s.chat_seen = new[-1]["id"]
        ev["chat"] = new
    if s.com.retracted:
        ev["chat_removed"], s.com.retracted = s.com.retracted[:], []
    if sl:
        ev["slot"] = {"id": sl["id"], "ends_in": round(sl["end"] - now)}
        if sl["end"] - now <= 60 and sl.get("program") not in (None, "rotation"):
            ev["slot_poll"] = {"slot": sl["id"], "program": sl["program"], "title": sl["title"], "ends_in": round(sl["end"] - now)}
    return ev


def poll_pub(row, viewer: int | None) -> dict | None:
    if not row:
        return None
    s = st()
    opts = json.loads(row["options"])
    t = s.store.tally(row["id"])
    now = time.time()
    closed = row["winner"] is not None or now >= row["closes"]
    mine = s.store.my_vote(row["id"], viewer) if viewer else None
    show = closed or mine is not None                     # results after you voted (or after it closed)
    out, used = [], set()
    for o in opts:
        n = t["total"].get(o["id"], 0)
        imgs = [x["image"] for x in (vpub(v) for v in o["videos"]) if x]
        lead = next((i for i in imgs if i not in used), imgs[0] if imgs else None)   # candidates should not look alike
        used.add(lead)
        imgs = ([lead] if lead else []) + [i for i in imgs if i != lead]
        out.append({"id": o["id"], "title": o["title"], "why": o.get("why", ""),
                    "images": imgs[:3],
                    "votes": n if show else None, "share": (round(100 * n / t["votes"]) if t["votes"] else 0) if show else None})
    c = now_local(row["closes"] - 1)
    slot = s.prog.slot_at(_slot_ts(row["slot"]))
    return {"id": row["id"], "title": row["title"], "slot": row["slot"], "slot_label": slot and f"{day_label(now_local(slot['start']))}{slot_range(slot['start'])}",
            "options": out, "votes": t["votes"], "mine": mine, "closed": closed, "winner": row["winner"],
            "closes": row["closes"], "closes_label": f"{c.month}/{c.day}（{'一二三四五六日'[c.weekday()]}）24:00",
            "by_kyc": t["by_kyc"] if show else None}


def _slot_ts(slot_id: str) -> float:
    from datetime import datetime
    from .programming import TZ
    return datetime.strptime(slot_id, "%Y-%m-%dT%H:%M").replace(tzinfo=TZ).timestamp() + 1


def topics_for(viewer: int | None) -> list[dict]:
    """Topics on the home page: 「依你的觀看」 when the viewer liked something in it; hidden videos removed."""
    s = st()
    d = s.prog.topics()
    mine = s.store.viewer_reactions(viewer) if viewer else {}
    hidden = {v for v, k in mine.items() if k == "not_interested"}
    liked = {v for v, k in mine.items() if k in ("like", "more")}
    liked_works = {s.cat.get(v).work for v in liked if s.cat.get(v)}
    out = []
    for t in d["topics"]:
        vids = [v for v in t["videos"] if v not in hidden and s.cat.get(v)]
        if not vids:
            continue
        hit = next((s.cat.get(v) for v in vids if s.cat.get(v).work in liked_works), None)
        reason = f"因為你喜歡《{hit.title}》" if hit else t.get("note") or ""
        out.append({"key": t["key"], "title": t["title"], "reason": reason, "personal": bool(hit),
                    "influence": INFLUENCE["wish"] if t["key"].startswith("wish-") else None,
                    "videos": [vpub(v) for v in vids[:5]], "count": len(vids)})
    out.sort(key=lambda t: not t["personal"])
    at = now_local(d["at"])
    return [{**t, "meta": f"{'今天' if at.date() == now_local().date() else f'{at.month}/{at.day}'} {at.strftime('%H:%M')} 歸納 · {t['count']} 部"} for t in out]


# ------------------------------------------------------------------------------------------------ API: home
@app.get(API + "/home")
def api_home(request: Request) -> dict:
    s = st()
    viewer, anon, v = actor_id(request)
    mon = week_start(now_local().date())
    nightly = s.prog.nightly(mon)
    poll_row = s.store.open_poll(time.time()) or s.store.latest_poll()
    ranks = {}
    for p in ("today", "week", "month"):
        r = s.prog.ranking(p)
        rows = []
        for i, x in enumerate(r["rows"]):
            pv = next((y for y in s.cat.works() if y.work == x["work"]), None)
            if pv:
                rows.append({"rank": i + 1, "move": x["move"], "views": x["views"], **pv.public(s.cat.names())})
        ranks[p] = {"rows": rows, "at": hm(r["at"])}
    week_plan = s.prog.week(mon) or {}
    return {
        "me": me_public(v), "live": live_now(),
        "verticals": [x.public(s.cat.names()) for x in s.cat.verticals()[:6]],
        "poll": poll_pub(poll_row, viewer if not anon else None),
        "nightly": [{**slot_pub(n), "day": n["day"], "time": n["time"], "today": n["today"]} for n in nightly],
        "schedule_note": (week_plan or None) and f"{now_local(week_plan['published']).month}/{now_local(week_plan['published']).day}"
                         f"（{'一二三四五六日'[now_local(week_plan['published']).weekday()]}）由 AI 排定",
        "ranking": ranks, "topics": topics_for(viewer),
        "actors": [a.public() | {"works": sum(1 for w in s.cat.works() if a.handle in w.actors and not w.work.startswith('actor:'))}
                   for a in s.cat.refresh().actors.values()],
        "dev_login": dev_login_enabled(),
    }


@app.get(API + "/me")
def api_me(request: Request) -> dict:
    v = me(request)
    return {"me": me_public(v), "favorites": st().store.favorites(int(v["id"])) if v else []}


# ------------------------------------------------------------------------------------------------ API: auth
STATEMENT = "登入 Midea：同步主題、收藏與觀看紀錄，參加投票"


@app.get(API + "/auth/nonce")
def auth_nonce(request: Request) -> dict:
    n = st().store.new_nonce(request.state.device)
    return {"nonce": n, "origin": origin(), "wallet": cafeca.wallet(), "statement": STATEMENT,
            "claims": ["kyc_level", "handle"], "redirectUri": origin() + "/auth/callback",
            "responseUri": origin() + API + "/auth/post"}


def _finish_login(request: Request, res: dict) -> JSONResponse:
    s = st()
    dev = request.state.device
    try:
        info = cafeca.verify(res, origin=origin(), nonce_ok=lambda n: s.store.take_nonce(n, dev))
    except cafeca.SignInError as e:
        raise HTTPException(400, str(e)) from e
    vid, token = s.store.sign_in(info["account"], handle=info["handle"], kyc_level=info["kyc_level"], device=dev)
    out = JSONResponse({"me": me_public(s.store.one("SELECT * FROM viewer WHERE id=?", (vid,)))})
    out.set_cookie(SESS_COOKIE, token, max_age=30 * 86400, httponly=True, samesite="lax", secure=_secure())
    return out


@app.post(API + "/auth/cafeca")
def auth_cafeca(request: Request, res: dict = Body(...)):
    return _finish_login(request, res)


@app.post(API + "/auth/post")
async def auth_post(request: Request):
    """QR / cross-device: the CAFECA app POSTs the response here (text/plain); the desktop page then polls."""
    raw = (await request.body())[:20000]
    try:
        res = json.loads(raw.decode("utf-8"))
        nonce = str((res.get("message") or {}).get("nonce") or res.get("nonce") or "")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, "bad response") from e
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", nonce):
        raise HTTPException(400, "bad nonce")
    pend = st().post_responses
    for k in [k for k, (t, _) in pend.items() if time.time() - t > 600]:
        pend.pop(k, None)
    pend[nonce] = (time.time(), res)
    return {"ok": True}


@app.post(API + "/auth/post/claim")
def auth_post_claim(request: Request, body: dict = Body(...)):
    got = st().post_responses.pop(str(body.get("nonce", "")), None)
    if not got:
        return JSONResponse({"pending": True}, status_code=202)
    return _finish_login(request, got[1])


@app.post(API + "/auth/logout")
def auth_logout(request: Request):
    st().store.sign_out(request.cookies.get(SESS_COOKIE))
    out = JSONResponse({"ok": True})
    out.delete_cookie(SESS_COOKIE)
    return out


@app.post(API + "/auth/dev")
def auth_dev(request: Request, body: dict = Body(...)):
    """Local testing only (MIDEA_SITE_DEV_LOGIN=1): sign in as a fake CAFECA identity."""
    if not dev_login_enabled():
        raise HTTPException(404)
    h = re.sub(r"[^a-z0-9_]", "", str(body.get("handle", "tester")).lower())[:20] or "tester"
    acct = "0x" + __import__("hashlib").sha256(h.encode()).hexdigest()[:40]
    vid, token = st().store.sign_in(acct, handle=h, kyc_level=body.get("kyc_level"), device=request.state.device)
    out = JSONResponse({"me": me_public(st().store.one("SELECT * FROM viewer WHERE id=?", (vid,)))})
    out.set_cookie(SESS_COOKIE, token, max_age=86400, httponly=True, samesite="lax", secure=_secure())
    return out


# ------------------------------------------------------------------------------------------------ API: videos
@app.get(API + "/videos/{vid}")
def api_video(vid: str, request: Request) -> dict:
    s = st()
    v = s.cat.get(vid)
    if not v:
        raise HTTPException(404, "找不到這部影片")
    viewer, anon, row = actor_id(request)
    favs = s.store.favorites(viewer) if not anon else []
    related = []
    for t in s.prog.topics()["topics"]:
        if any(s.cat.get(x) and s.cat.get(x).work == v.work for x in t["videos"]):
            related += [x for x in t["videos"] if s.cat.get(x) and s.cat.get(x).work != v.work]
    seen, rel = set(), []
    hidden = {k for k, r in s.store.viewer_reactions(viewer).items() if r == "not_interested"}
    for x in related:
        if x not in seen and x not in hidden:
            seen.add(x)
            rel.append(vpub(x))
    return {"video": v.public(s.cat.names()), "versions": [x.public() for x in s.cat.versions(v.work)],
            "reaction": s.store.my_reaction(viewer, vid), "favorite": vid in favs, "me": me_public(row),
            "highlights": s.prog.highlights(vid), "related": rel[:8]}


@app.post(API + "/videos/{vid}/reaction")
def api_react(vid: str, request: Request, body: dict = Body(...)):
    if not st().cat.get(vid):
        raise HTTPException(404)
    kind = body.get("kind")
    if kind not in REACTIONS:
        raise HTTPException(400, "unknown reaction")
    reason = body.get("reason") if kind == "not_interested" and body.get("reason") in NOT_INTERESTED_REASONS else None
    viewer, anon, _ = actor_id(request)
    return st().store.set_reaction(viewer, vid, kind, reason, anon=anon, src=src_of(request))


@app.delete(API + "/videos/{vid}/reaction")
def api_unreact(vid: str, request: Request):
    viewer, _, _ = actor_id(request)
    st().store.clear_reaction(viewer, vid)
    return {"kind": None}


@app.post(API + "/videos/{vid}/favorite")
def api_fav(vid: str, request: Request):
    v = need_login(request)
    if not st().cat.get(vid):
        raise HTTPException(404)
    st().store.set_favorite(int(v["id"]), vid, True)
    return {"favorite": True}


@app.delete(API + "/videos/{vid}/favorite")
def api_unfav(vid: str, request: Request):
    v = need_login(request)
    st().store.set_favorite(int(v["id"]), vid, False)
    return {"favorite": False}


@app.post(API + "/videos/{vid}/view")
def api_view(vid: str, request: Request, body: dict = Body(...)):
    v = st().cat.get(vid)
    if not v:
        raise HTTPException(404)
    seconds = max(0.0, min(float(body.get("seconds") or 0), v.duration + 1))
    completed = bool(body.get("completed")) and seconds >= 0.9 * v.duration      # 完整看完 = watched ≥ 90 %
    viewer, _, _ = actor_id(request)
    st().store.record_view(viewer, vid, seconds, completed, now_local().date().isoformat())
    return {"completed": completed}


@app.get(API + "/me/favorites")
def api_favs(request: Request):
    v = need_login(request)
    return {"videos": [x for x in (vpub(i) for i in st().store.favorites(int(v["id"]))) if x]}


# ------------------------------------------------------------------------------------------------ API: live
@app.get(API + "/live/now")
def api_live_now(request: Request) -> dict:
    st().live.heartbeat(request.state.device)
    return live_now()


@app.get(API + "/live/stream")
async def api_live_stream(request: Request):
    s = st()
    who = request.state.device
    q = s.live.subscribe()
    s.live.heartbeat(who)

    async def gen():
        try:
            yield "retry: 3000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                s.live.heartbeat(who)
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            s.live.unsubscribe(q)
            s.live.leave(who)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post(API + "/live/reactions")
def api_live_react(request: Request, body: dict = Body(...)):
    s = st()
    kind = body.get("kind")
    if kind not in LIVE_KINDS:
        raise HTTPException(400, "unknown reaction")
    np = s.prog.now_playing()
    if not np or not np["items"]:
        raise HTTPException(409, "現在沒有直播")
    item = np["items"][np["index"]]
    v = me(request)
    who = f"v{v['id']}" if v else request.state.device
    if not s.live.press(who, kind, np["slot"]["id"], item.id, np["offset"]):
        return JSONResponse({"ok": False, "retry_after": 2}, status_code=429)
    return {"ok": True}


@app.post(API + "/live/slot-vote")
def api_slot_vote(request: Request, body: dict = Body(...)):
    v = need_login(request)
    s = st()
    sl = s.prog.slot_at(time.time())
    if not sl or body.get("slot") != sl["id"] or sl["end"] - time.time() > 75 or sl.get("program") in (None, "rotation"):
        raise HTTPException(409, "這個時段的投票還沒開始或已經結束")
    s.store.slot_vote(sl["id"], sl["program"], int(v["id"]), bool(body.get("want")), v["kyc_level"])
    return {"mine": bool(body.get("want")), "tally": s.store.slot_tally(slot=sl["id"])}


# ------------------------------------------------------------------------------------------------ API: polls & schedule
@app.get(API + "/polls/current")
def api_poll(request: Request):
    viewer, anon, _ = actor_id(request)
    row = st().store.open_poll(time.time()) or st().store.latest_poll()
    return {"poll": poll_pub(row, None if anon else viewer)}


@app.post(API + "/polls/{pid}/vote")
def api_vote(pid: str, request: Request, body: dict = Body(...)):
    v = need_login(request)
    s = st()
    row = s.store.poll(pid)
    if not row:
        raise HTTPException(404)
    now = time.time()
    if not (row["opens"] <= now < row["closes"]) or row["winner"]:
        raise HTTPException(409, "投票已截止")
    if body.get("option") not in {o["id"] for o in json.loads(row["options"])}:
        raise HTTPException(400, "沒有這個候選")
    s.store.vote(pid, int(v["id"]), body["option"], v["kyc_level"])     # no KYC requirement; tallied per level
    return {"poll": poll_pub(s.store.poll(pid), int(v["id"]))}


@app.get(API + "/schedule")
def api_schedule(week: str | None = None):
    from datetime import date
    s = st()
    mon = week_start(date.fromisoformat(week)) if week else week_start(now_local().date())
    plan = s.prog.week(mon)
    if not plan:
        return {"week": mon.isoformat(), "days": [], "note": "下週節目表每週一 09:00 公布"}
    days: dict[str, list] = {}
    now = time.time()
    for sl in plan["slots"]:
        if not sl["prime"]:
            continue
        d = slot_pub(sl)
        d["now"] = sl["start"] <= now < sl["end"]
        days.setdefault(day_label(now_local(sl["start"])), []).append(d)
    pub = now_local(plan["published"])
    return {"week": mon.isoformat(), "by": plan.get("by"), "published": f"{pub.month}/{pub.day} {pub.strftime('%H:%M')}",
            "days": [{"day": k, "today": k == day_label(now_local()), "slots": v} for k, v in days.items()]}


# ------------------------------------------------------------------------------------------------ API: phase 2 (community)
def _writer(request: Request):
    v = need_login(request)
    return v


def _err(e: Exception) -> HTTPException:
    code = {PermissionError: 403, OverflowError: 429, LookupError: 404}.get(type(e), 400)
    return HTTPException(code, str(e))


@app.post(API + "/me/nickname")
def api_nickname(request: Request, body: dict = Body(...)):
    v = _writer(request)
    s = st()
    from .. import actors as AC
    names = [x for a in AC.list_all() for x in (a.name, a.handle)]
    try:
        n = s.com.set_nickname(int(v["id"]), str(body.get("nickname") or ""), names)
    except ValueError as e:
        raise _err(e) from e
    return {"nickname": n}


@app.get(API + "/me/notices")
def api_notices(request: Request):
    v = need_login(request)
    return {"notices": st().com.notices(int(v["id"]))}


@app.get(API + "/live/chat")
def api_chat(request: Request, slot: str | None = None):
    s = st()
    sl = s.prog.slot_at(time.time())
    sid = slot or (sl and sl["id"])
    pinned = None
    if sl and sid == sl["id"]:
        pinned = f"本時段「{sl['title']}」{slot_range(sl['start'])} · {len(sl['videos'])} 部 · {sl.get('reason', '')}"
    return {"slot": sid, "pinned": pinned, "messages": s.com.recent_chat(sid) if sid else []}


@app.post(API + "/live/chat")
def api_chat_post(request: Request, body: dict = Body(...)):
    v = _writer(request)
    s = st()
    sl = s.prog.slot_at(time.time())
    if not sl:
        raise HTTPException(409, "現在沒有直播")
    try:
        return s.com.post_chat(v, sl["id"], str(body.get("text") or ""))
    except (PermissionError, OverflowError, ValueError) as e:
        raise _err(e) from e


@app.get(API + "/wishes")
def api_wishes(request: Request, status: str | None = None):
    viewer, anon, v = actor_id(request)
    s = st()
    return {"cards": s.com.wall(None if anon else viewer, status if status in ("open", "topic", "producing", "done") else None),
            "left": s.com.wishes_left(viewer) if not anon else None, "threshold": int(settings().get("site.wish_threshold", 30)),
            "actors": [{"handle": a.handle, "name": a.name, "image": f"/media/a/{a.handle}.jpg"} for a in s.cat.refresh().actors.values()]}


@app.post(API + "/wishes")
def api_wish(request: Request, body: dict = Body(...)):
    v = _writer(request)
    s = st()
    try:
        return s.com.make_wish(v, str(body.get("kind") or "topic"), str(body.get("text") or ""), list(body.get("actors") or []),
                               {h: a.name for h, a in s.cat.refresh().actors.items()})
    except (PermissionError, OverflowError, ValueError) as e:
        raise _err(e) from e


@app.post(API + "/wishes/{card}/support")
def api_wish_support(card: int, request: Request):
    v = _writer(request)
    try:
        return st().com.support_wish(int(v["id"]), card, True)
    except LookupError as e:
        raise _err(e) from e


@app.delete(API + "/wishes/{card}/support")
def api_wish_unsupport(card: int, request: Request):
    v = _writer(request)
    try:
        return st().com.support_wish(int(v["id"]), card, False)
    except LookupError as e:
        raise _err(e) from e


def actor_pub(handle: str, viewer: int | None) -> dict:
    s = st()
    a = s.cat.refresh().actors.get(handle)
    if not a:
        raise HTTPException(404, "找不到這位演員")
    from .. import actors as AC
    full = AC.find(handle)
    works = [v.public(s.cat.names()) for v in s.cat.works() if handle in v.actors and not v.work.startswith("actor:")]
    answered = s.com.questions(handle, viewer, order="answered", limit=12)
    return {"actor": a.public() | {"bio": full.bio if full else "", "personality": full.personality if full else "",
                                    "age": a.age, "official": not (full and full.owner)},
            "intro": vpub(a.intro_video) if a.intro_video else None, "works": works,
            "counts": {"works": len(works), "questions": int(s.store.one("SELECT COUNT(*) n FROM question WHERE actor=? AND status='shown'", (handle,))["n"]),
                       "answers": sum(1 for q in answered if q["answer_video"])},
            "left": s.com.questions_left(viewer) if viewer else None}


@app.get(API + "/actors/{handle}")
def api_actor(handle: str, request: Request):
    viewer, anon, _ = actor_id(request)
    return actor_pub(handle, None if anon else viewer)


@app.get(API + "/actors/{handle}/questions")
def api_questions(handle: str, request: Request, order: str = "top"):
    viewer, anon, _ = actor_id(request)
    if handle not in st().cat.refresh().actors:
        raise HTTPException(404)
    s = st()
    v = None if anon else viewer
    return {"questions": s.com.questions(handle, v, order if order in ("top", "new", "answered") else "top"),
            "mine": s.com.my_questions(v, handle) if v else []}


@app.post(API + "/actors/{handle}/questions")
def api_ask(handle: str, request: Request, body: dict = Body(...)):
    v = _writer(request)
    s = st()
    if handle not in s.cat.refresh().actors:
        raise HTTPException(404)
    try:
        out = s.com.ask(v, handle, str(body.get("text") or ""))
    except (PermissionError, OverflowError, ValueError) as e:
        raise _err(e) from e
    return out


@app.post(API + "/questions/{qid}/support")
def api_q_support(qid: int, request: Request):
    v = _writer(request)
    try:
        return {"supporters": st().com.support_question(int(v["id"]), qid, True)}
    except LookupError as e:
        raise _err(e) from e


@app.delete(API + "/questions/{qid}/support")
def api_q_unsupport(qid: int, request: Request):
    v = _writer(request)
    try:
        return {"supporters": st().com.support_question(int(v["id"]), qid, False)}
    except LookupError as e:
        raise _err(e) from e


@app.post(API + "/reports")
def api_report(request: Request, body: dict = Body(...)):
    v = need_login(request)
    try:
        return st().com.report(int(v["id"]), str(body.get("kind")), int(body.get("id") or 0), body.get("reason"))
    except (ValueError, LookupError) as e:
        raise _err(e) from e


@app.get(API + "/topics/{key}")
def api_topic(key: str, request: Request):
    s = st()
    viewer, anon, _ = actor_id(request)
    for t in topics_for(None if anon else viewer):
        if t["key"] == key:
            allv = next((x["videos"] for x in s.prog.topics()["topics"] if x["key"] == key), [])
            return t | {"videos": [x for x in (vpub(v) for v in allv) if x]}
    raise HTTPException(404, "這個主題已經重新歸納，請回首頁看看最新的主題")


@app.get("/actor/{handle}", response_class=HTMLResponse)
def actor_page(handle: str):
    return _page("actor.html")


@app.get("/topic/{key}", response_class=HTMLResponse)
def topic_page(key: str):
    return _page("topic.html")


@app.get("/wishes", response_class=HTMLResponse)
def wishes_page():
    return _page("wishes.html")


# ------------------------------------------------------------------------------------------------ the studio (/studio)
def _mount_studio() -> None:
    from ..web import app as board
    from . import studio
    studio.install(st)
    app.mount("/studio", board.app)


_mount_studio()
