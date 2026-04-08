import random
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.backtesting.indian_costs import calculate_indian_costs
from iatb.core.exceptions import ConfigError

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_calculate_indian_costs_equity_delivery() -> None:
    result = calculate_indian_costs(Decimal("100000"), "equity_delivery")
    assert result.stt == Decimal("100.000")
    assert result.sebi == Decimal("0.100000")
    assert result.exchange_txn == Decimal("2.9700000")
    assert result.total > Decimal("0")


def test_calculate_indian_costs_mcx_uses_mcx_exchange_rate() -> None:
    result = calculate_indian_costs(Decimal("50000"), "mcx")
    assert result.exchange_txn == Decimal("1.3350000")


def test_calculate_indian_costs_rejects_invalid_inputs() -> None:
    with pytest.raises(ConfigError, match="notional must be positive"):
        calculate_indian_costs(Decimal("0"), "fo")
    with pytest.raises(ConfigError, match="unsupported segment"):
        calculate_indian_costs(Decimal("10000"), "crypto")  # type: ignore[arg-type]
