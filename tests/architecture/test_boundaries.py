"""Enforce the package boundaries from docs/specs/a0-foundations.md §9."""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "home_dns"

FORBIDDEN: dict[str, set[str]] = {
    "core": {
        "home_dns.config",
        "home_dns.providers",
        "home_dns.storage",
        "home_dns.api",
        "home_dns.bootstrap",
        "home_dns.cli",
        "fastapi",
        "httpx",
        "sqlite3",
        "yaml",
        "uvicorn",
    },
    "config": {
        "home_dns.providers",
        "home_dns.storage",
        "home_dns.api",
        "home_dns.bootstrap",
        "home_dns.cli",
        "fastapi",
        "httpx",
        "sqlite3",
        "uvicorn",
    },
    "providers": {
        "home_dns.config",
        "home_dns.storage",
        "home_dns.api",
        "home_dns.bootstrap",
        "home_dns.cli",
        "fastapi",
        "sqlite3",
        "yaml",
        "uvicorn",
    },
    "storage": {
        "home_dns.config",
        "home_dns.providers",
        "home_dns.api",
        "home_dns.bootstrap",
        "home_dns.cli",
        "fastapi",
        "httpx",
        "yaml",
        "uvicorn",
    },
    "api": {
        "home_dns.providers.mock",
        "home_dns.bootstrap",
        "home_dns.cli",
        "sqlite3",
        "yaml",
        "uvicorn",
    },
    "bootstrap": {"home_dns.api", "home_dns.cli", "fastapi", "uvicorn"},
}


def _module_files(package: str) -> list[Path]:
    path = SRC / package
    return sorted(path.rglob("*.py")) if path.is_dir() else [SRC / f"{package}.py"]


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _violates(imported: str, forbidden: str) -> bool:
    return imported == forbidden or imported.startswith(forbidden + ".")


@pytest.mark.parametrize("package", sorted(FORBIDDEN))
def test_package_respects_import_boundaries(package: str) -> None:
    files = _module_files(package)
    assert files, f"no source files found for {package}"
    violations = [
        f"{path.relative_to(SRC)} imports {name}"
        for path in files
        for name in sorted(_imports(path))
        if any(_violates(name, forbidden) for forbidden in FORBIDDEN[package])
    ]
    assert not violations, "\n".join(violations)


def test_sqlite3_is_only_used_by_storage() -> None:
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if "sqlite3" in _imports(path) and not path.is_relative_to(SRC / "storage")
    ]
    assert not offenders
