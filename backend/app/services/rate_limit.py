"""Rate limiting service using sliding window counters."""
from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

from app.config import settings


class RateLimiter:
    """Sliding window rate limiter for per-user upload limits."""

    def __init__(self, window_seconds: int = 60):
        self.window_seconds = window_seconds
        self._timestamps: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def _cleanup_old_timestamps(self, key: str, now: float) -> None:
        """Remove timestamps older than the window."""
        cutoff = now - self.window_seconds
        self._timestamps[key] = [ts for ts in self._timestamps[key] if ts > cutoff]

    def is_allowed(self, key: str, max_requests: int) -> tuple[bool, int]:
        """Check if a request is allowed under the rate limit.

        Args:
            key: Unique identifier (user_id or IP address)
            max_requests: Maximum requests allowed in the window

        Returns:
            (is_allowed, retry_after_seconds)
            - is_allowed: True if request is within limits
            - retry_after_seconds: Seconds until rate limit resets (0 if allowed)
        """
        if max_requests <= 0:
            return True, 0

        now = time.time()

        with self._lock:
            self._cleanup_old_timestamps(key, now)
            current_count = len(self._timestamps[key])

            if current_count >= max_requests:
                # Rate limit exceeded - calculate retry after
                oldest = min(self._timestamps[key]) if self._timestamps[key] else now
                retry_after = int(oldest + self.window_seconds - now) + 1
                return False, max(1, retry_after)

            # Request allowed - record timestamp
            self._timestamps[key].append(now)
            return True, 0

    def get_remaining(self, key: str, max_requests: int) -> int:
        """Get remaining requests for a key."""
        if max_requests <= 0:
            return -1  # Unlimited

        now = time.time()

        with self._lock:
            self._cleanup_old_timestamps(key, now)
            return max(0, max_requests - len(self._timestamps[key]))

    def clear(self) -> None:
        """Clear all rate limit data. Useful for testing."""
        with self._lock:
            self._timestamps.clear()


# Global rate limiter instance for uploads
upload_rate_limiter = RateLimiter(window_seconds=60)


def check_upload_rate_limit(user_id: str | None, client_ip: str) -> tuple[bool, int]:
    """Check if an upload is allowed based on rate limits.

    Uses user_id if authenticated, otherwise falls back to IP address.

    Args:
        user_id: Authenticated user's ID (None if anonymous)
        client_ip: Client's IP address

    Returns:
        (is_allowed, retry_after_seconds)
    """
    key = f"user:{user_id}" if user_id else f"ip:{client_ip}"
    return upload_rate_limiter.is_allowed(key, settings.upload_rate_limit_per_minute)


def get_upload_rate_limit_remaining(user_id: str | None, client_ip: str) -> int:
    """Get remaining upload requests for a user/IP."""
    key = f"user:{user_id}" if user_id else f"ip:{client_ip}"
    return upload_rate_limiter.get_remaining(key, settings.upload_rate_limit_per_minute)
