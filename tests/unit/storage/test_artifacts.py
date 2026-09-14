import json
from pathlib import Path

import pytest

from home_dns.storage.artifacts import ArtifactStore, ArtifactStoreError, SourceState, sha256_text

V1 = "artifact v1\n"
V2 = "artifact v2\n"


def _files(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")) if root.exists() else []


def test_empty_store() -> None:
    store = ArtifactStore(Path("/nonexistent/home-dns-test-store"))
    assert store.state("list-a") == SourceState()
    assert store.current("list-a") is None


def test_activate_dry_run_writes_nothing(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "store")
    change = store.activate("list-a", V1, {"k": "v"})
    assert change.dry_run is True and change.changed and change.wrote_artifact
    assert change.after.current == sha256_text(V1)
    assert _files(tmp_path / "store") == []


def test_activate_apply_then_second_version(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    store.activate("list-a", V1, {"n": 1}, dry_run=False)
    change = store.activate("list-a", V2, {"n": 2}, dry_run=False)
    assert change.before.current == sha256_text(V1)
    assert store.state("list-a") == SourceState(current=sha256_text(V2), previous=sha256_text(V1))
    current = store.current("list-a")
    assert current is not None and current.text == V2 and current.metadata == {"n": 2}
    assert not [p for p in _files(tmp_path) if p.endswith(".tmp")]


def test_activating_same_content_is_a_no_op(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    store.activate("list-a", V1, {}, dry_run=False)
    change = store.activate("list-a", V1, {}, dry_run=False)
    assert not change.changed and not change.wrote_artifact


def test_rollback_restores_exact_previous_artifact(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    store.activate("list-a", V1, {}, dry_run=False)
    store.activate("list-a", V2, {}, dry_run=False)
    dry = store.rollback("list-a")
    assert dry.dry_run and store.state("list-a").current == sha256_text(V2)
    store.rollback("list-a", dry_run=False)
    restored = store.current("list-a")
    assert restored is not None and restored.text == V1
    assert store.state("list-a").previous == sha256_text(V2)


def test_rollback_without_previous_is_refused(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    with pytest.raises(ArtifactStoreError, match="no previous"):
        store.rollback("list-a")
    store.activate("list-a", V1, {}, dry_run=False)
    with pytest.raises(ArtifactStoreError, match="no previous"):
        store.rollback("list-a", dry_run=False)


def test_corrupted_artifact_is_detected(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    store.activate("list-a", V1, {}, dry_run=False)
    store.activate("list-a", V2, {}, dry_run=False)
    (tmp_path / "list-a" / "artifacts" / f"{sha256_text(V1)}.txt").write_text("tampered\n")
    with pytest.raises(ArtifactStoreError, match="integrity"):
        store.rollback("list-a", dry_run=False)
    assert store.current("list-a") is not None


def test_missing_artifact_and_corrupted_state(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    store.activate("list-a", V1, {}, dry_run=False)
    (tmp_path / "list-a" / "artifacts" / f"{sha256_text(V1)}.txt").unlink()
    with pytest.raises(ArtifactStoreError, match="missing"):
        store.current("list-a")
    (tmp_path / "list-a" / "state.json").write_text("{not json")
    with pytest.raises(ArtifactStoreError, match="corrupted state"):
        store.state("list-a")


@pytest.mark.parametrize("source_id", ["../escape", "List-A", "", "a/b"])
def test_invalid_source_ids_are_rejected(tmp_path: Path, source_id: str) -> None:
    with pytest.raises(ArtifactStoreError, match="invalid source id"):
        ArtifactStore(tmp_path).state(source_id)


def test_invalid_hash_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ArtifactStoreError, match="invalid artifact hash"):
        ArtifactStore(tmp_path).read("list-a", "../../etc/passwd")


def test_metadata_is_written_as_json(tmp_path: Path) -> None:
    ArtifactStore(tmp_path).activate("list-a", V1, {"b": 2, "a": 1}, dry_run=False)
    meta = tmp_path / "list-a" / "artifacts" / f"{sha256_text(V1)}.json"
    assert json.loads(meta.read_text()) == {"a": 1, "b": 2}


# ------------------------------------------------------------ retention: current/previous/backup

VERSIONS = [f"artifact v{i}\n" for i in range(1, 6)]


def _artifact_names(root: Path, source_id: str = "list-a") -> set[str]:
    directory = root / source_id / "artifacts"
    return {p.name for p in directory.iterdir()} if directory.is_dir() else set()


def _expected_names(*texts: str) -> set[str]:
    return {f"{sha256_text(t)}.{ext}" for t in texts for ext in ("txt", "json")}


def test_retention_keeps_exactly_three_versions(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    for text in VERSIONS:
        store.activate("list-a", text, {"v": text}, dry_run=False)
    v3, v4, v5 = VERSIONS[2:]
    assert store.state("list-a") == SourceState(
        current=sha256_text(v5), previous=sha256_text(v4), backup=sha256_text(v3)
    )
    assert _artifact_names(tmp_path) == _expected_names(v3, v4, v5)
    for sha in store.state("list-a").retained():
        store.read("list-a", sha)  # all retained artifacts pass integrity


def test_pruning_reports_removed_files_and_dry_run_deletes_nothing(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    for text in VERSIONS[:3]:
        store.activate("list-a", text, {}, dry_run=False)
    before = _artifact_names(tmp_path)
    dry = store.activate("list-a", VERSIONS[3], {})
    assert set(dry.pruned) == _expected_names(VERSIONS[0])
    assert _artifact_names(tmp_path) == before
    applied = store.activate("list-a", VERSIONS[3], {}, dry_run=False)
    assert set(applied.pruned) == _expected_names(VERSIONS[0])
    assert _artifact_names(tmp_path) == _expected_names(*VERSIONS[1:4])


def test_pruning_happens_only_after_state_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ArtifactStore(tmp_path)
    for text in VERSIONS[:3]:
        store.activate("list-a", text, {}, dry_run=False)
    state_before = store.state("list-a")
    names_before = _artifact_names(tmp_path)

    def crash(*args: object, **kwargs: object) -> None:
        raise OSError("power loss while writing state")

    monkeypatch.setattr(store, "_write_state", crash)
    with pytest.raises(OSError, match="power loss"):
        store.activate("list-a", VERSIONS[3], {}, dry_run=False)
    assert store.state("list-a") == state_before
    assert names_before <= _artifact_names(tmp_path)  # nothing referenced was deleted
    for sha in state_before.retained():
        store.read("list-a", sha)

    monkeypatch.undo()
    store.activate("list-a", VERSIONS[3], {}, dry_run=False)  # recovery prunes leftovers
    assert _artifact_names(tmp_path) == _expected_names(*VERSIONS[1:4])


def test_leftover_temp_files_are_pruned_but_foreign_files_are_never_touched(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    store.activate("list-a", VERSIONS[0], {}, dry_run=False)
    directory = tmp_path / "list-a" / "artifacts"
    leftover = directory / f".{'a' * 64}.txt.tmp"
    foreign = [directory / "notes.txt", directory / "README", directory / f"{'b' * 64}.bak"]
    leftover.write_text("partial")
    for path in foreign:
        path.write_text("keep me")
    store.activate("list-a", VERSIONS[1], {}, dry_run=False)
    assert not leftover.exists()
    assert all(path.exists() for path in foreign)


def test_prune_failure_does_not_break_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ArtifactStore(tmp_path)
    for text in VERSIONS[:3]:
        store.activate("list-a", text, {}, dry_run=False)

    def refuse(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError("read-only")

    monkeypatch.setattr(Path, "unlink", refuse)
    change = store.activate("list-a", VERSIONS[3], {}, dry_run=False)
    monkeypatch.undo()
    assert store.state("list-a").current == sha256_text(VERSIONS[3])
    assert change.pruned  # reported, retried on the next activation
    store.activate("list-a", VERSIONS[4], {}, dry_run=False)
    assert _artifact_names(tmp_path) == _expected_names(*VERSIONS[2:5])


def test_rollback_keeps_backup_and_reactivating_an_older_version(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    for text in VERSIONS[:3]:
        store.activate("list-a", text, {}, dry_run=False)
    store.rollback("list-a", dry_run=False)
    v1, v2, v3 = (sha256_text(t) for t in VERSIONS[:3])
    assert store.state("list-a") == SourceState(current=v2, previous=v3, backup=v1)
    change = store.activate("list-a", VERSIONS[0], {}, dry_run=False)  # already stored as backup
    assert not change.wrote_artifact and change.pruned == ()
    assert store.state("list-a") == SourceState(current=v1, previous=v2, backup=v3)


def test_state_files_without_backup_key_are_still_readable(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    store.activate("list-a", VERSIONS[0], {}, dry_run=False)
    store.activate("list-a", VERSIONS[1], {}, dry_run=False)
    state_path = tmp_path / "list-a" / "state.json"
    legacy = json.loads(state_path.read_text())
    del legacy["backup"]
    state_path.write_text(json.dumps(legacy))
    assert store.state("list-a").backup is None
    store.activate("list-a", VERSIONS[2], {}, dry_run=False)
    assert store.state("list-a").backup == sha256_text(VERSIONS[0])
