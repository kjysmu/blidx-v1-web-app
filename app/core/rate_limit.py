import hashlib
import math
import threading
import time
from collections import deque

from app.core.config import settings


class LoginRateLimiter:
    def __init__(
        self,
        attempts_setting: str = "LOGIN_RATE_LIMIT_ATTEMPTS",
        window_setting: str = "LOGIN_RATE_LIMIT_WINDOW_SECONDS",
    ) -> None:
        self._attempts: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = 0.0
        self._attempts_setting = attempts_setting
        self._window_setting = window_setting

    @property
    def attempts_limit(self) -> int:
        return int(getattr(settings, self._attempts_setting))

    @property
    def window_seconds(self) -> int:
        return int(getattr(settings, self._window_setting))

    @staticmethod
    def _email_key(email: str) -> str:
        digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
        return f"email:{digest}"

    @staticmethod
    def _ip_key(client_ip: str) -> str:
        digest = hashlib.sha256((client_ip or "unknown").encode("utf-8")).hexdigest()
        return f"ip:{digest}"

    def _prune(self, attempts: deque[float], now: float) -> None:
        cutoff = now - self.window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()

    def _cleanup_locked(self, now: float) -> None:
        cleanup_interval = min(60, self.window_seconds)
        if now - self._last_cleanup < cleanup_interval:
            return
        for key, attempts in list(self._attempts.items()):
            self._prune(attempts, now)
            if not attempts:
                self._attempts.pop(key, None)
        self._last_cleanup = now

    def retry_after(self, client_ip: str, email: str) -> int:
        now = time.monotonic()
        retry_after = 0
        with self._lock:
            self._cleanup_locked(now)
            for key in (self._ip_key(client_ip), self._email_key(email)):
                attempts = self._attempts.get(key)
                if not attempts:
                    continue
                self._prune(attempts, now)
                if len(attempts) >= self.attempts_limit:
                    remaining = self.window_seconds - (now - attempts[0])
                    retry_after = max(retry_after, max(1, math.ceil(remaining)))
        return retry_after

    def record_failure(self, client_ip: str, email: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._cleanup_locked(now)
            for key in (self._ip_key(client_ip), self._email_key(email)):
                attempts = self._attempts.setdefault(key, deque())
                self._prune(attempts, now)
                attempts.append(now)

    def record_success(self, email: str) -> None:
        with self._lock:
            self._attempts.pop(self._email_key(email), None)

    def clear(self) -> None:
        with self._lock:
            self._attempts.clear()
            self._last_cleanup = 0.0


login_rate_limiter = LoginRateLimiter()
account_email_rate_limiter = LoginRateLimiter(
    "ACCOUNT_EMAIL_RATE_LIMIT_ATTEMPTS",
    "ACCOUNT_EMAIL_RATE_LIMIT_WINDOW_SECONDS",
)
