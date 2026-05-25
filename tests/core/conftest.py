"""
Core tests conftest — handle file handle issues on Windows.

Assigns all core tests to a single xdist group to prevent
file handle leaks across workers.
"""

import sys

import pytest


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Assign all core tests to a single xdist group on Windows."""
    if sys.platform == "win32":
        for item in items:
            item.add_marker(pytest.mark.xdist_group("core"))
