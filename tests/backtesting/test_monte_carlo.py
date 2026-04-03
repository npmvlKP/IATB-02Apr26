from decimal import Decimal

import pytest
from iatb.backtesting.monte_carlo import MonteCarloAnalyzer
from iatb.core.exceptions import ConfigError


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
