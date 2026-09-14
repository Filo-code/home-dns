import re

import pytest

from home_dns.core.regex import UnportableRegexError, validate_portable_regex


@pytest.mark.parametrize(
    "pattern",
    [
        r"^ads?[0-9]*\.example\.com$",
        r"(^|\.)doubleclick\.net$",
        r"^(ads|track|pixel)\.",
        r"^[a-z0-9-]{3,63}\.casino$",
        r"^tracker[0-9]{2}\.example$",
        r"^[^.]+\.bet[0-9]*\.it$",
        r"^[]a-z]+\.example$",
        r"^x{2,}\.example$",
        r"^a+b*c?\.example$",
        r"\\\/\-",
        r"^cdn[-.]ads\.",
    ],
)
def test_portable_patterns_are_accepted(pattern: str) -> None:
    validate_portable_regex(pattern)
    re.compile(pattern)


@pytest.mark.parametrize(
    ("pattern", "fragment"),
    [
        ("", "empty"),
        (r"^\d+\.example$", r"unsupported escape \d"),
        (r"\w+\.ads$", r"unsupported escape \w"),
        (r"\bads\b", r"unsupported escape \b"),
        (r"^ads\s", r"unsupported escape \s"),
        (r"(ads)\1", r"unsupported escape \1"),
        (r"^(?=ads)", "'(?' groups"),
        (r"^(?:ads|trk)\.", "'(?' groups"),
        (r"(?i)ads", "'(?' groups"),
        (r"^ads.*?\.com$", "stacked or lazy quantifier"),
        (r"^ads++$", "stacked or lazy quantifier"),
        (r"^*ads", "quantifier without an atom"),
        (r"*ads", "quantifier without an atom"),
        (r"(|ads)", "empty alternative"),
        (r"ads|", "empty trailing alternative"),
        (r"()ads", "empty group"),
        (r"^[[:digit:]]+\.example$", "POSIX bracket class"),
        (r"^[\d]+\.example$", "backslash inside brackets"),
        (r"^[]$", "unterminated bracket"),
        (r"^[^]$", "unterminated bracket"),
        (r"^ads{2,1}$", "invalid interval bounds"),
        (r"^ads{300}$", "invalid interval bounds"),
        (r"^ads{x}$", "invalid interval"),
        (r"^ads}$", "unmatched '}'"),
        (r"(ads", "unbalanced '('"),
        (r"ads)", "unbalanced ')'"),
        ("ads\\", "trailing backslash"),
        (r"^Ads\.example$", "upper-case"),
        (r"^(a*)$", "matches the empty string"),
        (r"x?", "matches the empty string"),
    ],
)
def test_unportable_patterns_are_rejected(pattern: str, fragment: str) -> None:
    with pytest.raises(UnportableRegexError, match=re.escape(fragment)):
        validate_portable_regex(pattern)


def test_python_invalid_pattern_inside_subset_is_still_rejected() -> None:
    with pytest.raises(UnportableRegexError, match=r"invalid regular expression"):
        validate_portable_regex(r"[z-a]")
