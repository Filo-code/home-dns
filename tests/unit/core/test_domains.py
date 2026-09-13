import pytest

from home_dns.core.domains import InvalidDomainError, covers, normalize_domain


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Example.COM", "example.com"),
        ("example.com.", "example.com"),
        ("  sub.example.com  ", "sub.example.com"),
        ("_dmarc.example.com", "_dmarc.example.com"),
        ("xn--bcher-kva.example", "xn--bcher-kva.example"),
        ("bücher.example", "xn--bcher-kva.example"),
        ("a-b.c-d.example", "a-b.c-d.example"),
    ],
)
def test_valid_domains_are_normalized(raw: str, expected: str) -> None:
    assert normalize_domain(raw) == expected


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("", "empty"),
        (".", "empty"),
        ("*.example.com", "wildcards"),
        ("192.0.2.1", "IP addresses"),
        ("2001:db8::1", "IP addresses"),
        ("com", "single-label"),
        ("-bad.example.com", "invalid label"),
        ("bad-.example.com", "invalid label"),
        ("sp ace.example.com", "invalid label"),
        ("a..example.com", "invalid label"),
        ("example.123", "numeric"),
        ("a" * 64 + ".example.com", "invalid label"),
        (".".join(["a" * 63] * 4) + ".example", "longer than"),
        ("xn--.example", "invalid label"),
        ("bü" + "x" * 70 + ".example", "invalid internationalized"),
    ],
)
def test_invalid_domains_are_rejected(raw: str, reason: str) -> None:
    with pytest.raises(InvalidDomainError, match=reason):
        normalize_domain(raw)


def test_covers_exact_and_subdomains() -> None:
    assert covers("example.com", include_subdomains=False, name="example.com")
    assert not covers("example.com", include_subdomains=False, name="a.example.com")
    assert covers("example.com", include_subdomains=True, name="a.b.example.com")
    assert not covers("example.com", include_subdomains=True, name="badexample.com")
    assert not covers("a.example.com", include_subdomains=True, name="example.com")
