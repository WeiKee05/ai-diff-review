"""Token-bucket rate limiter for POST /v1/reviews.

Two parameters map onto the brief's two requirements:
  refill rate = the sustained rate that must always succeed (30/min)
  capacity    = the burst ceiling, beyond which we return 429

Global rather than per-client: this is a single-tenant service with one bearer
token. Per-key buckets would be the change if it served multiple clients.
"""

from __future__ import annotations

import time

from app import config

_CAPACITY = config.RATE_LIMIT_BURST
_REFILL_PER_SECOND = config.RATE_LIMIT_PER_MINUTE / 60.0

_tokens: float = float(_CAPACITY)
_last_refill: float = time.monotonic()


def _refill() -> None:
    global _tokens, _last_refill
    now = time.monotonic()
    elapsed = now - _last_refill
    _last_refill = now
    _tokens = min(_CAPACITY, _tokens + elapsed * _REFILL_PER_SECOND)


def try_acquire() -> tuple[bool, int]:
    """Take one token. Returns (allowed, retry_after_seconds)."""
    global _tokens
    _refill()

    if _tokens >= 1.0:
        _tokens -= 1.0
        return True, 0

    # Seconds until one token is available, rounded up, minimum 1.
    needed = 1.0 - _tokens
    retry_after = max(1, int(needed / _REFILL_PER_SECOND) + 1)
    return False, retry_after


def reset() -> None:
    """Test helper: restore a full bucket."""
    global _tokens, _last_refill
    _tokens = float(_CAPACITY)
    _last_refill = time.monotonic()
