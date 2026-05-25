"""
Broker tests conftest — handle DLL and file handle issues on Windows.

Assigns all broker tests to the same xdist group to prevent SQLite
handle leaks and DuckDB DLL initialization race conditions across workers.
"""

import sys

import pytest

if sys.platform == "win32":
    try:
        import duckdb  # noqa: F401 — pre-import to share DLL across xdist forks
    except OSError:
        pass


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Assign all broker tests to a single xdist group on Windows."""
    if sys.platform == "win32":
        for item in items:
            item.add_marker(pytest.mark.xdist_group("broker"))
