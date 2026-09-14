from datetime import UTC, datetime
from pathlib import Path

import pytest

from home_dns.core.monitoring import FreshnessCounter, Incident, IncidentState
from home_dns.storage.monitoring import MonitoringStore, MonitoringStoreError

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def test_load_incident_defaults_to_ok_when_no_file_exists(tmp_path: Path) -> None:
    store = MonitoringStore(tmp_path)
    incident = store.load_incident("storage")
    assert incident == Incident("storage")


def test_save_then_load_incident_round_trips(tmp_path: Path) -> None:
    store = MonitoringStore(tmp_path)
    incident = Incident(
        "storage",
        IncidentState.INCIDENT,
        consecutive_problem=3,
        consecutive_ok=0,
        opened_at=NOW,
        last_change_at=NOW,
        last_notified_at=NOW,
    )
    store.save_incident(incident, dry_run=False)
    loaded = store.load_incident("storage")
    assert loaded == incident


def test_save_incident_dry_run_does_not_write(tmp_path: Path) -> None:
    store = MonitoringStore(tmp_path)
    store.save_incident(Incident("storage", IncidentState.SUSPECT), dry_run=True)
    assert store.load_incident("storage") == Incident("storage")
    assert not (tmp_path / "incidents" / "storage.json").exists()


def test_load_incident_corrupted_file_raises(tmp_path: Path) -> None:
    incidents_dir = tmp_path / "incidents"
    incidents_dir.mkdir(parents=True)
    (incidents_dir / "storage.json").write_text("not json", encoding="utf-8")
    with pytest.raises(MonitoringStoreError):
        MonitoringStore(tmp_path).load_incident("storage")


def test_load_freshness_corrupted_file_raises(tmp_path: Path) -> None:
    freshness_dir = tmp_path / "blocklist-freshness"
    freshness_dir.mkdir(parents=True)
    (freshness_dir / "list-a.json").write_text("not json", encoding="utf-8")
    with pytest.raises(MonitoringStoreError):
        MonitoringStore(tmp_path).load_freshness("list-a")


def test_load_freshness_defaults_to_zero_when_no_file_exists(tmp_path: Path) -> None:
    store = MonitoringStore(tmp_path)
    assert store.load_freshness("list-a") == FreshnessCounter("list-a")


def test_save_then_load_freshness_round_trips(tmp_path: Path) -> None:
    store = MonitoringStore(tmp_path)
    counter = FreshnessCounter("list-a", consecutive_kept_previous=2)
    store.save_freshness(counter, dry_run=False)
    assert store.load_freshness("list-a") == counter


def test_save_freshness_dry_run_does_not_write(tmp_path: Path) -> None:
    store = MonitoringStore(tmp_path)
    store.save_freshness(FreshnessCounter("list-a", 5), dry_run=True)
    assert store.load_freshness("list-a") == FreshnessCounter("list-a")
    assert not (tmp_path / "blocklist-freshness" / "list-a.json").exists()


def test_state_for_one_check_or_source_does_not_affect_another(tmp_path: Path) -> None:
    store = MonitoringStore(tmp_path)
    store.save_incident(Incident("storage", IncidentState.INCIDENT), dry_run=False)
    store.save_freshness(FreshnessCounter("list-a", 3), dry_run=False)
    assert store.load_incident("dns") == Incident("dns")
    assert store.load_freshness("list-b") == FreshnessCounter("list-b")


@pytest.mark.parametrize("name", ["../escape", "UPPER", "has space", "", "a/b"])
def test_invalid_names_are_rejected(tmp_path: Path, name: str) -> None:
    store = MonitoringStore(tmp_path)
    with pytest.raises(MonitoringStoreError):
        store.save_incident(Incident(name), dry_run=False)
