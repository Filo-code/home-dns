"""Pure blocklist processing: header, parsing, normalization, deduplication, protected-domain
tripwire, artifact rendering and sanity evaluation. No I/O.

Semantics of an entry:
- ``include_subdomains=True``  blocks the domain and everything below it (``||domain^``)
- ``include_subdomains=False`` blocks the exact name only (hosts / plain-domain formats)
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import NamedTuple

from home_dns.core.domains import InvalidDomainError, normalize_domain
from home_dns.core.filtering import ListFormat, ProtectedDomain, SanityLimits

MAX_ISSUE_SAMPLES = 20
ARTIFACT_MAGIC = "! home-dns blocklist artifact v1"

_HEADER_RE = re.compile(r"^[!#]\s*([A-Za-z][A-Za-z ]*?)\s*:\s*(.+?)\s*$")
_ADBLOCK_RULE_RE = re.compile(r"^\|\|([^\^|$/*]+)\^$")
_EXPIRES_RE = re.compile(r"^(\d+)\s*(hour|hours|day|days)\b", re.I)
_HOSTS_SINKS = {"0.0.0.0", "127.0.0.1", "::", "::1"}  # noqa: S104 - hosts-file sink addresses
_HOSTS_IGNORED_NAMES = {"localhost", "localhost.localdomain", "local", "broadcasthost",
                        "ip6-localhost", "ip6-loopback", "0.0.0.0"}  # noqa: S104  # fmt: skip


class BlockEntry(NamedTuple):
    domain: str
    include_subdomains: bool


# -------------------------------------------------------------------------------- header


@dataclass(frozen=True)
class ListHeader:
    title: str | None = None
    version: str | None = None
    last_modified: datetime | None = None
    declared_entries: int | None = None
    expires: timedelta | None = None
    syntax: str | None = None


def _parse_last_modified(value: str) -> datetime | None:
    text = value.strip()
    for suffix in (" UTC", " GMT"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    for fmt in ("%d %b %Y %H:%M", "%d %b %Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def parse_header(lines: Iterable[str], *, max_lines: int = 50) -> ListHeader:
    values: dict[str, str] = {}
    for index, line in enumerate(lines):
        if index >= max_lines:
            break
        match = _HEADER_RE.match(line)
        if match:
            values.setdefault(match.group(1).strip().lower(), match.group(2))
    declared = values.get("number of entries", "").replace(",", "").strip()
    expires_match = _EXPIRES_RE.match(values.get("expires", ""))
    expires = None
    if expires_match:
        amount = int(expires_match.group(1))
        expires = (
            timedelta(days=amount)
            if expires_match.group(2).lower().startswith("day")
            else timedelta(hours=amount)
        )
    return ListHeader(
        title=values.get("title"),
        version=values.get("version"),
        last_modified=_parse_last_modified(values["last modified"])
        if "last modified" in values
        else None,
        declared_entries=int(declared) if declared.isdigit() else None,
        expires=expires,
        syntax=values.get("syntax"),
    )


# ------------------------------------------------------------------------------- parsing


class InvalidReason(StrEnum):
    UNSUPPORTED_SYNTAX = "unsupported_syntax"
    INVALID_DOMAIN = "invalid_domain"


@dataclass(frozen=True)
class InvalidLine:
    line_number: int
    reason: InvalidReason
    text: str


@dataclass(frozen=True)
class ParseResult:
    """Outcome of parsing + normalization + deduplication of one list."""

    header: ListHeader
    entries: frozenset[BlockEntry]
    total_lines: int
    comment_lines: int
    blank_lines: int
    rule_lines: int
    invalid_count: int
    duplicate_count: int
    invalid_samples: tuple[InvalidLine, ...] = field(default=())

    @property
    def valid_rules(self) -> int:
        return self.rule_lines - self.invalid_count

    @property
    def invalid_ratio(self) -> float:
        return self.invalid_count / self.rule_lines if self.rule_lines else 0.0


def _is_comment(line: str) -> bool:
    return line.startswith(("!", "#", "[")) and not line.startswith("||")


def _candidates(line: str, fmt: ListFormat) -> list[tuple[str, bool]] | None:
    """Return raw (domain, include_subdomains) candidates, or None for unsupported syntax."""
    if fmt is ListFormat.ADBLOCK:
        match = _ADBLOCK_RULE_RE.match(line)
        return [(match.group(1), True)] if match else None
    if fmt is ListFormat.HOSTS:
        parts = line.split("#", 1)[0].split()
        if len(parts) < 2 or parts[0] not in _HOSTS_SINKS:
            return None
        return [(name, False) for name in parts[1:] if name.lower() not in _HOSTS_IGNORED_NAMES]
    parts = line.split("#", 1)[0].split()
    return [(parts[0], False)] if len(parts) == 1 else None


def parse_list(text: str, fmt: ListFormat) -> ParseResult:
    lines = text.splitlines()
    header = parse_header(lines)
    seen: set[BlockEntry] = set()
    comments = blanks = rules = invalid = duplicates = 0
    samples: list[InvalidLine] = []

    def record(number: int, reason: InvalidReason, raw: str) -> None:
        nonlocal invalid
        invalid += 1
        if len(samples) < MAX_ISSUE_SAMPLES:
            samples.append(InvalidLine(number, reason, raw[:200]))

    for number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            blanks += 1
            continue
        if _is_comment(line):
            comments += 1
            continue
        rules += 1
        candidates = _candidates(line, fmt)
        if candidates is None:
            record(number, InvalidReason.UNSUPPORTED_SYNTAX, raw)
            continue
        try:
            normalized = [BlockEntry(normalize_domain(d), sub) for d, sub in candidates]
        except InvalidDomainError:
            record(number, InvalidReason.INVALID_DOMAIN, raw)
            continue
        for entry in normalized:
            if entry in seen:
                duplicates += 1
            else:
                seen.add(entry)

    return ParseResult(
        header=header,
        entries=frozenset(seen),
        total_lines=len(lines),
        comment_lines=comments,
        blank_lines=blanks,
        rule_lines=rules,
        invalid_count=invalid,
        duplicate_count=duplicates,
        invalid_samples=tuple(samples),
    )


# ------------------------------------------------------------------------------- tripwire


@dataclass(frozen=True)
class TripwireHit:
    entry: BlockEntry
    protected_domain: str
    relation: str  # "exact", "entry-covers-protected", "entry-inside-protected"


def _ancestors(domain: str) -> Iterator[str]:
    labels = domain.split(".")
    for index in range(1, len(labels) - 1):
        yield ".".join(labels[index:])


def find_tripwire_hits(
    entries: Iterable[BlockEntry], protected: Sequence[ProtectedDomain]
) -> list[TripwireHit]:
    """Entries that would block a protected domain (either direction of the subdomain relation)."""
    exact = {p.domain for p in protected}
    with_subdomains = {p.domain for p in protected if p.include_subdomains}
    hits: list[TripwireHit] = []
    for entry in entries:
        if entry.domain in exact:
            hits.append(TripwireHit(entry, entry.domain, "exact"))
            continue
        inside = next((a for a in _ancestors(entry.domain) if a in with_subdomains), None)
        if inside is not None:
            hits.append(TripwireHit(entry, inside, "entry-inside-protected"))
            continue
        if entry.include_subdomains:
            suffix = "." + entry.domain
            for name in exact:
                if name.endswith(suffix):
                    hits.append(TripwireHit(entry, name, "entry-covers-protected"))
                    break
    return sorted(hits, key=lambda hit: (hit.protected_domain, hit.entry.domain))


# ------------------------------------------------------------------------------ artifacts


def render_artifact(source_id: str, entries: Iterable[BlockEntry]) -> str:
    """Deterministic artifact text (no timestamps) so identical content has an identical hash."""
    ordered = sorted(entries, key=lambda e: (e.domain, e.include_subdomains))
    lines = [ARTIFACT_MAGIC, f"! source: {source_id}", f"! entries: {len(ordered)}"]
    lines += [f"||{e.domain}^" if e.include_subdomains else e.domain for e in ordered]
    return "\n".join(lines) + "\n"


class ArtifactFormatError(ValueError):
    """Rendered artifact text is not valid artifact syntax."""


def parse_artifact(text: str) -> frozenset[BlockEntry]:
    lines = text.splitlines()
    if not lines or lines[0] != ARTIFACT_MAGIC:
        raise ArtifactFormatError("missing artifact header")
    entries: set[BlockEntry] = set()
    declared: int | None = None
    for number, line in enumerate(lines[1:], start=2):
        if line.startswith("! entries: "):
            declared = int(line.removeprefix("! entries: "))
            continue
        if line.startswith("!"):
            continue
        match = _ADBLOCK_RULE_RE.match(line)
        raw, include = (match.group(1), True) if match else (line, False)
        try:
            domain = normalize_domain(raw)
        except InvalidDomainError as exc:
            raise ArtifactFormatError(f"line {number}: {exc}") from exc
        if domain != raw:
            raise ArtifactFormatError(f"line {number}: {raw!r} is not normalized")
        entries.add(BlockEntry(domain, include))
    if declared is None or declared != len(entries):
        raise ArtifactFormatError(f"declared entries {declared} != parsed {len(entries)}")
    return frozenset(entries)


# -------------------------------------------------------------------------------- sanity


class Verdict(StrEnum):
    PASS = "pass"  # noqa: S105 - not a password
    ANOMALY = "anomaly"
    FAIL = "fail"


@dataclass(frozen=True)
class Delta:
    previous_entries: int
    added: int
    removed: int

    @property
    def added_ratio(self) -> float:
        return self.added / self.previous_entries if self.previous_entries else 0.0

    @property
    def removed_ratio(self) -> float:
        return self.removed / self.previous_entries if self.previous_entries else 0.0


def compute_delta(previous: frozenset[BlockEntry], current: frozenset[BlockEntry]) -> Delta:
    return Delta(len(previous), len(current - previous), len(previous - current))


@dataclass(frozen=True)
class SanityResult:
    verdict: Verdict
    findings: tuple[str, ...]


def evaluate_sanity(
    parsed: ParseResult, delta: Delta | None, limits: SanityLimits | None
) -> SanityResult:
    """Hard invariants fail; approved limits produce anomalies that need review, not failures."""
    failures: list[str] = []
    anomalies: list[str] = []
    notes: list[str] = []
    count = len(parsed.entries)
    if count == 0:
        failures.append("no valid entries")
    if limits is None:
        notes.append("no approved sanity limits for this source; size/delta limits not applied")
    else:
        if limits.min_entries is not None and count < limits.min_entries:
            anomalies.append(f"{count} entries below approved minimum {limits.min_entries}")
        if limits.max_entries is not None and count > limits.max_entries:
            anomalies.append(f"{count} entries above approved maximum {limits.max_entries}")
        if delta is not None and delta.previous_entries:
            if limits.max_added_ratio is not None and delta.added_ratio > limits.max_added_ratio:
                anomalies.append(
                    f"added {delta.added_ratio:.2%} > approved {limits.max_added_ratio:.2%}"
                )
            if (
                limits.max_removed_ratio is not None
                and delta.removed_ratio > limits.max_removed_ratio
            ):
                anomalies.append(
                    f"removed {delta.removed_ratio:.2%} > approved {limits.max_removed_ratio:.2%}"
                )
    if failures:
        return SanityResult(Verdict.FAIL, tuple(failures + anomalies + notes))
    if anomalies:
        return SanityResult(Verdict.ANOMALY, tuple(anomalies + notes))
    return SanityResult(Verdict.PASS, tuple(notes))
