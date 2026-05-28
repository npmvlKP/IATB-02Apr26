"""
Core tests conftest — handle file handle issues on Windows.

Assigns all core tests to a single xdist group to prevent
file handle leaks across workers.
"""

import logging
import sys

import pytest


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Assign all core tests to a single xdist group on Windows."""
    if sys.platform == "win32":
        for item in items:
            item.add_marker(pytest.mark.xdist_group("core"))


@pytest.fixture(autouse=True)
def _sanitize_logging_handlers() -> None:
    """Remove MagicMock logging handlers left by prior tests.

    When a test patches a module-level logger with MagicMock, the
    MagicMock ends up registered as a handler on the real logger.
    Subsequent tests that emit log records then crash with::

        TypeError: '>=' not supported between 'int' and 'MagicMock'

    This fixture walks every logger before each test and removes any
    handler whose ``level`` attribute is not an int.
    """
    for name in list(logging.Logger.manager.loggerDict):
        logger = logging.getLogger(name)
        for hdlr in list(logger.handlers):
            if not isinstance(getattr(hdlr, "level", None), int):
                logger.removeHandler(hdlr)
    root = logging.getLogger()
    for hdlr in list(root.handlers):
        if not isinstance(getattr(hdlr, "level", None), int):
            root.removeHandler(hdlr)
