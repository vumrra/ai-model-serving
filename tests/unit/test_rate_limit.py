import asyncio

from apps.gateway.rate_limit import InMemoryRateLimiter


def test_rate_limiter_releases_entries_after_window():
    now = 0.0
    limiter = InMemoryRateLimiter(2, 10, clock=lambda: now)

    assert asyncio.run(limiter.allow("key")) == (True, 0)
    assert asyncio.run(limiter.allow("key")) == (True, 0)
    allowed, retry_after = asyncio.run(limiter.allow("key"))
    assert allowed is False
    assert retry_after > 0

    now = 11.0
    assert asyncio.run(limiter.allow("key")) == (True, 0)
