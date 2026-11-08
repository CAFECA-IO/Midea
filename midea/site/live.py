"""Official-channel live room: presence (「N 人正在看」), live reactions, 5-second aggregation, SSE fan-out.

In-process state (single site process). The plan's Redis replaces `LiveRoom` when the site runs on more than one
process; the store only ever receives 5-second aggregates, never per-press rows.
"""
from __future__ import annotations

import asyncio
import threading
import time

from .store import Store

LIVE_KINDS = ("like", "beautiful", "funny", "moving", "more")   # 喜歡、美、好笑、感動、想看更多
PRESS_GAP_S = 2.0          # 每人每 2 秒 1 次
SHOW_PER_S = 20            # 全場每秒最多顯示 20 個，其餘只計數
VIEWERS_MIN = 10           # 少於 10 人時不顯示數字
VIEWERS_EVERY_S = 10       # 每 10 秒更新
PRESENT_S = 30             # a viewer counts as watching for 30 s after the last heartbeat
BUCKET_S = 5


class LiveRoom:
    def __init__(self, store: Store):
        self.store = store
        self._lock = threading.Lock()
        self._present: dict[str, float] = {}
        self._last_press: dict[str, float] = {}
        self._second: dict[str, int] = {}
        self._buckets: dict[tuple[str, str, int, str], int] = {}
        self._viewers_shown: int | None = None
        self._viewers_at = 0.0
        self.subscribers: set[asyncio.Queue] = set()

    # ------------------------------------------------------------ presence
    def heartbeat(self, who: str) -> None:
        with self._lock:
            self._present[who] = time.time()

    def leave(self, who: str) -> None:
        with self._lock:
            self._present.pop(who, None)

    def viewers(self) -> int | None:
        """Shown value, refreshed every 10 s; None below 10 so small rooms don't show a number."""
        now = time.time()
        if now - self._viewers_at >= VIEWERS_EVERY_S:
            with self._lock:
                for k in [k for k, t in self._present.items() if now - t > PRESENT_S]:
                    self._present.pop(k, None)
                n = len(self._present)
            self._viewers_shown = n if n >= VIEWERS_MIN else None
            self._viewers_at = now
        return self._viewers_shown

    # ------------------------------------------------------------ reactions
    def press(self, who: str, kind: str, slot: str, video: str, position: float) -> bool:
        if kind not in LIVE_KINDS:
            raise ValueError("unknown reaction")
        now = time.time()
        with self._lock:
            if now - self._last_press.get(who, 0) < PRESS_GAP_S:
                return False
            self._last_press[who] = now
            self._present[who] = now
            self._second[kind] = self._second.get(kind, 0) + 1
            key = (slot, video, int(max(0.0, position) // BUCKET_S), kind)
            self._buckets[key] = self._buckets.get(key, 0) + 1
        return True

    def take_second(self) -> dict:
        """Counts pressed in the last second, plus how many of them to animate (≤ 20 across all kinds)."""
        with self._lock:
            got, self._second = self._second, {}
        total = sum(got.values())
        show = {}
        if total:
            budget = min(SHOW_PER_S, total)
            for k, n in sorted(got.items(), key=lambda x: -x[1]):
                show[k] = max(1, round(budget * n / total)) if budget else 0
        return {"counts": got, "show": show}

    def flush(self) -> int:
        with self._lock:
            rows, self._buckets = self._buckets, {}
        self.store.add_live_buckets([(s, v, b, k, n) for (s, v, b, k), n in rows.items()])
        return len(rows)

    # ------------------------------------------------------------ SSE
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    def broadcast(self, event: dict) -> None:
        for q in list(self.subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass        # a stalled client misses ticks; the next one carries the full state again
