"""Phase 2 of the audience plan: live chat, wish wall, questions to actors, reports, penalties and the review queue.

Moderation runs in two passes:
1. **rules** (instant, every message): personal data (phone, e-mail, ID numbers), links / ads, and a word list for
   harassment, hate and sexual content. A hit is not shown and the writer is told which category it was.
2. **AI** (Qwen, in the background worker): texts that passed the rules are classified again into the plan's six
   categories; a hit hides the text afterwards (chat messages are retracted live). The same worker writes the
   actors' first-person text replies. Qwen is shared with production, so this pass waits for it instead of
   blocking the page — the plan's "1 second or not shown" became "rules first, AI right after".

Every text can be reported; three different reporters hide it and open a review. Confirmed violations escalate:
warning → muted 24 h → suspended 30 days (watching is never blocked).
"""
from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from ..config import settings
from ..log import get_logger
from .store import Store

log = get_logger("site.community")

SCHEMA = """
CREATE TABLE IF NOT EXISTS role (account TEXT PRIMARY KEY, role TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS chat (
  id INTEGER PRIMARY KEY, slot TEXT NOT NULL, viewer INTEGER NOT NULL, nickname TEXT NOT NULL, text TEXT NOT NULL,
  status TEXT NOT NULL, reason TEXT, checked INTEGER NOT NULL DEFAULT 0, at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS chat_slot ON chat(slot, id);
CREATE TABLE IF NOT EXISTS wish_card (
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, text TEXT NOT NULL, actors TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'open', merged INTEGER NOT NULL DEFAULT 1, note TEXT, project TEXT,
  created REAL NOT NULL, updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS wish (
  id INTEGER PRIMARY KEY, card INTEGER NOT NULL, viewer INTEGER NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL,
  actors TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL, reason TEXT, checked INTEGER NOT NULL DEFAULT 0, at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS wish_support (card INTEGER NOT NULL, viewer INTEGER NOT NULL, at REAL NOT NULL, PRIMARY KEY (card, viewer));
CREATE TABLE IF NOT EXISTS question (
  id INTEGER PRIMARY KEY, actor TEXT NOT NULL, viewer INTEGER NOT NULL, text TEXT NOT NULL, status TEXT NOT NULL,
  reason TEXT, checked INTEGER NOT NULL DEFAULT 0, reply TEXT, reply_status TEXT NOT NULL DEFAULT 'pending',
  picked REAL, answer_video TEXT, at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS question_actor ON question(actor, status);
CREATE TABLE IF NOT EXISTS question_support (question INTEGER NOT NULL, viewer INTEGER NOT NULL, at REAL NOT NULL, PRIMARY KEY (question, viewer));
CREATE TABLE IF NOT EXISTS report (
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, target INTEGER NOT NULL, viewer INTEGER NOT NULL, reason TEXT, at REAL NOT NULL,
  UNIQUE (kind, target, viewer)
);
CREATE TABLE IF NOT EXISTS review (
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, target TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', summary TEXT,
  decision TEXT, note TEXT, by TEXT, created REAL NOT NULL, resolved REAL, UNIQUE (kind, target)
);
CREATE TABLE IF NOT EXISTS penalty (
  id INTEGER PRIMARY KEY, viewer INTEGER NOT NULL, level INTEGER NOT NULL, until REAL, reason TEXT, by TEXT, at REAL NOT NULL
);
"""

CHAT_MAX, CHAT_GAP_S = 100, 5
WISH_TOPIC_MAX, WISHES_PER_WEEK = 40, 3
QUESTION_MAX, QUESTIONS_PER_DAY = 60, 3
REPLY_MAX = 80
REPORTS_TO_HIDE = 3
NICK_MIN, NICK_MAX = 2, 16

CATEGORY = {"harassment": "騷擾", "hate": "仇恨", "sexual": "色情", "personal": "個資", "ads": "廣告", "real_person": "真實人物"}

