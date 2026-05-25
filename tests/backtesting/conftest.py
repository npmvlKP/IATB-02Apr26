"""
Backtesting tests conftest — handle DLL and file handle issues on Windows.
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
    """Assign all backtesting tests to a single xdist group on Windows."""
    if sys.platform == "win32":
        for item in items:
            item.add_marker(pytest.mark.xdist_group("backtesting"))
