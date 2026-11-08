"""Audience records (SQLite). One connection per thread, WAL, every write in a short transaction.

Tables follow the plan's data model (§ 資料模型與 API). Phase 1 uses: viewer, session, auth_nonce, reaction,
favorite, view, live_reaction (5-second aggregates only), poll / poll_vote (the 「觀眾決定」 slot) and
slot_vote (the end-of-slot 「下週還想看嗎」 question).
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS viewer (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,                 -- device | cafeca
  device TEXT UNIQUE,                 -- random browser id (anonymous)
  account TEXT UNIQUE,                -- CAFECA identity contract address (lower-case)
  handle TEXT, nickname TEXT,
  kyc_level INTEGER,                  -- effectiveLevel at last sign-in; NULL = not shared
  status TEXT NOT NULL DEFAULT 'ok',  -- ok | muted | banned
  created REAL NOT NULL, seen REAL
);
CREATE TABLE IF NOT EXISTS session (
  token_hash TEXT PRIMARY KEY, viewer INTEGER NOT NULL, created REAL NOT NULL, expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_nonce (
  nonce TEXT PRIMARY KEY, device TEXT NOT NULL, created REAL NOT NULL, used REAL
);
CREATE TABLE IF NOT EXISTS reaction (
  viewer INTEGER NOT NULL, video TEXT NOT NULL, kind TEXT NOT NULL, reason TEXT,
  anon INTEGER NOT NULL, counted INTEGER NOT NULL DEFAULT 1, src TEXT, at REAL NOT NULL,
  PRIMARY KEY (viewer, video)
);
CREATE INDEX IF NOT EXISTS reaction_video ON reaction(video);
CREATE TABLE IF NOT EXISTS favorite (
  viewer INTEGER NOT NULL, video TEXT NOT NULL, at REAL NOT NULL, PRIMARY KEY (viewer, video)
);
CREATE TABLE IF NOT EXISTS view (
  viewer INTEGER NOT NULL, video TEXT NOT NULL, day TEXT NOT NULL, seconds REAL NOT NULL DEFAULT 0,
  completed INTEGER NOT NULL DEFAULT 0, at REAL NOT NULL, PRIMARY KEY (viewer, video, day)
);
CREATE INDEX IF NOT EXISTS view_at ON view(at);
CREATE TABLE IF NOT EXISTS live_reaction (
  slot TEXT NOT NULL, video TEXT NOT NULL, bucket INTEGER NOT NULL, kind TEXT NOT NULL, n INTEGER NOT NULL,
  PRIMARY KEY (slot, video, bucket, kind)
);
CREATE TABLE IF NOT EXISTS poll (
  id TEXT PRIMARY KEY, slot TEXT NOT NULL, title TEXT NOT NULL, options TEXT NOT NULL,
  opens REAL NOT NULL, closes REAL NOT NULL, winner TEXT, closed REAL
);
CREATE TABLE IF NOT EXISTS poll_vote (
  poll TEXT NOT NULL, viewer INTEGER NOT NULL, option TEXT NOT NULL, kyc_level INTEGER, at REAL NOT NULL,
  PRIMARY KEY (poll, viewer)
);
CREATE TABLE IF NOT EXISTS slot_vote (
  slot TEXT NOT NULL, program TEXT NOT NULL, viewer INTEGER NOT NULL, want INTEGER NOT NULL, kyc_level INTEGER,
  at REAL NOT NULL, PRIMARY KEY (slot, viewer)
);
CREATE INDEX IF NOT EXISTS slot_vote_program ON slot_vote(program);
"""

SESSION_DAYS = 30


