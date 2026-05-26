"""Comprehensive coverage tests for iatb.risk.portfolio_risk."""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.risk.portfolio_risk import (
    PortfolioRiskSnapshot,
    _validate_returns,
    build_risk_snapshot,
    compute_cvar,
    compute_max_drawdown,
    compute_var,
)


class TestComputeVar:
    def test_basic_returns(self) -> None:
        returns = [Decimal("-0.05"), Decimal("0.02"), Decimal("-0.03"), Decimal("0.01")]
        result = compute_var(returns, Decimal("0.95"))
        assert result > Decimal("0")

    def test_sorted_returns_index(self) -> None:
        returns = [
            Decimal("-0.10"),
            Decimal("-0.05"),
            Decimal("0"),
            Decimal("0.05"),
            Decimal("0.10"),
        ]
        result = compute_var(returns, Decimal("0.75"))
        assert result == Decimal("0.05")

    def test_default_confidence(self) -> None:
        returns = [Decimal("-0.10"), Decimal("-0.05"), Decimal("0.01")]
        result = compute_var(returns)
        assert result > Decimal("0")

    def test_two_returns(self) -> None:
        returns = [Decimal("-0.03"), Decimal("0.02")]
        result = compute_var(returns, Decimal("0.95"))
        assert isinstance(result, Decimal)

    def test_all_negative_returns(self) -> None:
        returns = [Decimal("-0.10"), Decimal("-0.20")]
        result = compute_var(returns)
        assert result > Decimal("0")

    def test_all_positive_returns(self) -> None:
        returns = [Decimal("0.10"), Decimal("0.20")]
        result = compute_var(returns)
        assert result >= Decimal("0")

    def test_empty_returns_raises(self) -> None:
        with pytest.raises(ConfigError, match="at least two"):
            compute_var([], Decimal("0.95"))

    def test_single_return_raises(self) -> None:
        with pytest.raises(ConfigError, match="at least two"):
            compute_var([Decimal("0.01")], Decimal("0.95"))

    def test_zero_confidence_raises(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            compute_var([Decimal("0.01"), Decimal("0.02")], Decimal("0"))

    def test_one_confidence_raises(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            compute_var([Decimal("0.01"), Decimal("0.02")], Decimal("1"))

    def test_negative_confidence_raises(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            compute_var([Decimal("0.01"), Decimal("0.02")], Decimal("-0.5"))


class TestComputeCvar:
    def test_basic_cvar(self) -> None:
        returns = [Decimal("-0.10"), Decimal("-0.05"), Decimal("0.01"), Decimal("0.02")]
        result = compute_cvar(returns, Decimal("0.95"))
        assert result > Decimal("0")

    def test_cvar_ge_var(self) -> None:
        returns = [Decimal("-0.10"), Decimal("-0.05"), Decimal("0.01"), Decimal("0.02")]
        var = compute_var(returns, Decimal("0.95"))
        cvar = compute_cvar(returns, Decimal("0.95"))
        assert cvar >= var

    def test_empty_tail_returns_var(self) -> None:
        returns = [Decimal("0.01"), Decimal("0.02"), Decimal("0.03"), Decimal("0.04")]
        var = compute_var(returns, Decimal("0.95"))
        cvar = compute_cvar(returns, Decimal("0.95"))
        assert cvar == var

    def test_default_confidence(self) -> None:
        returns = [Decimal("-0.10"), Decimal("-0.05")]
        result = compute_cvar(returns)
        assert result > Decimal("0")


class TestComputeMaxDrawdown:
    def test_basic_drawdown(self) -> None:
        curve = [Decimal("100"), Decimal("110"), Decimal("95"), Decimal("105")]
        result = compute_max_drawdown(curve)
        assert result > Decimal("0")

    def test_no_drawdown(self) -> None:
        curve = [Decimal("100"), Decimal("110"), Decimal("120")]
        result = compute_max_drawdown(curve)
        assert result == Decimal("0")

    def test_declining_curve(self) -> None:
        curve = [Decimal("100"), Decimal("90"), Decimal("80")]
        result = compute_max_drawdown(curve)
        assert result > Decimal("0")

    def test_single_point_raises(self) -> None:
        with pytest.raises(ConfigError, match="at least two"):
            compute_max_drawdown([Decimal("100")])

    def test_empty_curve_raises(self) -> None:
        with pytest.raises(ConfigError, match="at least two"):
            compute_max_drawdown([])

    def test_drawdown_calculation(self) -> None:
        curve = [Decimal("100"), Decimal("80")]
        result = compute_max_drawdown(curve)
        assert result == Decimal("0.2")

    def test_peak_updates(self) -> None:
        curve = [Decimal("100"), Decimal("120"), Decimal("100")]
        result = compute_max_drawdown(curve)
        expected = (Decimal("120") - Decimal("100")) / Decimal("120")
        assert result == expected


class TestBuildRiskSnapshot:
    def test_basic_snapshot(self) -> None:
        returns = [Decimal("-0.05"), Decimal("0.02")]
        curve = [Decimal("100"), Decimal("110")]
        snap = build_risk_snapshot(returns, curve)
        assert isinstance(snap, PortfolioRiskSnapshot)
        assert snap.var_95 > Decimal("0")
        assert snap.cvar_95 > Decimal("0")
        assert not snap.drawdown_breached

    def test_drawdown_breached(self) -> None:
        returns = [Decimal("-0.05"), Decimal("0.02")]
        curve = [Decimal("100"), Decimal("80")]
        snap = build_risk_snapshot(returns, curve, max_allowed_drawdown=Decimal("0.01"))
        assert snap.drawdown_breached is True

    def test_drawdown_not_breached(self) -> None:
        returns = [Decimal("-0.05"), Decimal("0.02")]
        curve = [Decimal("100"), Decimal("110")]
        snap = build_risk_snapshot(returns, curve, max_allowed_drawdown=Decimal("0.5"))
        assert snap.drawdown_breached is False

    def test_default_max_allowed_drawdown(self) -> None:
        returns = [Decimal("-0.05"), Decimal("0.02")]
        curve = [Decimal("100"), Decimal("110")]
        snap = build_risk_snapshot(returns, curve)
        assert isinstance(snap, PortfolioRiskSnapshot)


class TestValidateReturns:
    def test_valid_returns(self) -> None:
        _validate_returns([Decimal("0.01"), Decimal("0.02")], Decimal("0.95"))

    def test_empty_returns(self) -> None:
        with pytest.raises(ConfigError, match="at least two"):
            _validate_returns([], Decimal("0.95"))

    def test_single_return(self) -> None:
        with pytest.raises(ConfigError, match="at least two"):
            _validate_returns([Decimal("0.01")], Decimal("0.95"))

    def test_confidence_zero(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            _validate_returns([Decimal("0.01"), Decimal("0.02")], Decimal("0"))

    def test_confidence_one(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            _validate_returns([Decimal("0.01"), Decimal("0.02")], Decimal("1"))

    def test_confidence_negative(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            _validate_returns([Decimal("0.01"), Decimal("0.02")], Decimal("-0.5"))

    def test_valid_confidence_boundary(self) -> None:
        _validate_returns([Decimal("0.01"), Decimal("0.02")], Decimal("0.5"))
