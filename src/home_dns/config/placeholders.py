"""Placeholder tokens for environment-specific values.

A placeholder is a whole string value of the form ``<<REQUIRED:name>>`` (the owner must
supply it) or ``<<AUDIT:name>>`` (known only after the Raspberry Pi / network audits).
Anything that looks like a token but does not match exactly is rejected, so a typo can
never silently become a literal configuration value.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from enum import StrEnum
from typing import Annotated, Any, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict

_TOKEN_RE = re.compile(r"<<(REQUIRED|AUDIT):([a-z][a-z0-9_.-]*)>>")
_TOKEN_LIKE_RE = re.compile(r"<<.*>>", re.DOTALL)


class PlaceholderKind(StrEnum):
    REQUIRED = "REQUIRED"
    AUDIT = "AUDIT"


class MalformedPlaceholderError(ValueError):
    """A string looks like a placeholder token but is not a valid one."""


class Placeholder(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: PlaceholderKind
    name: str

    @property
    def token(self) -> str:
        return f"<<{self.kind.value}:{self.name}>>"

    def __str__(self) -> str:
        return self.token


def parse_placeholder(value: object) -> Placeholder | None:
    """Return a Placeholder for a valid token, None for ordinary values.

    Raises MalformedPlaceholderError for strings that resemble a token but are invalid.
    """
    if not isinstance(value, str) or not _TOKEN_LIKE_RE.search(value):
        return None
    match = _TOKEN_RE.fullmatch(value)
    if match is None:
        raise MalformedPlaceholderError(
            f"malformed placeholder {value!r}: expected <<REQUIRED:name>> or <<AUDIT:name>> "
            "with a lower-case name"
        )
    return Placeholder(kind=PlaceholderKind(match.group(1)), name=match.group(2))


def _coerce_token(value: Any) -> Any:
    placeholder = parse_placeholder(value)
    return value if placeholder is None else placeholder


T = TypeVar("T")

# A field that may hold a real value of type T or a placeholder awaiting a real value.
Deferred = Annotated[Placeholder | T, BeforeValidator(_coerce_token)]


def iter_raw_placeholders(data: Any, path: str = "") -> Iterator[tuple[str, Placeholder]]:
    """Walk parsed YAML (dicts, lists, scalars) and yield (dotted path, placeholder).

    Raises MalformedPlaceholderError, prefixed with the path, for invalid tokens.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            yield from iter_raw_placeholders(value, f"{path}.{key}" if path else str(key))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            yield from iter_raw_placeholders(value, f"{path}[{index}]")
    else:
        try:
            placeholder = parse_placeholder(data)
        except MalformedPlaceholderError as exc:
            raise MalformedPlaceholderError(f"{path}: {exc}") from exc
        if placeholder is not None:
            yield path, placeholder
