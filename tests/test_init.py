"""
Test suite for IATB package initialization
"""

import random

import numpy as np
import torch
from iatb import __author__, __version__

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_version_exists() -> None:
    """Test that version is defined."""
    assert __version__ is not None
    assert isinstance(__version__, str)
    assert len(__version__) > 0


def test_author_exists() -> None:
    """Test that author is defined."""
    assert __author__ is not None
    assert isinstance(__author__, str)
    assert len(__author__) > 0


def test_version_format() -> None:
    """Test that version follows semantic versioning."""
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
