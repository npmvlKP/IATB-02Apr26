"""
Test fixtures for core module tests.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_aion_sentiment():
    """Mock aion-sentiment module to avoid ConfigError in tests.

    This fixture automatically mocks the aion-sentiment dependency
    for all tests in this directory, preventing ConfigError when
    SentimentAggregator is initialized.
    """
    # Create a mock aion_sentiment module
    mock_module = MagicMock()
    mock_module.predict = MagicMock(return_value=0.5)

    with patch.dict("sys.modules", {"aion_sentiment": mock_module}):
        yield
