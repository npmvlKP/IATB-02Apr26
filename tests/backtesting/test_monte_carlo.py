import random
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.backtesting.monte_carlo import MonteCarloAnalyzer
from iatb.core.exceptions import ConfigError

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_monte_carlo_analyzer_runs_with_seeded_permutations() -> None:
    analyzer = MonteCarloAnalyzer(permutations=20, seed=7)
    result = analyzer.run([Decimal("0.01"), Decimal("-0.005"), Decimal("0.008"), Decimal("0.004")])
    assert result.permutations == 20
    assert isinstance(result.robust, bool)


def test_monte_carlo_analyzer_rejects_invalid_inputs() -> None:
    with pytest.raises(ConfigError, match="permutations must be positive"):
        MonteCarloAnalyzer(permutations=0)
    analyzer = MonteCarloAnalyzer(permutations=5)
    with pytest.raises(ConfigError, match="at least two points"):
        analyzer.run([Decimal("0.01")])


def test_monte_carlo_zero_dispersion_returns_zero_sharpe() -> None:
    """Test that zero dispersion (constant returns) returns zero Sharpe (line 58)."""
    analyzer = MonteCarloAnalyzer(permutations=5, seed=42)
    # All returns are the same, so dispersion = 0
    constant_returns = [Decimal("0.01"), Decimal("0.01"), Decimal("0.01")]
    result = analyzer.run(constant_returns)
    # When dispersion is 0, should return 0
    assert result.base_sharpe == Decimal("0")
