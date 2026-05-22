"""Storage tests conftest — handle DuckDB DLL loading on Windows.

DuckDB's native library (duckdb.dll) has a known issue on Windows where
concurrent process forks under xdist cause DLL initialization failures
(WinError 1114 / "Not enough memory resources"). Assigning all storage
tests to the same xdist_group forces them onto a single worker, which
avoids concurrent DLL initialization.
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
    """Assign all storage tests to a single xdist group."""
    for item in items:
        item.add_marker(pytest.mark.xdist_group("storage"))
