"""Dashboard authentication primitives: roles, password hashing, tokens, login rate limiting.

Pure apart from the OS random source. See docs/specs/a7-backend.md §7.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

MIN_PASSWORD_LENGTH = 12
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW = timedelta(minutes=15)


class Role(StrEnum):
    ADMIN = "admin"
    VIEWER = "viewer"


@dataclass(frozen=True)
class ScryptParams:
    """OWASP minimum for scrypt. Tests pass cheaper parameters explicitly."""

    n: int = 2**17
    r: int = 8
    p: int = 1


class WeakPasswordError(ValueError):
    """The password does not meet the minimum policy."""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _scrypt(password: str, salt: bytes, params: ScryptParams) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=params.n,
        r=params.r,
        p=params.p,
        maxmem=256 * 1024 * 1024,
        dklen=32,
    )


def hash_password(password: str, *, params: ScryptParams | None = None) -> str:
    """Return ``scrypt$n$r$p$salt$hash`` (base64). Raises WeakPasswordError."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    params = params or ScryptParams()
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, params)
    return f"scrypt${params.n}${params.r}${params.p}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time comparison. A malformed stored hash verifies as False, never raises."""
    try:
        scheme, n, r, p, salt, expected = encoded.split("$")
        if scheme != "scrypt":
            return False
        params = ScryptParams(int(n), int(r), int(p))
        actual = _scrypt(password, base64.b64decode(salt), params)
        return hmac.compare_digest(actual, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    """Only this digest is stored, so a leaked database does not leak live sessions."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


class LoginRateLimiter:
    """At most ``max_failures`` failed logins per key in a sliding ``window``.

    ponytail: in memory, so a restart resets it; persist only if LAN brute force becomes a real
    concern (a 12-character minimum makes 5 tries per restart negligible).
    """

    def __init__(
        self, *, max_failures: int = LOGIN_MAX_FAILURES, window: timedelta = LOGIN_WINDOW
    ) -> None:
        self._max = max_failures
        self._window = window
        self._failures: dict[str, deque[datetime]] = {}

    def _recent(self, key: str, now: datetime) -> int:
        failures = self._failures.get(key)
        if failures is None:
            return 0
        while failures and now - failures[0] >= self._window:
            failures.popleft()
        if not failures:
            del self._failures[key]
        return len(failures)

    def is_locked(self, key: str, now: datetime) -> bool:
        return self._recent(key, now) >= self._max

    def record_failure(self, key: str, now: datetime) -> None:
        self._recent(key, now)
        self._failures.setdefault(key, deque()).append(now)

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