def kyc_bucket(level: int | None) -> str:
    """Votes are open to every CAFECA identity; results are reported per KYC level as well."""
    if level is None:
        return "unknown"
    return str(min(int(level), 3)) + ("+" if int(level) >= 3 else "")


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._wlock = threading.Lock()
        with self._wlock:
            self.db.executescript(SCHEMA)

    # ---------------------------------------------------------------- plumbing
    @property
    def db(self) -> sqlite3.Connection:
        c = getattr(self._local, "c", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=10, check_same_thread=False, isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA foreign_keys=ON")
            self._local.c = c
        return c

    def tx(self):
        store = self

        class _Tx:
            def __enter__(self_inner):
                store._wlock.acquire()
                store.db.execute("BEGIN IMMEDIATE")
                return store.db

            def __exit__(self_inner, et, ev, tb):
                try:
                    store.db.execute("ROLLBACK" if et else "COMMIT")
                finally:
                    store._wlock.release()
                return False
        return _Tx()

    def q(self, sql: str, args: Iterable[Any] = ()) -> list[sqlite3.Row]:
        return self.db.execute(sql, tuple(args)).fetchall()

    def one(self, sql: str, args: Iterable[Any] = ()) -> sqlite3.Row | None:
        return self.db.execute(sql, tuple(args)).fetchone()

    # ---------------------------------------------------------------- viewers & sessions
    def device_viewer(self, device: str) -> int:
        r = self.one("SELECT id FROM viewer WHERE device=?", (device,))
        if r:
            return int(r["id"])
        with self.tx() as c:
            r = c.execute("SELECT id FROM viewer WHERE device=?", (device,)).fetchone()
            if r:
                return int(r["id"])
            return int(c.execute("INSERT INTO viewer(kind, device, created, seen) VALUES('device', ?, ?, ?)",
                                 (device, time.time(), time.time())).lastrowid)

    def sign_in(self, account: str, *, handle: str | None, kyc_level: int | None, device: str | None) -> tuple[int, str]:
        """Create/refresh the CAFECA viewer, merge this browser's anonymous records into it, open a session."""
        account = account.lower()
        now = time.time()
        with self.tx() as c:
            r = c.execute("SELECT id FROM viewer WHERE account=?", (account,)).fetchone()
            if r:
                vid = int(r["id"])
                c.execute("UPDATE viewer SET handle=COALESCE(?, handle), nickname=COALESCE(nickname, ?), kyc_level=?, seen=? WHERE id=?",
                          (handle, handle, kyc_level, now, vid))
            else:
                vid = int(c.execute("INSERT INTO viewer(kind, account, handle, nickname, kyc_level, created, seen) "
                                    "VALUES('cafeca', ?, ?, ?, ?, ?, ?)", (account, handle, handle, kyc_level, now, now)).lastrowid)
            if device:
                d = c.execute("SELECT id FROM viewer WHERE device=? AND kind='device'", (device,)).fetchone()
                if d:
                    did = int(d["id"])
                    # the account's own choice wins when both reacted to the same video
                    c.execute("UPDATE OR IGNORE reaction SET viewer=?, anon=0 WHERE viewer=?", (vid, did))
                    c.execute("DELETE FROM reaction WHERE viewer=?", (did,))
                    c.execute("UPDATE OR IGNORE view SET viewer=? WHERE viewer=?", (vid, did))
                    c.execute("DELETE FROM view WHERE viewer=?", (did,))
            token = secrets.token_urlsafe(32)
            c.execute("INSERT INTO session(token_hash, viewer, created, expires) VALUES(?, ?, ?, ?)",
                      (_h(token), vid, now, now + SESSION_DAYS * 86400))
        return vid, token

    def session_viewer(self, token: str | None) -> sqlite3.Row | None:
        if not token:
            return None
        return self.one("SELECT v.* FROM session s JOIN viewer v ON v.id=s.viewer WHERE s.token_hash=? AND s.expires>?",
                        (_h(token), time.time()))

    def sign_out(self, token: str | None) -> None:
        if token:
            with self.tx() as c:
                c.execute("DELETE FROM session WHERE token_hash=?", (_h(token),))

    def new_nonce(self, device: str) -> str:
        n = secrets.token_urlsafe(24)
        with self.tx() as c:
            c.execute("DELETE FROM auth_nonce WHERE created<?", (time.time() - 3600,))
            c.execute("INSERT INTO auth_nonce(nonce, device, created) VALUES(?, ?, ?)", (n, device, time.time()))
        return n

    def take_nonce(self, nonce: str, device: str, max_age: float = 600) -> bool:
        """Single use, bound to the browser that asked for it; invalidated before the signature is checked."""
        with self.tx() as c:
            r = c.execute("SELECT * FROM auth_nonce WHERE nonce=?", (nonce,)).fetchone()
            if not r or r["used"] or r["device"] != device or time.time() - r["created"] > max_age:
                return False
            c.execute("UPDATE auth_nonce SET used=? WHERE nonce=?", (time.time(), nonce))
        return True

    # ---------------------------------------------------------------- reactions / favorites / views
    def set_reaction(self, viewer: int, video: str, kind: str, reason: str | None, *, anon: bool, src: str | None,
                     burst_limit: int = 30, window_s: float = 600) -> dict:
        now = time.time()
        counted = 1
        if anon and src:
            n = self.one("SELECT COUNT(*) n FROM reaction WHERE src=? AND anon=1 AND at>?", (src, now - window_s))["n"]
            counted = 0 if n >= burst_limit else 1      # 異常偵測：同一來源短時間大量匿名反應，超過的部分不計分
        with self.tx() as c:
            c.execute("INSERT INTO reaction(viewer, video, kind, reason, anon, counted, src, at) VALUES(?,?,?,?,?,?,?,?) "
                      "ON CONFLICT(viewer, video) DO UPDATE SET kind=excluded.kind, reason=excluded.reason, at=excluded.at",
                      (viewer, video, kind, reason, int(anon), counted, src, now))
        return {"kind": kind, "reason": reason}

    def clear_reaction(self, viewer: int, video: str) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM reaction WHERE viewer=? AND video=?", (viewer, video))

    def my_reaction(self, viewer: int, video: str) -> str | None:
        r = self.one("SELECT kind FROM reaction WHERE viewer=? AND video=?", (viewer, video))
        return r["kind"] if r else None

    def reaction_totals(self, since: float = 0) -> dict[str, dict[str, dict[str, int]]]:
        """{video: {"auth": {kind: n}, "anon": {kind: n}}} — only counted rows."""
        out: dict[str, dict[str, dict[str, int]]] = {}
        for r in self.q("SELECT video, kind, anon, COUNT(*) n FROM reaction WHERE counted=1 AND at>=? GROUP BY video, kind, anon", (since,)):
            out.setdefault(r["video"], {"auth": {}, "anon": {}})["anon" if r["anon"] else "auth"][r["kind"]] = int(r["n"])
        return out

    def viewer_reactions(self, viewer: int) -> dict[str, str]:
        return {r["video"]: r["kind"] for r in self.q("SELECT video, kind FROM reaction WHERE viewer=?", (viewer,))}

    def set_favorite(self, viewer: int, video: str, on: bool) -> None:
        with self.tx() as c:
            if on:
                c.execute("INSERT OR IGNORE INTO favorite(viewer, video, at) VALUES(?,?,?)", (viewer, video, time.time()))
            else:
                c.execute("DELETE FROM favorite WHERE viewer=? AND video=?", (viewer, video))

    def favorites(self, viewer: int) -> list[str]:
        return [r["video"] for r in self.q("SELECT video FROM favorite WHERE viewer=? ORDER BY at DESC", (viewer,))]

    def record_view(self, viewer: int, video: str, seconds: float, completed: bool, day: str) -> None:
        """同一人同一部每天計 1 次 — one row per (viewer, video, day); completion is sticky."""
        with self.tx() as c:
            c.execute("INSERT INTO view(viewer, video, day, seconds, completed, at) VALUES(?,?,?,?,?,?) "
                      "ON CONFLICT(viewer, video, day) DO UPDATE SET seconds=MAX(seconds, excluded.seconds), "
                      "completed=MAX(completed, excluded.completed), at=excluded.at",
                      (viewer, video, day, float(seconds), int(completed), time.time()))

    def completed_views(self, since: float, until: float | None = None) -> dict[str, int]:
        until = until or time.time() + 1
        return {r["video"]: int(r["n"]) for r in self.q(
            "SELECT video, COUNT(*) n FROM view WHERE completed=1 AND at>=? AND at<? GROUP BY video", (since, until))}

    # ---------------------------------------------------------------- live
    def add_live_buckets(self, rows: list[tuple[str, str, int, str, int]]) -> None:
        if not rows:
            return
        with self.tx() as c:
            c.executemany("INSERT INTO live_reaction(slot, video, bucket, kind, n) VALUES(?,?,?,?,?) "
                          "ON CONFLICT(slot, video, bucket, kind) DO UPDATE SET n=n+excluded.n", rows)

    def live_buckets(self, video: str) -> dict[int, int]:
        return {int(r["bucket"]): int(r["n"]) for r in self.q(
            "SELECT bucket, SUM(n) n FROM live_reaction WHERE video=? GROUP BY bucket", (video,))}

    def live_heat(self, since_slot_prefix: str = "") -> dict[str, int]:
        return {r["video"]: int(r["n"]) for r in self.q(
            "SELECT video, SUM(n) n FROM live_reaction WHERE slot>=? GROUP BY video", (since_slot_prefix,))}

    # ---------------------------------------------------------------- polls
    def upsert_poll(self, pid: str, slot: str, title: str, options_json: str, opens: float, closes: float) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO poll(id, slot, title, options, opens, closes) VALUES(?,?,?,?,?,?) "
                      "ON CONFLICT(id) DO NOTHING", (pid, slot, title, options_json, opens, closes))

    def poll(self, pid: str) -> sqlite3.Row | None:
        return self.one("SELECT * FROM poll WHERE id=?", (pid,))

    def open_poll(self, now: float) -> sqlite3.Row | None:
        return self.one("SELECT * FROM poll WHERE opens<=? AND closes>? ORDER BY closes LIMIT 1", (now, now))

    def latest_poll(self) -> sqlite3.Row | None:
        return self.one("SELECT * FROM poll ORDER BY closes DESC LIMIT 1")

    def vote(self, pid: str, viewer: int, option: str, kyc_level: int | None) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO poll_vote(poll, viewer, option, kyc_level, at) VALUES(?,?,?,?,?) "
                      "ON CONFLICT(poll, viewer) DO UPDATE SET option=excluded.option, kyc_level=excluded.kyc_level, at=excluded.at",
                      (pid, viewer, option, kyc_level, time.time()))

    def my_vote(self, pid: str, viewer: int) -> str | None:
        r = self.one("SELECT option FROM poll_vote WHERE poll=? AND viewer=?", (pid, viewer))
        return r["option"] if r else None

    def tally(self, pid: str) -> dict:
        total: dict[str, int] = {}
        by_kyc: dict[str, dict[str, int]] = {}
        for r in self.q("SELECT option, kyc_level, COUNT(*) n FROM poll_vote WHERE poll=? GROUP BY option, kyc_level", (pid,)):
            total[r["option"]] = total.get(r["option"], 0) + int(r["n"])
            b = by_kyc.setdefault(kyc_bucket(r["kyc_level"]), {})
            b[r["option"]] = b.get(r["option"], 0) + int(r["n"])
        return {"total": total, "votes": sum(total.values()), "by_kyc": by_kyc}

    def close_poll(self, pid: str, winner: str) -> None:
        with self.tx() as c:
            c.execute("UPDATE poll SET winner=?, closed=? WHERE id=? AND winner IS NULL", (winner, time.time(), pid))

    def slot_vote(self, slot: str, program: str, viewer: int, want: bool, kyc_level: int | None) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO slot_vote(slot, program, viewer, want, kyc_level, at) VALUES(?,?,?,?,?,?) "
                      "ON CONFLICT(slot, viewer) DO UPDATE SET want=excluded.want, at=excluded.at",
                      (slot, program, viewer, int(want), kyc_level, time.time()))

    def my_slot_vote(self, slot: str, viewer: int) -> bool | None:
        r = self.one("SELECT want FROM slot_vote WHERE slot=? AND viewer=?", (slot, viewer))
        return None if r is None else bool(r["want"])

    def slot_tally(self, *, slot: str | None = None, program: str | None = None, since: float = 0) -> dict:
        where, args = ["at>=?"], [since]
        if slot:
            where.append("slot=?"); args.append(slot)
        if program:
            where.append("program=?"); args.append(program)
        want = no = 0
        by_kyc: dict[str, dict[str, int]] = {}
        for r in self.q(f"SELECT want, kyc_level, COUNT(*) n FROM slot_vote WHERE {' AND '.join(where)} GROUP BY want, kyc_level", args):
            k = "want" if r["want"] else "no"
            if r["want"]:
                want += int(r["n"])
            else:
                no += int(r["n"])
            b = by_kyc.setdefault(kyc_bucket(r["kyc_level"]), {"want": 0, "no": 0})
            b[k] += int(r["n"])
        return {"want": want, "no": no, "votes": want + no, "by_kyc": by_kyc}


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
