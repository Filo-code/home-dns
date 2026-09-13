from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from home_dns.config.placeholders import (
    Deferred,
    MalformedPlaceholderError,
    Placeholder,
    PlaceholderKind,
    iter_raw_placeholders,
    parse_placeholder,
)


@pytest.mark.parametrize(
    ("token", "kind", "name"),
    [
        ("<<REQUIRED:api.port>>", PlaceholderKind.REQUIRED, "api.port"),
        ("<<AUDIT:paths.data_dir>>", PlaceholderKind.AUDIT, "paths.data_dir"),
        ("<<AUDIT:a-b_c.d9>>", PlaceholderKind.AUDIT, "a-b_c.d9"),
    ],
)
def test_valid_tokens_parse(token: str, kind: PlaceholderKind, name: str) -> None:
    placeholder = parse_placeholder(token)
    assert placeholder == Placeholder(kind=kind, name=name)
    assert str(placeholder) == token


@pytest.mark.parametrize("value", ["/opt/home-dns", "a << b", "x >> y", 8080, None, True, ""])
def test_ordinary_values_are_not_placeholders(value: object) -> None:
    assert parse_placeholder(value) is None


@pytest.mark.parametrize(
    "value",
    [
        "<<TODO>>",
        "<<AUDT:paths.data_dir>>",
        "<<REQUIRED:Api.Port>>",
        "<<REQUIRED:>>",
        "<<required:api.port>>",
        " <<AUDIT:x>>",
        "<<AUDIT:x>> trailing",
        "prefix-<<AUDIT:x>>",
    ],
)
def test_malformed_tokens_are_rejected(value: str) -> None:
    with pytest.raises(MalformedPlaceholderError):
        parse_placeholder(value)


def test_iter_raw_placeholders_reports_nested_paths() -> None:
    data = {
        "a": {"b": "<<AUDIT:a.b>>", "c": 1},
        "items": ["plain", "<<REQUIRED:items.one>>"],
    }
    found = dict(iter_raw_placeholders(data))
    assert set(found) == {"a.b", "items[1]"}
    assert found["items[1]"].kind is PlaceholderKind.REQUIRED


def test_iter_raw_placeholders_prefixes_path_on_malformed_token() -> None:
    with pytest.raises(MalformedPlaceholderError, match=r"^a\.b: "):
        list(iter_raw_placeholders({"a": {"b": "<<OOPS>>"}}))


class _Model(BaseModel):
    deferred_path: Deferred[Path]
    plain_path: Path


def test_deferred_field_accepts_placeholder_or_value() -> None:
    model = _Model(deferred_path="<<AUDIT:x>>", plain_path="/tmp/a")
    assert isinstance(model.deferred_path, Placeholder)
    assert _Model(deferred_path="/srv/x", plain_path="/tmp/a").deferred_path == Path("/srv/x")


def test_placeholder_in_non_deferred_field_fails_validation() -> None:
    with pytest.raises(ValidationError):
        _Model(deferred_path="/srv/x", plain_path=Placeholder(kind=PlaceholderKind.AUDIT, name="x"))
