import random
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.visualization.portfolio_view import PositionSnapshot, build_portfolio_snapshot

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_build_portfolio_snapshot() -> None:
    positions = [
        PositionSnapshot("NIFTY", Decimal("2"), Decimal("100"), Decimal("110")),
        PositionSnapshot("BANKNIFTY", Decimal("1"), Decimal("200"), Decimal("190")),
    ]
    snapshot = build_portfolio_snapshot(
        positions, [Decimal("100000"), Decimal("98000"), Decimal("102000")]
    )
    assert snapshot["position_count"] == 2
    assert snapshot["total_unrealized_pnl"] == Decimal("10")
    assert snapshot["max_drawdown"] > Decimal("0")


def test_build_portfolio_snapshot_validation() -> None:
    with pytest.raises(ConfigError, match="cannot be empty"):
        build_portfolio_snapshot([], [])
