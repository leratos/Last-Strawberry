from collections import defaultdict, deque
from dataclasses import dataclass
from math import ceil
from threading import Lock
from time import monotonic
from typing import Callable


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int | None
    remaining: int


class SlidingWindowRateLimiter:
    def __init__(
        self,
        *,
        limit: int,
        window_seconds: int,
        enabled: bool = True,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be > 0")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._limit = limit
        self._window_seconds = float(window_seconds)
        self._enabled = enabled
        self._clock = clock
        self._lock = Lock()
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> RateLimitDecision:
        if not self._enabled:
            return RateLimitDecision(allowed=True, retry_after_seconds=None, remaining=self._limit)

        now = self._clock()
        oldest_allowed_ts = now - self._window_seconds
        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] <= oldest_allowed_ts:
                bucket.popleft()

            if len(bucket) >= self._limit:
                retry_after = max(1, int(ceil((bucket[0] + self._window_seconds) - now)))
                return RateLimitDecision(allowed=False, retry_after_seconds=retry_after, remaining=0)

            bucket.append(now)
            remaining = self._limit - len(bucket)
            return RateLimitDecision(allowed=True, retry_after_seconds=None, remaining=remaining)
