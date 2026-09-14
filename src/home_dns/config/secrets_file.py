"""Optional systemd-EnvironmentFile-style secret loader (CLAUDE.md §31/§32, A6).

Not wired to any default path — the normal path is real environment variables (set by systemd's
``EnvironmentFile=`` directive itself, which this module has nothing to do with) or a developer's
shell. This is only for a deployment that wants home-dns to read the file directly; it refuses to
read anything world- or group-readable, checked before a single byte is opened.
"""

from __future__ import annotations

import stat
from pathlib import Path

_DISALLOWED_MODE_BITS = 0o077  # group or other: read, write or execute


class SecretFilePermissionError(Exception):
    """The file is readable by group or others and must not be trusted with secrets."""


class SecretFileFormatError(Exception):
    """A line is not a valid ``KEY=VALUE`` pair."""


def load_env_file(path: Path) -> dict[str, str]:
    mode = path.stat().st_mode
    if mode & _DISALLOWED_MODE_BITS:
        raise SecretFilePermissionError(
            f"{path}: refusing to read — permissions {stat.filemode(mode)} "
            "allow group or other access"
        )
    values: dict[str, str] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SecretFileFormatError(f"{path}:{lineno}: not a KEY=VALUE line")
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            raise SecretFileFormatError(f"{path}:{lineno}: empty key")
        values[key] = value.strip().strip('"').strip("'")
    return values
