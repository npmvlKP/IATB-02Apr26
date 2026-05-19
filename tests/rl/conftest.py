"""
Pytest configuration for RL tests.

This conftest.py mocks stable_baselines3 to avoid Windows DLL
initialization errors when importing the module on Windows systems.
"""

import importlib
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_stable_baselines3(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Mock stable_baselines3 module to avoid Windows DLL initialization errors.

    This fixture automatically applies to all tests in tests/rl/ directory.
    It creates a mock CheckpointCallback class that can be instantiated
    without triggering DLL loading issues.
    """

    def mock_import_module(name: str) -> Any:
        """Mock import_module to intercept stable_baselines3 imports."""
        if name == "stable_baselines3.common.callbacks":
            # Create a mock module with CheckpointCallback
            mock_module = MagicMock()

            # Create a mock CheckpointCallback class
            mock_checkpoint = MagicMock()
            mock_checkpoint.return_value = MagicMock(
                save_freq=10_000, save_path="/mock/path", name_prefix="iatb_rl"
            )

            mock_module.CheckpointCallback = mock_checkpoint
            return mock_module
        # For all other imports, use the real importlib.import_module
        return importlib.import_module(name)

    # Patch importlib.import_module in the callbacks module
    monkeypatch.setattr("iatb.rl.callbacks.importlib.import_module", mock_import_module)
