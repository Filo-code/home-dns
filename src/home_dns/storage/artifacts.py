"""Content-addressed filesystem store for validated blocklist artifacts.

Layout (per source):

    <root>/<source_id>/artifacts/<sha256>.txt    rendered artifact (immutable)
    <root>/<source_id>/artifacts/<sha256>.json   metadata (stats, origin, timestamps)
    <root>/<source_id>/state.json                {"current": sha|null, "previous": sha|null}

Writes are atomic (temp file + fsync + rename). Every mutating method defaults to dry_run=True.
Reads verify the SHA-256 of the artifact against its name, so on-disk corruption is detected.
Retention/cleanup of old artifacts is handled by maintenance (A4).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SOURCE_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
_SHA_RE = re.compile(r"[0-9a-f]{64}")


class ArtifactStoreError(Exception):
    """The store is inconsistent, corrupted, or the operation is not possible."""


@dataclass(frozen=True)
class SourceState:
    current: str | None = None
    previous: str | None = None


@dataclass(frozen=True)
class StoredArtifact:
    sha256: str
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class StoreChange:
    dry_run: bool
    source_id: str
    before: SourceState
    after: SourceState
    wrote_artifact: bool

    @property
    def changed(self) -> bool:
        return self.before != self.after


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _source_dir(self, source_id: str) -> Path:
        if not _SOURCE_ID_RE.fullmatch(source_id):
            raise ArtifactStoreError(f"invalid source id {source_id!r}")
        return self._root / source_id

    def _artifact_paths(self, source_id: str, sha: str) -> tuple[Path, Path]:
        if not _SHA_RE.fullmatch(sha):
            raise ArtifactStoreError(f"invalid artifact hash {sha!r}")
        base = self._source_dir(source_id) / "artifacts" / sha
        return base.with_suffix(".txt"), base.with_suffix(".json")

    def state(self, source_id: str) -> SourceState:
        path = self._source_dir(source_id) / "state.json"
        if not path.is_file():
            return SourceState()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SourceState(current=data.get("current"), previous=data.get("previous"))
        except (json.JSONDecodeError, AttributeError) as exc:
            raise ArtifactStoreError(f"{path}: corrupted state file") from exc

    def read(self, source_id: str, sha: str) -> StoredArtifact:
        text_path, meta_path = self._artifact_paths(source_id, sha)
        if not text_path.is_file():
            raise ArtifactStoreError(f"artifact {sha} for {source_id} is missing")
        text = text_path.read_text(encoding="utf-8")
        if sha256_text(text) != sha:
            raise ArtifactStoreError(f"artifact {sha} for {source_id} failed integrity check")
        metadata = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
        return StoredArtifact(sha, text, metadata)

    def current(self, source_id: str) -> StoredArtifact | None:
        sha = self.state(source_id).current
        return self.read(source_id, sha) if sha else None

    def _write_state(self, source_id: str, state: SourceState) -> None:
        payload = json.dumps({"current": state.current, "previous": state.previous}, indent=2)
        _atomic_write(self._source_dir(source_id) / "state.json", payload.encode("utf-8"))

    def activate(
        self, source_id: str, text: str, metadata: dict[str, Any], *, dry_run: bool = True
    ) -> StoreChange:
        """Make ``text`` the current artifact; the old current becomes previous."""
        sha = sha256_text(text)
        before = self.state(source_id)
        if before.current == sha:
            return StoreChange(dry_run, source_id, before, before, wrote_artifact=False)
        after = SourceState(current=sha, previous=before.current)
        text_path, meta_path = self._artifact_paths(source_id, sha)
        write_needed = not text_path.is_file()
        if not dry_run:
            if write_needed:
                _atomic_write(text_path, text.encode("utf-8"))
            _atomic_write(meta_path, json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8"))
            self.read(source_id, sha)  # verify what was written before switching pointers
            self._write_state(source_id, after)
        return StoreChange(dry_run, source_id, before, after, wrote_artifact=write_needed)

    def rollback(self, source_id: str, *, dry_run: bool = True) -> StoreChange:
        """Swap current and previous. The previous artifact must exist and pass integrity."""
        before = self.state(source_id)
        if before.previous is None:
            raise ArtifactStoreError(f"{source_id}: no previous artifact to roll back to")
        self.read(source_id, before.previous)
        after = SourceState(current=before.previous, previous=before.current)
        if not dry_run:
            self._write_state(source_id, after)
        return StoreChange(dry_run, source_id, before, after, wrote_artifact=False)
