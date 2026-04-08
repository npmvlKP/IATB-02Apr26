"""
Pytest configuration with deterministic random seeds for reproducibility.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator


# Fixed seed value for reproducibility across all tests
DETERMINISTIC_SEED: int = 42


@pytest.fixture(autouse=True)
def set_deterministic_seeds() -> Generator[None, None, None]:
    """
    Fixture that sets deterministic seeds for all random number generators.

    This fixture runs automatically for all tests (autouse=True) to ensure
    reproducible test results across multiple runs.

    Sets seeds for:
    - Python's random module
    - NumPy's random module (if available)
    - PyTorch's random module (if available)

    Yields:
        None
    """
    # Set Python's built-in random seed
    random.seed(DETERMINISTIC_SEED)

    # Set NumPy random seed if available
    try:
        import numpy as np

        np.random.seed(DETERMINISTIC_SEED)
    except ImportError:
        # NumPy not installed, skip
        pass

    # Set PyTorch random seed if available
    try:
        import torch

        torch.manual_seed(DETERMINISTIC_SEED)
        # Set deterministic mode for PyTorch CUDA operations if CUDA is available
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(DETERMINISTIC_SEED)
            # Enable deterministic algorithms (may impact performance)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
    except (ImportError, OSError):
        # PyTorch not installed or DLL loading failed, skip
        pass

    yield
