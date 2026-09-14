from pathlib import Path

from home_dns.storage.disk import SystemDiskUsage, directory_size_bytes


def test_system_disk_usage_reads_real_filesystem(tmp_path: Path) -> None:
    usage = SystemDiskUsage().get(tmp_path)
    assert usage.total_bytes > 0
    assert 0 <= usage.used_bytes <= usage.total_bytes
    assert usage.free_bytes >= 0


def test_directory_size_bytes_sums_nested_files(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_bytes(b"x" * 10)
    nested = tmp_path / "sub"
    nested.mkdir()
    (nested / "b.txt").write_bytes(b"y" * 20)
    assert directory_size_bytes(tmp_path) == 30


def test_directory_size_bytes_missing_directory_is_zero(tmp_path: Path) -> None:
    assert directory_size_bytes(tmp_path / "does-not-exist") == 0


def test_directory_size_bytes_does_not_double_count_symlinks(tmp_path: Path) -> None:
    real = tmp_path / "real.txt"
    real.write_bytes(b"z" * 40)
    (tmp_path / "link.txt").symlink_to(real)
    assert directory_size_bytes(tmp_path) == 40


def test_directory_size_bytes_empty_directory(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert directory_size_bytes(empty) == 0


def test_system_disk_usage_handles_nonexistent_path_via_nearest_ancestor(tmp_path: Path) -> None:
    missing = tmp_path / "does" / "not" / "exist" / "yet"
    usage = SystemDiskUsage().get(missing)
    assert usage.total_bytes > 0
