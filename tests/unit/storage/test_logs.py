import logging
from pathlib import Path

from home_dns.storage.logs import build_rotating_file_handler, log_directory_usage_bytes


def test_handler_creates_parent_directory_and_writes(tmp_path: Path) -> None:
    log_path = tmp_path / "sub" / "app.log"
    handler = build_rotating_file_handler(log_path, max_bytes=10_000, backup_count=2)
    try:
        logger = logging.getLogger("test-a4-logs")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.warning("hello")
        handler.flush()
        assert log_path.is_file()
        assert "hello" in log_path.read_text()
    finally:
        handler.close()


def test_rotation_bounds_total_size(tmp_path: Path) -> None:
    log_path = tmp_path / "app.log"
    max_bytes = 500
    backup_count = 3
    handler = build_rotating_file_handler(log_path, max_bytes=max_bytes, backup_count=backup_count)
    try:
        logger = logging.getLogger("test-a4-logs-rotation")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        for i in range(2000):
            logger.info("padding line %d %s", i, "x" * 40)
        handler.flush()
    finally:
        handler.close()
    total = log_directory_usage_bytes(tmp_path)
    # bounded regardless of how much was logged: at most (backup_count + 1) files near max_bytes
    assert total <= max_bytes * (backup_count + 1) * 1.5


def test_log_directory_usage_missing_dir_is_zero(tmp_path: Path) -> None:
    assert log_directory_usage_bytes(tmp_path / "nope") == 0
