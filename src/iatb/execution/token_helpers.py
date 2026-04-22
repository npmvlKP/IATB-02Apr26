"""
Helper functions for token management and environment variable handling.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


def load_env_file(env_path: Path) -> dict[str, str]:
    """Load environment variables from a .env file.

    Args:
        env_path: Path to .env file.

    Returns:
        Dictionary of environment variables.
    """
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", maxsplit=1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


def apply_env_defaults(values: Mapping[str, str]) -> None:
    """Apply environment values to os.environ if not already set.

    Args:
        values: Dictionary of environment variable key-value pairs.
    """
    for key, value in values.items():
        if value and key not in os.environ:
            os.environ[key] = value
