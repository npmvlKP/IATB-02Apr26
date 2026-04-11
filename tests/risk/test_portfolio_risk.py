import random
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.risk.portfolio_risk import (
    build_risk_snapshot,
    compute_cvar,
    compute_max_drawdown,
    compute_var,
)

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_portfolio_risk_metrics_and_snapshot() -> None:
    returns = [
        Decimal("0.01"),
        Decimal("-0.02"),
        Decimal("0.015"),
        Decimal("-0.01"),
        Decimal("0.005"),
    ]
    equity_curve = [Decimal("100"), Decimal("98"), Decimal("101"), Decimal("97"), Decimal("102")]
    var_95 = compute_var(returns)
    cvar_95 = compute_cvar(returns)
    max_dd = compute_max_drawdown(equity_curve)
    snapshot = build_risk_snapshot(returns, equity_curve, max_allowed_drawdown=Decimal("0.03"))
    assert var_95 >= Decimal("0")
    assert cvar_95 >= var_95
    assert max_dd > Decimal("0")
    assert snapshot.drawdown_breached


def test_portfolio_risk_validations() -> None:
    with pytest.raises(ConfigError, match="at least two points"):
        compute_var([Decimal("0.1")])
    with pytest.raises(ConfigError, match="between 0 and 1"):
        compute_var([Decimal("0.1"), Decimal("-0.1")], confidence=Decimal("1"))
    with pytest.raises(ConfigError, match="at least two points"):
        compute_max_drawdown([Decimal("100")])
