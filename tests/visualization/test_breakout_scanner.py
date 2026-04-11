import random
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.visualization.breakout_scanner import BreakoutCandidate, rank_breakout_candidates

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_rank_breakout_candidates_orders_by_probability_then_distance() -> None:
    candidates = [
        BreakoutCandidate("A", Decimal("0.8"), Decimal("5"), "breakout"),
        BreakoutCandidate("B", Decimal("0.9"), Decimal("6"), "breakout"),
        BreakoutCandidate("C", Decimal("0.9"), Decimal("2"), "breakout"),
    ]
    ranked = rank_breakout_candidates(candidates, top_n=2, direction="breakout")
    assert [item.symbol for item in ranked] == ["C", "B"]


def test_rank_breakout_candidates_validations() -> None:
    with pytest.raises(ConfigError, match="must be positive"):
        rank_breakout_candidates([], top_n=0)
    with pytest.raises(ConfigError, match="either 'breakout' or 'breakdown'"):
        rank_breakout_candidates([], direction="x")
    with pytest.raises(ConfigError, match="between 0 and 1"):
        BreakoutCandidate("A", Decimal("2"), Decimal("1"), "breakout")
