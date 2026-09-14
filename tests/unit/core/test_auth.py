from datetime import UTC, datetime, timedelta

import pytest

from home_dns.core.auth import (
    LoginRateLimiter,
    ScryptParams,
    WeakPasswordError,
    hash_password,
    new_token,
    token_digest,
    tokens_match,
    verify_password,
)

FAST = ScryptParams(n=2**10, r=8, p=1)
PASSWORD = "correct horse battery"


def test_hash_round_trip_and_salting() -> None:
    first = hash_password(PASSWORD, params=FAST)
    second = hash_password(PASSWORD, params=FAST)
    assert first != second
    assert first.startswith("scrypt$1024$8$1$")
    assert PASSWORD not in first
    assert verify_password(PASSWORD, first)
    assert not verify_password(PASSWORD + "x", first)


def test_default_parameters_are_owasp_minimum() -> None:
    assert ScryptParams() == ScryptParams(n=2**17, r=8, p=1)


def test_short_password_is_rejected() -> None:
    with pytest.raises(WeakPasswordError):
        hash_password("short", params=FAST)


@pytest.mark.parametrize(
    "stored", ["", "plain", "bcrypt$1$2$3$4$5", "scrypt$x$8$1$AA==$AA==", "scrypt$1024$8$1$!!$!!"]
)
def test_malformed_hash_never_verifies(stored: str) -> None:
    assert verify_password(PASSWORD, stored) is False


def test_tokens_are_random_and_digest_is_stable() -> None:
    assert new_token() != new_token()
    assert len(new_token()) >= 43
    assert token_digest("abc") == token_digest("abc") != token_digest("abd")
    assert tokens_match("abc", "abc") and not tokens_match("abc", "abd")


def test_rate_limiter_locks_after_max_failures_and_expires() -> None:
    limiter = LoginRateLimiter(max_failures=3, window=timedelta(minutes=15))
    t0 = datetime(2026, 9, 13, tzinfo=UTC)
    for i in range(3):
        assert not limiter.is_locked("ip", t0 + timedelta(minutes=i))
        limiter.record_failure("ip", t0 + timedelta(minutes=i))
    assert limiter.is_locked("ip", t0 + timedelta(minutes=3))
    assert not limiter.is_locked("other", t0)
    assert not limiter.is_locked("ip", t0 + timedelta(minutes=15, seconds=1))


def test_rate_limiter_reset_clears_key() -> None:
    limiter = LoginRateLimiter(max_failures=1)
    now = datetime(2026, 9, 13, tzinfo=UTC)
    limiter.record_failure("user", now)
    assert limiter.is_locked("user", now)
    limiter.reset("user")
    assert not limiter.is_locked("user", now)
