import random
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.risk.circuit_breaker import evaluate_circuit_breaker

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_circuit_breaker_levels() -> None:
    assert evaluate_circuit_breaker(Decimal("5")).level == 0
    assert evaluate_circuit_breaker(Decimal("10")).level == 1
    assert evaluate_circuit_breaker(Decimal("15")).level == 2
    assert evaluate_circuit_breaker(Decimal("20")).level == 3


def test_circuit_breaker_rejects_negative_values() -> None:
    with pytest.raises(ConfigError, match="non-negative"):
        evaluate_circuit_breaker(Decimal("-1"))
