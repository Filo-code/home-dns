"""Portable regular-expression subset for DNS rules.

Pi-hole evaluates regex rules with a POSIX-ERE engine; tests and the policy engine use Python's
``re``. The two agree on *whether a pattern matches* (the only question a DNS rule asks) as long
as the pattern stays inside this subset:

    literals, escaped metacharacters (backslash + one of . ^ $ | ( ) [ ] { } * + ? \\ / -),
    .  ^  $  |  ( )  [ ]  [^ ]  ranges a-z  quantifiers * + ? {m} {m,} {m,n}

Everything else is rejected: backslash classes (\\d \\w \\s \\b), lookaround and other ``(?``
groups, lazy/possessive or stacked quantifiers, backreferences, POSIX classes ([:digit:]),
backslashes inside brackets, empty groups/alternatives, invalid intervals, upper-case letters
(domains are matched in lower case) and patterns that match the empty string.
Real behaviour is re-verified against Pi-hole in phase C2.
"""

from __future__ import annotations

import re

MAX_INTERVAL = 255
_ESCAPABLE = set(".^$|()[]{}*+?\\/-")
_QUANTIFIERS = set("*+?")
_INTERVAL_RE = re.compile(r"\{(\d+)(,(\d*))?\}")


class UnportableRegexError(ValueError):
    """The pattern uses syntax outside the portable POSIX-ERE subset."""


def _bracket_end(pattern: str, start: int) -> int:
    """Return the index of the closing ']' for a bracket expression opening at ``start``."""
    i = start + 1
    if i < len(pattern) and pattern[i] == "^":
        i += 1
    if i < len(pattern) and pattern[i] == "]":
        i += 1  # a leading ']' is a literal
    while i < len(pattern):
        char = pattern[i]
        if char == "\\":
            raise UnportableRegexError(
                f"backslash inside brackets at {i} (literal in POSIX, escape in Python)"
            )
        if char == "[" and i + 1 < len(pattern) and pattern[i + 1] in ":=.":
            raise UnportableRegexError(
                f"POSIX bracket class at {i} is not supported; use explicit ranges"
            )
        if char == "]":
            if i == start + 1 or (i == start + 2 and pattern[start + 1] == "^"):
                raise UnportableRegexError(f"empty bracket expression at {start}")
            return i
        i += 1
    raise UnportableRegexError(f"unterminated bracket expression at {start}")


def validate_portable_regex(pattern: str) -> None:
    """Raise UnportableRegexError unless ``pattern`` is inside the portable subset."""
    if not pattern:
        raise UnportableRegexError("pattern is empty")
    if any(c.isupper() for c in pattern):
        raise UnportableRegexError("upper-case letters never match normalized (lower-case) domains")
    depth = 0
    previous: str | None = None  # "atom", "anchor", "quantifier", "open", "alt" or None (start)
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "\\":
            if i + 1 >= len(pattern):
                raise UnportableRegexError("trailing backslash")
            escaped = pattern[i + 1]
            if escaped not in _ESCAPABLE:
                raise UnportableRegexError(f"unsupported escape \\{escaped} at {i}")
            previous, i = "atom", i + 2
            continue
        if char == "[":
            i, previous = _bracket_end(pattern, i) + 1, "atom"
            continue
        if char == "(":
            if i + 1 < len(pattern) and pattern[i + 1] == "?":
                raise UnportableRegexError(
                    f"'(?' groups (lookaround, flags, named) at {i} are not supported"
                )
            depth += 1
            previous, i = "open", i + 1
            continue
        if char == ")":
            if depth == 0:
                raise UnportableRegexError(f"unbalanced ')' at {i}")
            if previous in ("open", "alt"):
                raise UnportableRegexError(f"empty group or alternative at {i}")
            depth -= 1
            previous, i = "atom", i + 1
            continue
        if char == "|":
            if previous in (None, "open", "alt"):
                raise UnportableRegexError(f"empty alternative at {i}")
            previous, i = "alt", i + 1
            continue
        if char in _QUANTIFIERS or char == "{":
            if previous != "atom":
                what = (
                    "stacked or lazy quantifier"
                    if previous == "quantifier"
                    else "quantifier without an atom"
                )
                raise UnportableRegexError(f"{what} at {i}")
            if char == "{":
                match = _INTERVAL_RE.match(pattern, i)
                if match is None:
                    raise UnportableRegexError(
                        f"invalid interval at {i}; escape a literal '{{' as '\\{{'"
                    )
                low = int(match.group(1))
                high = match.group(3)
                if low > MAX_INTERVAL or (high and (int(high) > MAX_INTERVAL or int(high) < low)):
                    raise UnportableRegexError(f"invalid interval bounds at {i}")
                i = match.end()
            else:
                i += 1
            previous = "quantifier"
            continue
        if char == "}":
            raise UnportableRegexError(f"unmatched '}}' at {i}; escape it as '\\}}'")
        previous, i = ("anchor" if char in "^$" else "atom"), i + 1
    if depth:
        raise UnportableRegexError("unbalanced '('")
    if previous == "alt":
        raise UnportableRegexError("empty trailing alternative")
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise UnportableRegexError(f"invalid regular expression: {exc}") from exc
    if compiled.search("") is not None:
        raise UnportableRegexError("pattern matches the empty string and would match every domain")
