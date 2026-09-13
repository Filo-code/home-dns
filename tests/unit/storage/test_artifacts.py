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
