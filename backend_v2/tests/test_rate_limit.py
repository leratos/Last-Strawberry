import unittest

from backend_v2.app.services.rate_limit import SlidingWindowRateLimiter


class _Clock:
    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestSlidingWindowRateLimiter(unittest.TestCase):
    def test_allows_requests_until_limit(self):
        clock = _Clock()
        limiter = SlidingWindowRateLimiter(limit=2, window_seconds=10, clock=clock)

        first = limiter.check("user:1")
        second = limiter.check("user:1")

        self.assertTrue(first.allowed)
        self.assertEqual(first.remaining, 1)
        self.assertTrue(second.allowed)
        self.assertEqual(second.remaining, 0)

    def test_blocks_after_limit_and_returns_retry_after(self):
        clock = _Clock()
        limiter = SlidingWindowRateLimiter(limit=2, window_seconds=10, clock=clock)
        limiter.check("user:1")
        limiter.check("user:1")

        blocked = limiter.check("user:1")
        self.assertFalse(blocked.allowed)
        self.assertEqual(blocked.retry_after_seconds, 10)

    def test_allows_again_after_window_passes(self):
        clock = _Clock()
        limiter = SlidingWindowRateLimiter(limit=1, window_seconds=10, clock=clock)
        limiter.check("user:1")
        blocked = limiter.check("user:1")
        self.assertFalse(blocked.allowed)

        clock.advance(10.1)
        allowed = limiter.check("user:1")
        self.assertTrue(allowed.allowed)

    def test_disabled_limiter_always_allows(self):
        limiter = SlidingWindowRateLimiter(limit=1, window_seconds=10, enabled=False)
        first = limiter.check("user:1")
        second = limiter.check("user:1")
        self.assertTrue(first.allowed)
        self.assertTrue(second.allowed)

    def test_invalid_limit_raises(self):
        with self.assertRaises(ValueError):
            SlidingWindowRateLimiter(limit=0, window_seconds=10)

    def test_invalid_window_raises(self):
        with self.assertRaises(ValueError):
            SlidingWindowRateLimiter(limit=1, window_seconds=0)


if __name__ == "__main__":
    unittest.main()
