"""The studio inside the public site: CAFECA identities as studio users, publish review, creator feedback, admin queue.

`install(state)` mounts the production board (midea/web/app.py) at /studio with CAFECA sessions instead of HTTP Basic,
and adds the routes that need the audience database (feedback, review queue).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import Body, HTTPException, Request

from .. import actors as AC
from ..config import settings
from ..log import get_logger
from ..project import Project
from ..web import access
from ..web import app as board
from ..web.access import User
from .store import kyc_bucket

log = get_logger("site.studio")


# ------------------------------------------------------------------------------------------------ listing (上架審核)
def admins(state) -> set[str]:
    cfg = {a.lower() for a in (settings().get("site.admins") or [])}
    return cfg | {r["account"] for r in state.store.q("SELECT account FROM role WHERE role='admin'")}


def project_listed(state, d: dict) -> bool:
    """Official/legacy work (no owner), an admin's work, or a creator's work that passed review."""
    owner = (d.get("owner") or "").lower()
    if not owner or owner in admins(state):
        return True
    return (d.get("listing") or {}).get("status") == "approved"


def actor_listed(state, a: dict) -> bool:
    owner = (a.get("owner") or "").lower()
    if not owner or owner in admins(state):
        return True
    return (a.get("listing") or {}).get("status") == "approved"


def queue_listings(state) -> int:
    """Creators' finished works and actor intros wait for an admin before they reach the public site."""
    n = 0
    adm = admins(state)
    for pj in settings().workspace.glob("*/project.json"):
        try:
            d = json.loads(pj.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        owner = (d.get("owner") or "").lower()
        if not owner or owner in adm or d.get("status") != "done" or (d.get("listing") or {}).get("status"):
            continue
        if not (pj.parent / "stages" / "publish.json").exists():
            continue
        Project(d["id"]).update(lambda x: x.__setitem__("listing", {"status": "pending", "at": time.time()}))
        state.com.open_review("listing", f"project:{d['id']}", f"上架申請：{(d.get('brief') or {}).get('prompt', '')[:60]}")
        n += 1
    for a in AC.list_all():
        owner = (a.owner or "").lower()
        if not owner or owner in adm or a.listing.get("status") or a.intro.get("status") != "pass":
            continue
        AC.update(a.id, lambda x: setattr(x, "listing", {"status": "pending", "at": time.time()}))
        state.com.open_review("listing", f"actor:{a.id}", f"演員上架申請：{a.name} @{a.handle}")
        n += 1
    return n


def apply_listing(target: str, decision: str, by: str, note: str) -> None:
    status = {"approve": "approved", "reject": "rejected"}.get(decision)
    if not status:
        raise HTTPException(400, "上架審核只能核准或退回")
    rec = {"status": status, "by": by, "at": time.time(), "note": note}
    kind, _, ident = target.partition(":")
    if kind == "project":
        Project(ident).update(lambda d: d.__setitem__("listing", rec))
    elif kind == "actor":
        AC.update(ident, lambda a: setattr(a, "listing", rec))


# ------------------------------------------------------------------------------------------------ identity
def resolver(state):
    def resolve(request: Request) -> User | None:
        v = state.store.session_viewer(request.cookies.get("mid_sess"))
        if not v or v["kind"] != "cafeca":
            return None
        if v["banned_until"] and v["banned_until"] > time.time():
            return None
        return User(account=v["account"], name=v["nickname"] or v["handle"] or v["account"][:10],
                    admin=state.com.is_admin(v["account"]), viewer_id=int(v["id"]), kyc_level=v["kyc_level"])
    return resolve


# ------------------------------------------------------------------------------------------------ creator feedback
def feedback(state, u: User) -> dict:
    s = state
    cat = s.cat.refresh(force=True)
    mine_works: dict[str, dict] = {}
    for v in cat.videos.values():
        if v.work.startswith("actor:"):
            continue
        try:
            d = Project(v.work).load()
        except Exception:  # noqa: BLE001
            continue
        if not u.owns(d.get("owner")) or (not u.admin and not d.get("owner")):
            continue
        w = mine_works.setdefault(v.work, {"work": v.work, "title": v.title, "listing": (d.get("listing") or {}).get("status") or
                                           ("approved" if project_listed(s, d) else ""), "videos": []})
        w["videos"].append(v.id)
    # unpublished-on-site works too (pending review), so creators see the whole picture
    for p in board.list_projects():
        if p["status"] == "done" and u.owns(p.get("owner")) and (u.admin or p.get("owner")) and p["id"] not in mine_works:
            mine_works[p["id"]] = {"work": p["id"], "title": p.get("title"), "listing": p.get("listing") or "", "videos": []}
    since7 = time.time() - 7 * 86400
    out = []
    for w in mine_works.values():
        ids = w["videos"]
        q = lambda sql, *a: s.store.q(sql.replace("{ids}", ",".join("?" * len(ids))), (*ids, *a)) if ids else []  # noqa: E731
        views = q("SELECT COUNT(*) n, SUM(completed) c, COUNT(DISTINCT viewer) u, SUM(CASE WHEN at>? AND completed=1 THEN 1 ELSE 0 END) w "
                  "FROM view WHERE video IN ({ids})", since7)
        v0 = views[0] if views else None
        reacts: dict[str, int] = {}
        for r in q("SELECT kind, COUNT(*) n FROM reaction WHERE video IN ({ids}) GROUP BY kind"):
            reacts[r["kind"]] = int(r["n"])
        reasons = {r["reason"]: int(r["n"]) for r in q("SELECT reason, COUNT(*) n FROM reaction WHERE video IN ({ids}) "
                                                       "AND kind='not_interested' AND reason IS NOT NULL GROUP BY reason")}
        favs = q("SELECT COUNT(*) n FROM favorite WHERE video IN ({ids})")
        live = q("SELECT kind, SUM(n) n FROM live_reaction WHERE video IN ({ids}) GROUP BY kind")
        prim = next((cat.get(i) for i in ids if cat.get(i) and cat.get(i).primary), None) or (cat.get(ids[0]) if ids else None)
        out.append({**w, "image": f"/media/t/{prim.id}.jpg" if prim else None, "href": f"/watch/{prim.id}" if prim else None,
                    "views": {"plays": int(v0["n"] or 0) if v0 else 0, "completed": int(v0["c"] or 0) if v0 else 0,
                              "viewers": int(v0["u"] or 0) if v0 else 0, "completed_7d": int(v0["w"] or 0) if v0 else 0},
                    "reactions": reacts, "not_interested_reasons": reasons, "favorites": int(favs[0]["n"]) if favs else 0,
                    "live": {r["kind"]: int(r["n"]) for r in live},
                    "highlights": s.prog.highlights(prim.id) if prim else []})
    out.sort(key=lambda w: -w["views"]["completed"])
    # questions to my actors, wishes that mention them
    actors = [a for a in AC.list_all() if a.owner and u.owns(a.owner) and (u.admin or a.owner == u.account)]
    if u.admin:
        actors += [a for a in AC.list_all() if not a.owner]
    acts = []
    for a in actors:
        qs = s.com.questions(a.handle, None, order="top", limit=5)
        n = s.store.one("SELECT COUNT(*) n FROM question WHERE actor=? AND status='shown'", (a.handle,))["n"]
        wishes = [c for c in s.com.wall(None, limit=200) if a.handle in c["actors"]][:5]
        acts.append({"handle": a.handle, "name": a.name, "listing": a.listing.get("status") or ("approved" if not a.owner else ""),
                     "questions": int(n), "top_questions": qs, "wishes": wishes})
    return {"works": out, "actors": acts, "at": time.time()}


# ------------------------------------------------------------------------------------------------ admin review queue
def review_list(state) -> list[dict]:
    out = []
    for r in state.com.reviews("open"):
        if r["kind"] == "listing":
            kind, _, ident = r["target"].partition(":")
            r["detail"] = {"kind": kind, "id": ident, "studio": f"#{ident}" if kind == "project" else f"#actor/{ident}"}
        elif r["kind"] == "report" and r["detail"].get("author"):
            v = state.store.one("SELECT nickname, handle, strikes FROM viewer WHERE id=?", (r["detail"]["author"],))
            r["detail"]["author_name"] = v and (v["nickname"] or v["handle"])
            r["detail"]["strikes"] = v and v["strikes"]
        out.append(r)
    return out


def install(get) -> None:
    """`get()` returns the site State (created lazily, so importing the site does not open the database)."""
    board.AUTH.update(mode="cafeca", resolve=lambda request: resolver(get())(request))
    sa = board.app

    @sa.get("/api/feedback")
    def _feedback(request: Request) -> dict:
        return feedback(get(), access.user(request))

    @sa.get("/api/review")
    def _reviews(request: Request) -> dict:
        access.require_admin(request)
        return {"items": review_list(get())}

    @sa.post("/api/review/{rid}")
    def _decide(rid: int, request: Request, body: dict = Body(...)) -> dict:
        u = access.require_admin(request)
        try:
            out = get().com.resolve(rid, str(body.get("decision")), by=u.account or u.name, note=str(body.get("note") or "")[:200])
        except LookupError as e:
            raise HTTPException(409, str(e)) from e
        if "listing" in out:
            apply_listing(out["listing"]["target"], out["listing"]["decision"], u.account, str(body.get("note") or ""))
            get().cat.refresh(force=True)
        return {"ok": True, **out}

    @sa.get("/api/poll-stats")
    def _poll_stats(request: Request) -> dict:
        """Admins: every poll with its KYC split."""
        access.require_admin(request)
        rows = get().store.q("SELECT * FROM poll ORDER BY closes DESC LIMIT 12")
        return {"polls": [{"id": r["id"], "title": r["title"], "winner": r["winner"], **get().store.tally(r["id"])} for r in rows],
                "buckets": [kyc_bucket(x) for x in (None, 0, 1, 2, 3)]}