_RULES: list[tuple[str, re.Pattern]] = [
    ("personal", re.compile(r"(09\d{2}[-\s]?\d{3}[-\s]?\d{3})|(\+?886[-\s]?9\d{2}[-\s]?\d{3}[-\s]?\d{3})|"
                            r"([\w.+-]+@[\w-]+\.[\w.]+)|(\b[A-Z][12]\d{8}\b)", re.I)),
    ("ads", re.compile(r"(https?://|www\.|\.com\b|\.tw\b|line\s*id|加\s*line|加賴|私訊|優惠碼|代購|賺錢|博弈|娛樂城|t\.me/)", re.I)),
    ("sexual", re.compile(r"(色情|裸照|約炮|援交|性交易|porn|nude|sex\s*chat)", re.I)),
    ("hate", re.compile(r"(去死吧|滾回|支那|黑鬼|nigg|faggot|殺光)", re.I)),
    ("harassment", re.compile(r"(白癡|智障|廢物|幹你|操你|垃圾人|fuck\s*you|stupid\s*bitch)", re.I)),
]


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def rules_check(text: str) -> str | None:
    """Category key of the first rule hit, or None."""
    t = norm(text)
    for cat, rx in _RULES:
        if rx.search(t):
            return cat
    return None


def similar(a: str, b: str) -> float:
    a, b = re.sub(r"[\s，。,.!?！？、]", "", norm(a).lower()), re.sub(r"[\s，。,.!?！？、]", "", norm(b).lower())
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


