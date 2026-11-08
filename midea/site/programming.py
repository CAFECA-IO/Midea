"""Official channel schedule, topics, most-watched and the audience signals that feed them.

Timing (Asia/Taipei):
- Next week's schedule is published every Monday 09:00. Saturday 21:30 of that week is the 「觀眾決定」 slot: three
  candidates go up for a vote the same moment, voting closes Thursday 24:00, the winner fills the slot.
- Topics are regrouped at 02:00 / 08:00 / 14:00 / 20:00.
- 最多人看 counts completed views only, recomputed at the top of each hour.

Signal weights come from the plan (§ 反饋如何影響排程): completed view 1, 喜歡 +2, 想看更多這類 +3, 不感興趣 only hides
the video for that viewer; anonymous reactions may make up at most 30 % of a video's score. A program whose
end-of-slot question got more 「想」 than 「不想」 (at least `rerun_min_votes` answers) is rerun next week.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ..config import settings
from ..log import get_logger
from .catalog import Catalog, Video, fmt_dur
from .store import Store

log = get_logger("site.programming")
TZ = ZoneInfo("Asia/Taipei")
SLOT_S = 1800
PRIME = (20, 24)                       # 每晚主打時段 20:00–24:00
AUDIENCE_SLOT = (5, 21, 30)            # 週六 21:30（weekday 5）
WEEKDAYS = "一二三四五六日"
WEIGHTS = {"view": 1.0, "like": 2.0, "more": 3.0}
ANON_SHARE = 0.30

# fixed on-screen wording for every place the audience changed something (design system § 文案)
INFLUENCE = {
    "poll": "觀眾投票選出",
    "rerun": "觀眾想再看",
    "highlight": "觀眾最有反應的片段",
    "polling": "觀眾決定 · 投票中",
    "wish": "依觀眾許願",
}


def now_local(ts: float | None = None) -> datetime:
    return datetime.fromtimestamp(ts if ts is not None else time.time(), TZ)


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def day_label(dt: datetime) -> str:
    return f"{dt.month}/{dt.day}（{WEEKDAYS[dt.weekday()]}）"


def hm(ts: float) -> str:
    return now_local(ts).strftime("%H:%M")


def slot_range(start: float) -> str:
    end = start + SLOT_S
    e = hm(end)
    return f"{hm(start)}–{'24:00' if e == '00:00' else e}"


# ---------------------------------------------------------------------------------------------- scoring
def video_scores(store: Store, cat: Catalog, since: float = 0) -> dict[str, float]:
    views = store.completed_views(since)
    reacts = store.reaction_totals(since)
    out: dict[str, float] = {}
    for vid in cat.refresh().videos:
        base = views.get(vid, 0) * WEIGHTS["view"]
        r = reacts.get(vid, {"auth": {}, "anon": {}})
        auth = sum(WEIGHTS.get(k, 0) * n for k, n in r["auth"].items())
        anon = sum(WEIGHTS.get(k, 0) * n for k, n in r["anon"].items())
        # anonymous part ≤ 30 % of the total:  anon ≤ 0.3 (base + auth + anon)  ⇔  anon ≤ 3/7 (base + auth)
        anon = min(anon, (base + auth) * ANON_SHARE / (1 - ANON_SHARE))
        out[vid] = base + auth + anon
    return out


def work_scores(cat: Catalog, vscores: dict[str, float], heat: dict[str, int] | None = None) -> dict[str, float]:
    out: dict[str, float] = {}
    for v in cat.refresh().videos.values():
        out[v.work] = out.get(v.work, 0) + vscores.get(v.id, 0) + 0.1 * (heat or {}).get(v.id, 0)
    return out


# ---------------------------------------------------------------------------------------------- topics
@dataclass
class Topic:
    key: str
    title: str
    works: list[str]               # primary video ids, best first
    note: str = ""                 # why this grouping exists ("同一位演員" …)

    def to(self) -> dict:
        return {"key": self.key, "title": self.title, "videos": self.works, "note": self.note}


def _bigrams(t: str) -> set[str]:
    t = "".join(ch for ch in (t or "").lower() if ch.isalnum())
    return {t[i:i + 2] for i in range(len(t) - 1)}


def wish_topics(cat: Catalog, wishes: list[dict]) -> list[tuple[dict, list[Video]]]:
    """Wish cards the platform can already answer with ≥ 2 existing works."""
    works = [v for v in cat.works() if not v.work.startswith("actor:")]
    out = []
    for w in wishes:
        if w["kind"] == "cast":
            hs = set(json.loads(w["actors"]) if isinstance(w["actors"], str) else w["actors"])
            vs = [v for v in works if hs and hs <= set(v.actors)]
        else:
            want = _bigrams(w["text"])
            vs = [v for v in works if len(want & _bigrams(" ".join([v.title, v.description, v.kind]))) >= 2]
        if len(vs) >= 2:
            out.append((w, vs))
    return out


def build_topics(cat: Catalog, wscores: dict[str, float], wishes: list[dict] | None = None) -> list[Topic]:
    works = cat.works()

    def ranked(vs: list[Video]) -> list[str]:
        return [v.id for v in sorted(vs, key=lambda v: (-wscores.get(v.work, 0), -v.created))]

    topics: list[Topic] = []
    for w, vs in wish_topics(cat, wishes or []):
        topics.append(Topic(f"wish-{w['id']}", w["text"], ranked(vs), "依觀眾許願"))
    names = cat.names()
    for h, name in names.items():
        vs = [v for v in works if h in v.actors and not v.work.startswith("actor:")]
        intro = [v for v in works if v.work == f"actor:{h}"]
        if len(vs) + len(intro) >= 2:
            topics.append(Topic(f"actor-{h}", f"{name} @{h} 的作品", ranked(vs) + [v.id for v in intro], "同一位演員"))
    by_kind: dict[str, list[Video]] = {}
    for v in works:
        by_kind.setdefault(v.kind, []).append(v)
    labels = {"廣告": "廣告與品牌短片", "短片": "AI 短片", "動畫": "動畫解說", "演員自我介紹": "認識平台演員"}
    for k, vs in by_kind.items():
        if len(vs) >= 2:
            topics.append(Topic(f"kind-{k}", labels.get(k, k), ranked(vs), "同一類型"))
    fresh = [v for v in works if time.time() - v.created < 14 * 86400 and not v.work.startswith("actor:")]
    if len(fresh) >= 2:
        topics.append(Topic("fresh", "最近上架", [v.id for v in sorted(fresh, key=lambda v: -v.created)], "兩週內上架"))
    if not topics and works:
        topics.append(Topic("all", "平台全部影片", ranked(works), "全部"))
    # wishes first (the audience asked for them), then the strongest topics; ties keep the order above
    topics.sort(key=lambda t: (not t.key.startswith("wish-"), -sum(wscores.get(cat.get(i).work, 0) for i in t.works if cat.get(i))))
    return topics


# ---------------------------------------------------------------------------------------------- the planner
class Programming:
    def __init__(self, store: Store, cat: Catalog, data_dir: Path):
        self.store, self.cat = store, cat
        self.dir = Path(data_dir)
        (self.dir / "schedule").mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._rank_cache: dict[str, tuple[float, dict]] = {}
        self.wish_source = lambda: []             # set by the site: open wish cards
        self.on_wish_topic = lambda card_id: None  # mark a wish card as 「已成為主題」

    # ------------------------------------------------------------ topics (every 6 hours)
    def topics_file(self) -> Path:
        return self.dir / "topics.json"

    def topics(self) -> dict:
        f = self.topics_file()
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
        return self.regroup()

    def regroup(self) -> dict:
        with self._lock:
            ws = work_scores(self.cat, video_scores(self.store, self.cat, time.time() - 30 * 86400),
                             self.store.live_heat())
            tops = build_topics(self.cat, ws, self.wish_source())
            for t in tops:
                if t.key.startswith("wish-"):
                    self.on_wish_topic(int(t.key.split("-", 1)[1]))
            d = {"at": time.time(), "topics": [t.to() for t in tops]}
            _write(self.topics_file(), d)
            log.info("topics regrouped: %s", ", ".join(t.title for t in tops))
            return d

    # ------------------------------------------------------------ weekly schedule
    def week_file(self, monday: date) -> Path:
        return self.dir / "schedule" / f"{monday.isoformat()}.json"

    def week(self, monday: date) -> dict | None:
        f = self.week_file(monday)
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    def plan_week(self, monday: date, *, publish_at: float | None = None, with_poll: bool = True) -> dict:
        """Compose the 336 half-hour slots of one week. Prime time gets themed programs; the rest is a rotation."""
        with self._lock:
            topics = self.topics()["topics"] or []
            works = [v.id for v in self.cat.works()]
            reruns = self._reruns(monday)
            slots: list[dict] = []
            prime_i = 0
            program_pool = [t for t in topics if t["videos"]]
            for day in range(7):
                d0 = datetime.combine(monday + timedelta(days=day), datetime.min.time(), TZ)
                for k in range(48):
                    st = d0 + timedelta(minutes=30 * k)
                    start = st.timestamp()
                    sid = st.strftime("%Y-%m-%dT%H:%M")
                    prime = PRIME[0] <= st.hour < PRIME[1]
                    slot = {"id": sid, "start": start, "end": start + SLOT_S, "prime": prime, "influence": None}
                    if (day, st.hour, st.minute) == AUDIENCE_SLOT and with_poll:
                        slot.update(program="audience", title="觀眾決定", videos=works[:3] or [], audience=True,
                                    reason="由觀眾投票選出，週四 24:00 截止", influence="polling")
                    elif prime and reruns:
                        t = reruns.pop(0)
                        slot.update(program=t["key"], title=t["title"], videos=t["videos"], influence="rerun",
                                    reason=t["why"])
                    elif prime and program_pool:
                        t = program_pool[prime_i % len(program_pool)]
                        prime_i += 1
                        slot.update(program=t["key"], title=t["title"], videos=t["videos"][:6],
                                    reason=f"AI 依本週熱度排入 · {t['note']}",
                                    influence="wish" if t["key"].startswith("wish-") else None)
                    else:
                        rot = works[k % len(works):] + works[:k % len(works)] if works else []
                        slot.update(program="rotation", title="全天輪播", videos=rot, reason="平台全部影片依序輪播")
                    slots.append(slot)
            plan = {"week": monday.isoformat(), "published": publish_at or time.time(), "by": "rules",
                    "slots": slots, "prime_titles": {}}
            self._ai_titles(plan)
            _write(self.week_file(monday), plan)
            if with_poll:
                self._open_poll(monday, plan, topics)
            log.info("week %s planned: %d slots, %d reruns", monday, len(slots), sum(1 for s in slots if s.get("influence") == "rerun"))
            return plan

    def _reruns(self, monday: date) -> list[dict]:
        """Programs that last week's viewers wanted again (「想」 > 「不想」, enough answers)."""
        prev = self.week(monday - timedelta(days=7)) or self.week(monday - timedelta(days=14))
        if not prev:
            return []
        min_votes = int(settings().get("site.rerun_min_votes", 3))
        since = time.time() - 14 * 86400
        seen, out = set(), []
        for s in prev["slots"]:
            p = s.get("program")
            if not p or p in ("rotation", "audience") or p in seen:
                continue
            seen.add(p)
            t = self.store.slot_tally(program=p, since=since)
            if t["votes"] >= min_votes and t["want"] * 2 > t["votes"]:
                out.append({"key": p, "title": s["title"], "videos": s["videos"],
                            "why": f"上週 {t['votes']} 位觀眾中有 {t['want']} 位想再看"})
        return out

    def _ai_titles(self, plan: dict) -> None:
        """Optional: let Qwen polish prime-time program names. Rules stay authoritative if the model is unavailable."""
        if not settings().get("site.ai_titles", False) or settings().mode == "mock":
            return
        try:
            from ..providers.llm import llm
            progs = {}
            for s in plan["slots"]:
                if s["prime"] and s["program"] not in ("rotation", "audience"):
                    progs.setdefault(s["program"], [self.cat.get(v).title for v in s["videos"] if self.cat.get(v)])
            if not progs:
                return
            r = llm().json("site_titles",
                           "You name TV programs for a Traditional Chinese AI video channel. Calm, plain titles, "
                           "max 14 characters, no exclamation marks, no emoji. Return {\"titles\": {key: title}}.",
                           json.dumps(progs, ensure_ascii=False), max_tokens=1024)
            titles = {k: str(v)[:20] for k, v in (r.get("titles") or {}).items() if k in progs and v}
            for s in plan["slots"]:
                if s["program"] in titles:
                    s["title"] = titles[s["program"]]
            plan["by"] = "ai"
            plan["prime_titles"] = titles
        except Exception as e:  # noqa: BLE001
            log.warning("AI program titles skipped: %s", e)

    # ------------------------------------------------------------ the 「觀眾決定」 poll
    def _open_poll(self, monday: date, plan: dict, topics: list[dict]) -> None:
        slot = next((s for s in plan["slots"] if s.get("audience")), None)
        if not slot:
            return
        cands = [t for t in topics if t["videos"]][:3]
        if len(cands) < 2:
            return
        opts = [{"id": t["key"], "title": t["title"], "videos": t["videos"][:3],
                 "why": t["note"] and f"{t['note']} · {len(t['videos'])} 部"} for t in cands]
        prev_monday = monday - timedelta(days=7)
        closes = datetime.combine(prev_monday + timedelta(days=4), datetime.min.time(), TZ).timestamp()  # 週四 24:00
        opens = plan["published"]
        if closes <= opens:                                     # bootstrapped after Thursday: vote until Friday 24:00 of the same week
            closes = datetime.combine(monday + timedelta(days=4), datetime.min.time(), TZ).timestamp()
        start = now_local(slot["start"])
        title = f"{start.month}/{start.day}（{WEEKDAYS[start.weekday()]}）{slot_range(slot['start'])}，你想看哪一個？"
        self.store.upsert_poll(f"poll-{monday.isoformat()}", slot["id"], title, json.dumps(opts, ensure_ascii=False), opens, closes)
        slot["poll"] = f"poll-{monday.isoformat()}"
        _write(self.week_file(monday), plan)

    def close_due_polls(self) -> None:
        for r in self.store.q("SELECT * FROM poll WHERE winner IS NULL AND closes<=?", (time.time(),)):
            t = self.store.tally(r["id"])
            opts = json.loads(r["options"])
            if not opts:
                continue
            # most votes wins; a tie (or no votes) goes to the candidate the AI listed first
            win = max(opts, key=lambda o: (t["total"].get(o["id"], 0), -opts.index(o)))
            self.store.close_poll(r["id"], win["id"])
            monday = date.fromisoformat(r["id"].split("poll-", 1)[1])
            plan = self.week(monday)
            if plan:
                for s in plan["slots"]:
                    if s["id"] == r["slot"]:
                        n = t["total"].get(win["id"], 0)
                        s.update(program=win["id"], title=win["title"], videos=win["videos"] or s["videos"],
                                 influence="poll", reason=f"觀眾投票選出 · 第 1 名 {n} 票（共 {t['votes']} 票）")
                _write(self.week_file(monday), plan)
            log.info("poll %s closed: %s (%s)", r["id"], win["title"], t)

    # ------------------------------------------------------------ periodic work
    def ensure(self) -> None:
        """Called every minute: bootstrap missing weeks, publish next week on Monday 09:00, close polls, regroup topics."""
        now = now_local()
        mon = week_start(now.date())
        if not self.week(mon):
            self.plan_week(mon, with_poll=False)
        publish = datetime.combine(mon, datetime.min.time(), TZ) + timedelta(hours=9)
        nxt = mon + timedelta(days=7)
        if now >= publish and not self.week(nxt):
            self.plan_week(nxt, publish_at=time.time())
        self.close_due_polls()
        f = self.topics_file()
        last = json.loads(f.read_text(encoding="utf-8"))["at"] if f.exists() else 0
        if time.time() - last > 6 * 3600 or (now.hour in (2, 8, 14, 20) and now.minute == 0 and time.time() - last > 120):
            self.regroup()

    # ------------------------------------------------------------ queries
    def slot_at(self, ts: float) -> dict | None:
        plan = self.week(week_start(now_local(ts).date()))
        if not plan:
            return None
        for s in plan["slots"]:
            if s["start"] <= ts < s["end"]:
                return s
        return None

    def now_playing(self, ts: float | None = None) -> dict | None:
        ts = ts or time.time()
        s = self.slot_at(ts)
        if not s:
            return None
        items = [v for v in (self.cat.get(i) for i in s["videos"]) if v and v.duration > 0]
        if not items:
            return {"slot": s, "items": [], "index": 0, "offset": 0}
        total = sum(v.duration for v in items)
        pos = (ts - s["start"]) % total
        for i, v in enumerate(items):
            if pos < v.duration:
                return {"slot": s, "items": items, "index": i, "offset": pos}
            pos -= v.duration
        return {"slot": s, "items": items, "index": 0, "offset": 0}

    def nightly(self, monday: date) -> list[dict]:
        """One headline slot per night (the first prime slot that carries audience influence, else 21:00)."""
        plan = self.week(monday)
        if not plan:
            return []
        out = []
        for day in range(7):
            d = monday + timedelta(days=day)
            prime = [s for s in plan["slots"] if s["prime"] and now_local(s["start"]).date() == d]
            if not prime:
                continue
            pick = next((s for s in prime if s.get("influence")), None) or next(
                (s for s in prime if now_local(s["start"]).hour == 21 and now_local(s["start"]).minute == 0), prime[0])
            out.append({**pick, "day": f"{d.month}/{d.day} {WEEKDAYS[d.weekday()]}", "time": slot_range(pick["start"]),
                        "today": d == now_local().date(), "count": len(pick["videos"])})
        return out

    def ranking(self, period: str) -> dict:
        """最多人看：completed views per work, computed up to the top of the hour, compared with the previous period."""
        now = now_local()
        hour = now.replace(minute=0, second=0, microsecond=0)
        key = f"{period}|{hour.isoformat()}"
        if key in self._rank_cache:
            return self._rank_cache[key][1]
        if period == "today":
            start = hour.replace(hour=0)
            prev = start - timedelta(days=1)
        elif period == "week":
            start = datetime.combine(week_start(now.date()), datetime.min.time(), TZ)
            prev = start - timedelta(days=7)
        else:
            start = hour.replace(day=1, hour=0)
            prev = (start - timedelta(days=1)).replace(day=1)
        cur = self._work_views(start.timestamp(), hour.timestamp() if hour > start else start.timestamp() + 1)
        before = self._work_views(prev.timestamp(), start.timestamp())
        prev_rank = {w: i for i, (w, _) in enumerate(sorted(before.items(), key=lambda x: -x[1]))}
        rows = []
        for i, (w, n) in enumerate(sorted(cur.items(), key=lambda x: -x[1])[:10]):
            p = prev_rank.get(w)
            move = "new" if p is None else ("up" if p > i else "down" if p < i else "same")
            rows.append({"work": w, "views": n, "move": move})
        d = {"period": period, "at": hour.timestamp(), "rows": rows}
        self._rank_cache[key] = (time.time(), d)
        return d

    def _work_views(self, since: float, until: float) -> dict[str, int]:
        out: dict[str, int] = {}
        for vid, n in self.store.completed_views(since, until).items():
            v = self.cat.get(vid)
            if v:
                out[v.work] = out.get(v.work, 0) + n
        return out

    # ------------------------------------------------------------ highlights (live reaction peaks)
    def highlights(self, vid: str) -> list[dict]:
        b = self.store.live_buckets(vid)
        if not b:
            return []
        min_n = int(settings().get("site.highlight_min", 5))
        v = self.cat.get(vid)
        dur = v.duration if v else 0
        nb = max(1, -(-int(dur) // 5), len(b))                 # 5-second buckets across the whole video, quiet ones included
        mean = sum(b.values()) / nb
        thresh = min_n if nb <= 2 else max(min_n, 2 * mean)   # a peak = at least twice the video's average
        peaks = sorted([k for k, n in b.items() if n >= thresh], key=lambda k: -b[k])[:3]
        out = []
        for k in sorted(peaks):
            c = k * 5 + 2.5
            out.append({"start": max(0.0, c - 7), "end": min(dur or c + 7, c + 7), "reactions": b[k],
                        "label": INFLUENCE["highlight"]})
        return out

    def write_highlights(self) -> int:
        """Store peaks next to each project so the ad pipeline can prefer them when cutting the 15-second version."""
        n = 0
        for v in self.cat.refresh().videos.values():
            if v.work.startswith("actor:"):
                continue
            h = self.highlights(v.id)
            if not h:
                continue
            f = settings().workspace / v.work / "audience" / "highlights.json"
            cur = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
            cur[Path(v.file).name] = {"updated": time.time(), "peaks": h}
            _write(f, cur)
            n += 1
        return n


def _write(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


__all__ = ["Programming", "INFLUENCE", "TZ", "fmt_dur", "now_local", "week_start", "slot_range", "day_label"]
