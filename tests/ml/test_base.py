import random
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.ml.base import PredictionResult

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_prediction_result_validates_and_normalizes_metadata() -> None:
    result = PredictionResult(
        symbol="NIFTY",
        score=Decimal("0.2"),
        confidence=Decimal("0.8"),
        regime_label="BULL",
        metadata={"source": "lstm"},
    )
    assert result.symbol == "NIFTY"
    assert result.metadata["source"] == "lstm"


def test_prediction_result_rejects_invalid_inputs() -> None:
    with pytest.raises(ConfigError, match="symbol cannot be empty"):
        PredictionResult("", Decimal("0.1"), Decimal("0.5"), "BULL")
    with pytest.raises(ConfigError, match="regime_label cannot be empty"):
        PredictionResult("NIFTY", Decimal("0.1"), Decimal("0.5"), "")
    with pytest.raises(ConfigError, match="confidence must be between 0 and 1"):
        PredictionResult("NIFTY", Decimal("0.1"), Decimal("1.5"), "BULL")