class Community:
    def __init__(self, store: Store):
        self.s = store
        with store._wlock:
            store.db.executescript(SCHEMA)
            cols = {r["name"] for r in store.db.execute("PRAGMA table_info(viewer)").fetchall()}
            for c, typ in (("muted_until", "REAL"), ("banned_until", "REAL"), ("strikes", "INTEGER NOT NULL DEFAULT 0")):
                if c not in cols:
                    store.db.execute(f"ALTER TABLE viewer ADD COLUMN {c} {typ}")
        self._last_chat: dict[int, float] = {}
        self.retracted: list[int] = []              # chat ids hidden after the fact (broadcast by the live ticker)
        self._lock = threading.Lock()

    # ------------------------------------------------------------ roles
    def is_admin(self, account: str | None) -> bool:
        if not account:
            return False
        acc = account.lower()
        cfg = {a.lower() for a in (settings().get("site.admins") or [])}
        return acc in cfg or bool(self.s.one("SELECT 1 FROM role WHERE account=? AND role='admin'", (acc,)))

    def grant_admin(self, ref: str) -> str:
        ref = ref.strip().lstrip("@").lower()
        row = self.s.one("SELECT account FROM viewer WHERE kind='cafeca' AND (account=? OR lower(handle)=?)", (ref, ref))
        acc = row["account"] if row else (ref if re.fullmatch(r"0x[0-9a-f]{40}", ref) else None)
        if not acc:
            raise ValueError(f"找不到 {ref}：先用 CAFECA 登入一次網站，或直接給帳戶地址")
        with self.s.tx() as c:
            c.execute("INSERT OR REPLACE INTO role(account, role, at) VALUES(?, 'admin', ?)", (acc, time.time()))
        return acc

    # ------------------------------------------------------------ who may write
    def writer_state(self, v) -> tuple[bool, str]:
        """(may write, why not)."""
        now = time.time()
        if v["banned_until"] and v["banned_until"] > now:
            return False, f"帳戶停權到 {time.strftime('%m/%d %H:%M', time.localtime(v['banned_until']))}"
        if v["muted_until"] and v["muted_until"] > now:
            return False, f"禁言到 {time.strftime('%m/%d %H:%M', time.localtime(v['muted_until']))}（仍然可以觀看）"
        return True, ""

    def set_nickname(self, viewer: int, nick: str, actor_names: list[str]) -> str:
        n = norm(nick)
        if not (NICK_MIN <= len(n) <= NICK_MAX):
            raise ValueError(f"暱稱要 {NICK_MIN}–{NICK_MAX} 個字")
        low = n.lower()
        if "@" in n or "midea" in low or "官方" in n or any(a and a in n for a in actor_names):
            raise ValueError("暱稱不能用演員姓名、@代號、「Midea」或「官方」")
        cat = rules_check(n)
        if cat:
            raise ValueError(f"暱稱不能包含{CATEGORY[cat]}內容")
        with self.s.tx() as c:
            c.execute("UPDATE viewer SET nickname=? WHERE id=?", (n, viewer))
        return n

    # ------------------------------------------------------------ chat
    def post_chat(self, v, slot: str, text: str) -> dict:
        ok, why = self.writer_state(v)
        if not ok:
            raise PermissionError(why)
        t = norm(text)
        if not t:
            raise ValueError("訊息是空的")
        if len(t) > CHAT_MAX:
            raise ValueError(f"每則最多 {CHAT_MAX} 字")
        now = time.time()
        with self._lock:
            if now - self._last_chat.get(v["id"], 0) < CHAT_GAP_S:
                raise OverflowError(f"每 {CHAT_GAP_S} 秒只能送 1 則")
            self._last_chat[v["id"]] = now
        cat = rules_check(t)
        status = "rejected" if cat else "shown"
        with self.s.tx() as c:
            cid = c.execute("INSERT INTO chat(slot, viewer, nickname, text, status, reason, at) VALUES(?,?,?,?,?,?,?)",
                            (slot, v["id"], v["nickname"] or v["handle"] or "觀眾", t, status, cat, now)).lastrowid
        if cat:
            return {"id": cid, "status": "rejected", "reason": CATEGORY[cat], "message": f"這則訊息沒有顯示：疑似{CATEGORY[cat]}內容"}
        return {"id": cid, "status": "shown", "message": None, "item": self.chat_item(self.s.one("SELECT * FROM chat WHERE id=?", (cid,)))}

    @staticmethod
    def chat_item(r) -> dict:
        return {"id": r["id"], "nickname": r["nickname"], "text": r["text"], "at": r["at"]}

    def recent_chat(self, slot: str, after: int = 0, limit: int = 50) -> list[dict]:
        rows = self.s.q("SELECT * FROM chat WHERE slot=? AND status='shown' AND id>? ORDER BY id DESC LIMIT ?", (slot, after, limit))
        return [self.chat_item(r) for r in reversed(rows)]

    def chat_since(self, after: int) -> list[dict]:
        return [self.chat_item(r) | {"slot": r["slot"]} for r in
                self.s.q("SELECT * FROM chat WHERE status='shown' AND id>? ORDER BY id LIMIT 100", (after,))]

    # ------------------------------------------------------------ wishes
    def wishes_left(self, viewer: int) -> int:
        n = self.s.one("SELECT COUNT(*) n FROM wish WHERE viewer=? AND at>?", (viewer, time.time() - 7 * 86400))["n"]
        return max(0, WISHES_PER_WEEK - n)

    def make_wish(self, v, kind: str, text: str, actors: list[str], known_actors: dict[str, str]) -> dict:
        ok, why = self.writer_state(v)
        if not ok:
            raise PermissionError(why)
        if kind not in ("topic", "cast"):
            raise ValueError("許願類型錯誤")
        t = norm(text)
        if not t:
            raise ValueError("請寫下你的願望")
        if len(t) > WISH_TOPIC_MAX:
            raise ValueError(f"最多 {WISH_TOPIC_MAX} 字")
        handles = []
        if kind == "cast":
            handles = [h.lstrip("@").lower() for h in actors][:2]
            if not handles or any(h not in known_actors for h in handles):
                raise ValueError("請從演員清單選 1–2 位")
        if self.wishes_left(v["id"]) <= 0:
            raise OverflowError(f"每週最多許 {WISHES_PER_WEEK} 個願")
        cat = rules_check(t)
        if cat:
            raise ValueError(f"這個願望不能送出：疑似{CATEGORY[cat]}內容。真人、公眾人物與實際商品品牌也不接受。")
        now = time.time()
        card = self._match_card(kind, t, handles)
        with self.s.tx() as c:
            if card is None:
                card = c.execute("INSERT INTO wish_card(kind, text, actors, created, updated) VALUES(?,?,?,?,?)",
                                 (kind, t, json.dumps(handles), now, now)).lastrowid
                merged = False
            else:
                c.execute("UPDATE wish_card SET merged=merged+1, updated=? WHERE id=?", (now, card))
                merged = True
            wid = c.execute("INSERT INTO wish(card, viewer, kind, text, actors, status, at) VALUES(?,?,?,?,?,?,?)",
                            (card, v["id"], kind, t, json.dumps(handles), "shown", now)).lastrowid
            c.execute("INSERT OR IGNORE INTO wish_support(card, viewer, at) VALUES(?,?,?)", (card, v["id"], now))
        self._check_threshold(card)
        return {"id": wid, "card": card, "merged": merged, "left": self.wishes_left(v["id"])}

    def _match_card(self, kind: str, text: str, handles: list[str]) -> int | None:
        """合併：same kind, same cast (for 演員組合) and similar wording → the same card."""
        best, best_id = 0.0, None
        for r in self.s.q("SELECT * FROM wish_card WHERE kind=? AND status NOT IN ('hidden','rejected','done')", (kind,)):
            if kind == "cast" and sorted(json.loads(r["actors"])) != sorted(handles):
                continue
            sc = similar(r["text"], text)
            if sc > best:
                best, best_id = sc, r["id"]
        return best_id if best >= float(settings().get("site.wish_merge_similarity", 0.6)) else None

    def support_wish(self, viewer: int, card: int, on: bool) -> dict:
        r = self.s.one("SELECT * FROM wish_card WHERE id=?", (card,))
        if not r or r["status"] in ("hidden", "rejected"):
            raise LookupError("找不到這張許願卡")
        with self.s.tx() as c:
            if on:
                c.execute("INSERT OR IGNORE INTO wish_support(card, viewer, at) VALUES(?,?,?)", (card, viewer, time.time()))
            else:
                c.execute("DELETE FROM wish_support WHERE card=? AND viewer=?", (card, viewer))
        self._check_threshold(card)
        return self.card_pub(self.s.one("SELECT * FROM wish_card WHERE id=?", (card,)), viewer)

    def _check_threshold(self, card: int) -> None:
        """+1 達門檻 → 送管理者核准製作（平台已有相關影片的，由主題歸納接手）."""
        n = self.supporters(card)
        if n >= int(settings().get("site.wish_threshold", 30)):
            r = self.s.one("SELECT * FROM wish_card WHERE id=?", (card,))
            if r and r["status"] == "open":
                self.open_review("wish", str(card), f"許願 +1 達 {n}：{r['text']}")

    def supporters(self, card: int) -> int:
        return int(self.s.one("SELECT COUNT(*) n FROM wish_support WHERE card=?", (card,))["n"])

    def card_pub(self, r, viewer: int | None) -> dict:
        n = self.supporters(r["id"])
        th = int(settings().get("site.wish_threshold", 30))
        mine = bool(viewer and self.s.one("SELECT 1 FROM wish_support WHERE card=? AND viewer=?", (r["id"], viewer)))
        return {"id": r["id"], "kind": r["kind"], "text": r["text"], "actors": json.loads(r["actors"]), "status": r["status"],
                "supporters": n, "threshold": th, "progress": min(1.0, n / th), "merged": r["merged"], "mine": mine,
                "note": r["note"], "project": r["project"]}

    def wall(self, viewer: int | None, status: str | None = None, limit: int = 60) -> list[dict]:
        rows = self.s.q("SELECT c.*, (SELECT COUNT(*) FROM wish_support s WHERE s.card=c.id) n FROM wish_card c "
                        "WHERE c.status NOT IN ('hidden','rejected')" + (" AND c.status=?" if status else "") +
                        " ORDER BY n DESC, c.updated DESC LIMIT ?", ((status, limit) if status else (limit,)))
        return [self.card_pub(r, viewer) for r in rows]

    def open_wishes_for_topics(self) -> list[dict]:
        return [dict(r) for r in self.s.q("SELECT * FROM wish_card WHERE status IN ('open','topic')")]

    def set_card_status(self, card: int, status: str, note: str | None = None, project: str | None = None) -> None:
        with self.s.tx() as c:
            c.execute("UPDATE wish_card SET status=?, note=COALESCE(?, note), project=COALESCE(?, project), updated=? WHERE id=?",
                      (status, note, project, time.time(), card))

    # ------------------------------------------------------------ questions to actors
    def questions_left(self, viewer: int) -> int:
        n = self.s.one("SELECT COUNT(*) n FROM question WHERE viewer=? AND at>?", (viewer, time.time() - 86400))["n"]
        return max(0, QUESTIONS_PER_DAY - n)

    def ask(self, v, actor: str, text: str) -> dict:
        ok, why = self.writer_state(v)
        if not ok:
            raise PermissionError(why)
        t = norm(text)
        if not t:
            raise ValueError("請寫下你的問題")
        if len(t) > QUESTION_MAX:
            raise ValueError(f"每題最多 {QUESTION_MAX} 字")
        if self.questions_left(v["id"]) <= 0:
            raise OverflowError(f"每天最多問 {QUESTIONS_PER_DAY} 題")
        cat = rules_check(t)
        if cat:
            raise ValueError(f"這個問題不能送出：疑似{CATEGORY[cat]}內容")
        with self.s.tx() as c:
            qid = c.execute("INSERT INTO question(actor, viewer, text, status, at) VALUES(?,?,?,?,?)",
                            (actor, v["id"], t, "shown", time.time())).lastrowid
            c.execute("INSERT OR IGNORE INTO question_support(question, viewer, at) VALUES(?,?,?)", (qid, v["id"], time.time()))
        return {"id": qid, "left": self.questions_left(v["id"])}

    def support_question(self, viewer: int, qid: int, on: bool) -> int:
        r = self.s.one("SELECT * FROM question WHERE id=? AND status='shown'", (qid,))
        if not r:
            raise LookupError("找不到這個問題")
        with self.s.tx() as c:
            if on:
                c.execute("INSERT OR IGNORE INTO question_support(question, viewer, at) VALUES(?,?,?)", (qid, viewer, time.time()))
            else:
                c.execute("DELETE FROM question_support WHERE question=? AND viewer=?", (qid, viewer))
        return int(self.s.one("SELECT COUNT(*) n FROM question_support WHERE question=?", (qid,))["n"])

    def questions(self, actor: str, viewer: int | None, order: str = "top", limit: int = 30) -> list[dict]:
        sql = ("SELECT q.*, (SELECT COUNT(*) FROM question_support s WHERE s.question=q.id) n, v.nickname, v.handle "
               "FROM question q JOIN viewer v ON v.id=q.viewer WHERE q.actor=? AND q.status='shown'")
        if order == "answered":
            sql += " AND q.answer_video IS NOT NULL ORDER BY q.picked DESC"
        elif order == "new":
            sql += " ORDER BY q.at DESC"
        else:
            sql += " ORDER BY n DESC, q.at DESC"
        out = []
        for r in self.s.q(sql + " LIMIT ?", (actor, limit)):
            mine = viewer is not None and r["viewer"] == viewer
            supported = bool(viewer and self.s.one("SELECT 1 FROM question_support WHERE question=? AND viewer=?", (r["id"], viewer)))
            out.append({"id": r["id"], "text": r["text"], "supporters": int(r["n"]), "by": r["nickname"] or r["handle"] or "觀眾",
                        "at": r["at"], "mine": mine, "supported": supported, "picked": bool(r["picked"]),
                        "answer_video": r["answer_video"],
                        # 文字回覆只有提問者看得到，除非該題被選為影片回答
                        "reply": r["reply"] if (mine or r["picked"]) and r["reply_status"] == "ready" else None,
                        "reply_status": r["reply_status"] if mine else None})
        return out

    def my_questions(self, viewer: int, actor: str) -> list[dict]:
        return [q for q in self.questions(actor, viewer, order="new", limit=50) if q["mine"]]

    # ------------------------------------------------------------ reports & reviews
    TABLE = {"chat": "chat", "wish": "wish_card", "question": "question"}

    def report(self, viewer: int, kind: str, target: int, reason: str | None) -> dict:
        if kind not in self.TABLE:
            raise ValueError("無法檢舉這個項目")
        if not self.s.one(f"SELECT 1 FROM {self.TABLE[kind]} WHERE id=?", (target,)):
            raise LookupError("找不到")
        with self.s.tx() as c:
            c.execute("INSERT OR IGNORE INTO report(kind, target, viewer, reason, at) VALUES(?,?,?,?,?)",
                      (kind, target, viewer, (reason or "")[:40], time.time()))
        n = int(self.s.one("SELECT COUNT(DISTINCT viewer) n FROM report WHERE kind=? AND target=?", (kind, target))["n"])
        hidden = False
        if n >= REPORTS_TO_HIDE:
            self.hide(kind, target, "reported")
            self.open_review("report", f"{kind}:{target}", f"{n} 位觀眾檢舉")
            hidden = True
        return {"reports": n, "hidden": hidden}

    def hide(self, kind: str, target: int, why: str) -> None:
        with self.s.tx() as c:
            c.execute(f"UPDATE {self.TABLE[kind]} SET status='hidden'" + (", reason=?" if kind != "wish" else ", note=?") +
                      " WHERE id=?", (why, target))
        if kind == "chat":
            self.retracted.append(target)

    def restore(self, kind: str, target: int) -> None:
        with self.s.tx() as c:
            c.execute(f"UPDATE {self.TABLE[kind]} SET status=? WHERE id=?", ("open" if kind == "wish" else "shown", target))

    def open_review(self, kind: str, target: str, summary: str) -> None:
        with self.s.tx() as c:
            c.execute("INSERT INTO review(kind, target, summary, created) VALUES(?,?,?,?) "
                      "ON CONFLICT(kind, target) DO UPDATE SET status='open', summary=excluded.summary, created=excluded.created",
                      (kind, target, summary, time.time()))

    def reviews(self, status: str = "open") -> list[dict]:
        out = []
        for r in self.s.q("SELECT * FROM review WHERE status=? ORDER BY created", (status,)):
            d = dict(r)
            d["detail"] = self.review_detail(r["kind"], r["target"])
            out.append(d)
        return out

    def review_detail(self, kind: str, target: str) -> dict:
        if kind == "report":
            k, i = target.split(":")
            row = self.s.one(f"SELECT * FROM {self.TABLE[k]} WHERE id=?", (int(i),))
            reasons = [x["reason"] for x in self.s.q("SELECT reason FROM report WHERE kind=? AND target=?", (k, int(i)))]
            text = row["text"] if row else ""
            author = row["viewer"] if row and "viewer" in row.keys() else None
            return {"kind": k, "id": int(i), "text": text, "reasons": reasons, "author": author}
        if kind == "wish":
            row = self.s.one("SELECT * FROM wish_card WHERE id=?", (int(target),))
            return self.card_pub(row, None) if row else {}
        return {}

    def resolve(self, rid: int, decision: str, by: str, note: str = "") -> dict:
        r = self.s.one("SELECT * FROM review WHERE id=?", (rid,))
        if not r or r["status"] != "open":
            raise LookupError("這個審核項目已處理")
        out: dict[str, Any] = {}
        if r["kind"] == "report":
            k, i = r["target"].split(":")
            if decision == "violation":
                row = self.s.one(f"SELECT * FROM {self.TABLE[k]} WHERE id=?", (int(i),))
                if row is not None and "viewer" in row.keys():
                    out["penalty"] = self.penalize(row["viewer"], f"{k} #{i}", by)
            elif decision == "restore":
                self.restore(k, int(i))
                with self.s.tx() as c:                      # a restored item starts with a clean slate
                    c.execute("DELETE FROM report WHERE kind=? AND target=?", (k, int(i)))
        elif r["kind"] == "wish":
            if decision == "approve":
                self.set_card_status(int(r["target"]), "producing", note or "管理者核准製作")
            elif decision == "reject":
                self.set_card_status(int(r["target"]), "open", note or "暫不製作")
        elif r["kind"] == "listing":
            out["listing"] = {"target": r["target"], "decision": decision}
        with self.s.tx() as c:
            c.execute("UPDATE review SET status='resolved', decision=?, note=?, by=?, resolved=? WHERE id=?",
                      (decision, note, by, time.time(), rid))
        return out

    def penalize(self, viewer: int, reason: str, by: str) -> dict:
        """第一次提醒，第二次禁言 24 小時，第三次起停權 30 天。"""
        v = self.s.one("SELECT strikes FROM viewer WHERE id=?", (viewer,))
        strikes = int(v["strikes"] or 0) + 1 if v else 1
        now = time.time()
        level, until, col = ("warning", None, None) if strikes == 1 else (("mute", now + 86400, "muted_until") if strikes == 2
                                                                          else ("ban", now + 30 * 86400, "banned_until"))
        with self.s.tx() as c:
            c.execute("UPDATE viewer SET strikes=?" + (f", {col}=?" if col else "") + " WHERE id=?",
                      (strikes, until, viewer) if col else (strikes, viewer))
            c.execute("INSERT INTO penalty(viewer, level, until, reason, by, at) VALUES(?,?,?,?,?,?)",
                      (viewer, strikes, until, reason, by, now))
        return {"level": level, "until": until, "strikes": strikes}

    def notices(self, viewer: int) -> list[dict]:
        return [dict(r) for r in self.s.q("SELECT level, until, reason, at FROM penalty WHERE viewer=? ORDER BY at DESC LIMIT 5", (viewer,))]

    # ------------------------------------------------------------ AI pass (background)
    def pending_ai(self, limit: int = 20) -> dict[str, list]:
        return {
            "chat": [dict(r) for r in self.s.q("SELECT id, text FROM chat WHERE status='shown' AND checked=0 ORDER BY id LIMIT ?", (limit,))],
            "wish": [dict(r) for r in self.s.q("SELECT id, card, text FROM wish WHERE status='shown' AND checked=0 ORDER BY id LIMIT ?", (limit,))],
            "question": [dict(r) for r in self.s.q("SELECT id, actor, text FROM question WHERE status='shown' AND checked=0 ORDER BY id LIMIT ?", (limit,))],
            "replies": [dict(r) for r in self.s.q("SELECT id, actor, text FROM question WHERE status='shown' AND reply_status='pending' "
                                                  "AND checked=1 ORDER BY id LIMIT ?", (limit,))],
        }

    def apply_ai(self, kind: str, rid: int, category: str | None) -> None:
        table = {"chat": "chat", "wish": "wish", "question": "question"}[kind]
        with self.s.tx() as c:
            c.execute(f"UPDATE {table} SET checked=1 WHERE id=?", (rid,))
        if category in CATEGORY:
            if kind == "wish":
                card = self.s.one("SELECT card FROM wish WHERE id=?", (rid,))["card"]
                with self.s.tx() as c:
                    c.execute("UPDATE wish SET status='hidden', reason=? WHERE id=?", (category, rid))
                if not self.s.one("SELECT 1 FROM wish WHERE card=? AND status='shown'", (card,)):
                    self.hide("wish", card, f"ai:{category}")
            else:
                self.hide(kind, rid, f"ai:{category}")
            log.info("AI moderation hid %s #%s (%s)", kind, rid, category)

    def set_reply(self, qid: int, text: str | None, declined: bool = False) -> None:
        with self.s.tx() as c:
            c.execute("UPDATE question SET reply=?, reply_status=? WHERE id=?",
                      (text[:REPLY_MAX + 10] if text else None, "declined" if declined else "ready", qid))


