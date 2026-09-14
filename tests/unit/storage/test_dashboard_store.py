from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from home_dns.core.auth import Role
from home_dns.core.metrics import Resolution, Rollup
from home_dns.storage.dashboard import DashboardStore, DeviceUpsert, FlushBatch

T0 = datetime(2026, 9, 13, 10, tzinfo=UTC)


@pytest.fixture
def store(tmp_path: Path) -> DashboardStore:
    s = DashboardStore.open(tmp_path / "data")
    yield s  # type: ignore[misc]
    s.close()


def _rollup(total: int, blocked: int = 0) -> Rollup:
    return Rollup(
        total=total,
        blocked=blocked,
        forwarded=total - blocked,
        blocked_by_source={"list-a": blocked} if blocked else {},
    )


def _device(device_id: int = 1, mac: str | None = "00:00:5e:00:53:10") -> DeviceUpsert:
    return DeviceUpsert(device_id, mac, "pc-01.example", T0, T0)


def test_open_is_idempotent(tmp_path: Path) -> None:
    DashboardStore.open(tmp_path).close()
    DashboardStore.open(tmp_path).close()
    assert (tmp_path / "home-dns.db").is_file()


def test_user_upsert_revokes_sessions(store: DashboardStore) -> None:
    store.set_user("anna", Role.ADMIN, "hash-1", now=T0)
    store.create_session("digest", "anna", "csrf", now=T0)
    assert store.get_session("digest") is not None
    store.set_user("anna", Role.VIEWER, "hash-2", now=T0)
    user = store.get_user("anna")
    assert user is not None and user.role is Role.VIEWER and user.password_hash == "hash-2"
    assert store.get_session("digest") is None
    assert store.list_users() == [("anna", Role.VIEWER)]
    assert store.get_user("nobody") is None


def test_session_touch_delete_and_expiry(store: DashboardStore) -> None:
    store.set_user("anna", Role.ADMIN, "h", now=T0)
    store.create_session("old", "anna", "c1", now=T0)
    store.create_session("new", "anna", "c2", now=T0 + timedelta(hours=10))
    store.touch_session("old", now=T0 + timedelta(hours=1))
    session = store.get_session("old")
    assert session is not None and session.last_seen_at == T0 + timedelta(hours=1)
    assert session.role is Role.ADMIN and session.csrf_token == "c1"
    removed = store.delete_expired_sessions(
        idle_before=T0 + timedelta(hours=5), created_before=T0 - timedelta(days=7)
    )
    assert removed == 1
    assert store.get_session("old") is None
    store.delete_session("new")
    assert store.get_session("new") is None


def test_flush_merges_rollups_and_keeps_user_fields(store: DashboardStore) -> None:
    store.flush(
        FlushBatch(
            watermark=T0,
            devices=(_device(),),
            addresses=(("192.0.2.10", 1, T0),),
            rollups=((Resolution.HOUR, T0, 1, _rollup(10, 2)),),
        )
    )
    assert store.rename_device(1, "Michele PC")
    assert store.assign_group(1, "GAMING")
    later = T0 + timedelta(minutes=5)
    store.flush(
        FlushBatch(
            watermark=later,
            devices=(DeviceUpsert(1, None, None, later, later),),
            addresses=(("2001:db8::10", 1, later),),
            rollups=((Resolution.HOUR, T0, 1, _rollup(5, 1)),),
        )
    )
    device = store.get_device(1)
    assert device is not None
    assert (device.custom_name, device.group_id) == ("Michele PC", "GAMING")
    assert device.mac == "00:00:5e:00:53:10" and device.hostname == "pc-01.example"
    assert (device.first_seen, device.last_seen) == (T0, later)
    assert device.addresses == ("192.0.2.10", "2001:db8::10")
    [(start, device_id, merged)] = store.rollups(Resolution.HOUR, T0, T0 + timedelta(hours=1))
    assert (start, device_id, merged.total, merged.blocked) == (T0, 1, 15, 3)
    assert merged.blocked_by_source == {"list-a": 3}
    assert store.load_watermark() == later


def test_unknown_device_updates_report_not_found(store: DashboardStore) -> None:
    assert store.get_device(99) is None
    assert not store.rename_device(99, "x")
    assert not store.assign_group(99, "PC")


def test_retention_deletes_only_older_rows_of_that_resolution(store: DashboardStore) -> None:
    old, new = T0 - timedelta(days=3), T0
    store.flush(
        FlushBatch(
            watermark=T0,
            devices=(_device(),),
            rollups=(
                (Resolution.MINUTE, old, 1, _rollup(1)),
                (Resolution.MINUTE, new, 1, _rollup(1)),
                (Resolution.DAY, old, 1, _rollup(1)),
            ),
        )
    )
    store.flush(
        FlushBatch(watermark=T0, retention_cutoffs={Resolution.MINUTE: T0 - timedelta(hours=48)})
    )
    assert [r[0] for r in store.rollups(Resolution.MINUTE, old, T0 + timedelta(1))] == [new]
    assert len(store.rollups(Resolution.DAY, old, T0)) == 1


def test_failed_flush_writes_nothing(store: DashboardStore) -> None:
    # Rollup for a device that does not exist violates the foreign key -> whole batch rolls back.
    with pytest.raises(Exception, match="FOREIGN KEY"):
        store.flush(FlushBatch(watermark=T0, rollups=((Resolution.MINUTE, T0, 42, _rollup(1)),)))
    assert store.load_watermark() is None


def test_rollups_filter_by_device(store: DashboardStore) -> None:
    store.flush(
        FlushBatch(
            watermark=T0,
            devices=(_device(1), _device(2, None)),
            rollups=(
                (Resolution.MINUTE, T0, 1, _rollup(1)),
                (Resolution.MINUTE, T0, 2, _rollup(2)),
            ),
        )
    )
    rows = store.rollups(Resolution.MINUTE, T0, T0 + timedelta(minutes=1), device_id=2)
    assert [(r[1], r[2].total) for r in rows] == [(2, 2)]


def test_device_lists_only_recent_addresses_and_old_ones_are_pruned(store: DashboardStore) -> None:
    long_ago = T0 - timedelta(days=400)
    store.flush(
        FlushBatch(
            watermark=T0,
            devices=(_device(),),
            addresses=(
                ("2001:db8::1", 1, long_ago),
                ("2001:db8::2", 1, T0 - timedelta(days=3)),
                ("2001:db8::3", 1, T0),
            ),
        )
    )
    device = store.get_device(1)
    assert device is not None and device.addresses == ("2001:db8::3",)
    store.flush(
        FlushBatch(watermark=T0, retention_cutoffs={Resolution.DAY: T0 - timedelta(days=365)})
    )
    assert set(store.address_bindings()) == {"2001:db8::2", "2001:db8::3"}
