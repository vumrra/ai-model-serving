from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Callable


class InMemoryRateLimiter:
    """단일 프로세스 데모용 sliding-window 제한기."""

    def __init__(
        self,
        limit: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, key: str) -> tuple[bool, int]:
        now = self._clock()
        cutoff = now - self.window_seconds

        async with self._lock:
            entries = self._requests[key]
            while entries and entries[0] <= cutoff:
                entries.popleft()

            if len(entries) >= self.limit:
                retry_after = max(1, int(entries[0] + self.window_seconds - now) + 1)
                return False, retry_after

            entries.append(now)
            return True, 0