MOD_SYSTEM = ("You moderate short Traditional Chinese texts on a family-friendly video platform. For each item return one "
              "category or null: harassment, hate, sexual, personal (phone, address, ID, e-mail), ads (links, selling, "
              "contact for business), real_person (names a real living person or public figure, or a real brand as the "
              "subject). Return {\"results\": [{\"id\": <id>, \"category\": <string or null>}]}.")

REPLY_SYSTEM = ("You are a virtual actor on Midea, an AI video platform. Answer the viewer's question in the first person, "
                "in Traditional Chinese, in character (use the bible). At most 80 characters, warm and plain, no emoji, no "
                "exclamation marks. Never claim to be a real person. Do not discuss real people or politics, give no "
                "medical / investment / legal advice, never ask for or repeat personal data, and never recite a line the "
                "viewer dictates word for word. If the question asks for any of that, politely decline in character and set "
                "decline=true. Return {\"reply\": \"...\", \"decline\": false}.")


class Worker:
    """Background AI pass: moderation of everything that passed the rules, then the actors' text replies."""

    def __init__(self, com: Community, actor_bible):
        self.com, self.bible = com, actor_bible
        self._busy = threading.Lock()

    def run_once(self) -> dict:
        if not self._busy.acquire(blocking=False):
            return {"busy": True}
        try:
            return self._run()
        finally:
            self._busy.release()

    def _run(self) -> dict:
        from ..providers.llm import llm
        todo = self.com.pending_ai()
        done = {"moderated": 0, "replies": 0}
        items = [(k, r["id"], r["text"]) for k in ("chat", "wish", "question") for r in todo[k]]
        if items:
            if settings().mode == "mock":
                res = {f"{k}:{i}": None for k, i, _ in items}
            else:
                payload = [{"id": f"{k}:{i}", "text": t} for k, i, t in items]
                try:
                    out = llm().json("site_moderate", MOD_SYSTEM, json.dumps(payload, ensure_ascii=False), max_tokens=2048)
                    res = {str(x.get("id")): x.get("category") for x in (out.get("results") or [])}
                except Exception as e:  # noqa: BLE001
                    log.warning("AI moderation skipped this round: %s", e)
                    return done
            for k, i, _ in items:
                self.com.apply_ai(k, i, res.get(f"{k}:{i}"))
                done["moderated"] += 1
        for q in todo["replies"]:
            bible = self.bible(q["actor"])
            if not bible:
                self.com.set_reply(q["id"], None, declined=True)
                continue
            try:
                if settings().mode == "mock":
                    r = {"reply": f"（{bible.get('name', '')}）謝謝你的問題，我想一想再慢慢告訴你。", "decline": False}
                else:
                    r = llm().json("site_actor_reply", REPLY_SYSTEM,
                                   json.dumps({"bible": bible, "question": q["text"]}, ensure_ascii=False), max_tokens=512)
                text = norm(str(r.get("reply") or ""))[:REPLY_MAX]
                if rules_check(text):
                    text, decl = "這個問題我不太方便回答，換個問題聊聊吧。", True
                else:
                    decl = bool(r.get("decline"))
                self.com.set_reply(q["id"], text or None, declined=decl or not text)
                done["replies"] += 1
            except Exception as e:  # noqa: BLE001
                log.warning("actor reply failed for question %s: %s", q["id"], e)
                break
        return done
