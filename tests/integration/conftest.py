"""
Integration tests conftest — handle SQLite/DuckDB issues on Windows.

Assigns all integration tests to a single xdist group to prevent
file handle leaks and DLL initialization race conditions across workers.
"""

import sys

import pytest

if sys.platform == "win32":
    try:
        import duckdb  # noqa: F401
    except OSError:
        pass


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Assign all integration tests to a single xdist group on Windows."""
    if sys.platform == "win32":
        for item in items:
            item.add_marker(pytest.mark.xdist_group("integration"))
