"""Comprehensive coverage tests for iatb.risk.circuit_breaker."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from iatb.core.exceptions import ConfigError
from iatb.risk.circuit_breaker import (
    CircuitBreakerState,
    evaluate_and_engage_kill_switch,
    evaluate_circuit_breaker,
)

_NOW = datetime(2026, 5, 25, 10, 0, tzinfo=UTC)


class TestEvaluateCircuitBreaker:
    def test_level_3_at_20(self) -> None:
        state = evaluate_circuit_breaker(Decimal("20"))
        assert state.level == 3
        assert state.halt_required is True

    def test_level_2_at_15(self) -> None:
        state = evaluate_circuit_breaker(Decimal("15"))
        assert state.level == 2
        assert state.halt_required is True

    def test_level_1_at_10(self) -> None:
        state = evaluate_circuit_breaker(Decimal("10"))
        assert state.level == 1
        assert state.halt_required is True

    def test_no_halt_below_10(self) -> None:
        state = evaluate_circuit_breaker(Decimal("9.99"))
        assert state.level == 0
        assert state.halt_required is False

    def test_zero_move(self) -> None:
        state = evaluate_circuit_breaker(Decimal("0"))
        assert state.level == 0
        assert state.halt_required is False

    def test_between_10_and_15(self) -> None:
        state = evaluate_circuit_breaker(Decimal("12"))
        assert state.level == 1
        assert state.halt_required is True

    def test_between_15_and_20(self) -> None:
        state = evaluate_circuit_breaker(Decimal("17"))
        assert state.level == 2
        assert state.halt_required is True

    def test_above_20(self) -> None:
        state = evaluate_circuit_breaker(Decimal("25"))
        assert state.level == 3
        assert state.halt_required is True

    def test_negative_raises(self) -> None:
        with pytest.raises(ConfigError, match="non-negative"):
            evaluate_circuit_breaker(Decimal("-1"))

    def test_exact_10(self) -> None:
        state = evaluate_circuit_breaker(Decimal("10"))
        assert state.level == 1

    def test_exact_15(self) -> None:
        state = evaluate_circuit_breaker(Decimal("15"))
        assert state.level == 2

    def test_exact_20(self) -> None:
        state = evaluate_circuit_breaker(Decimal("20"))
        assert state.level == 3


class TestCircuitBreakerState:
    def test_frozen(self) -> None:
        state = CircuitBreakerState(
            level=1, halt_required=True, reason="Level-1 halt (10%)"
        )
        with pytest.raises(AttributeError):
            state.level = 2

    def test_fields(self) -> None:
        state = CircuitBreakerState(level=2, halt_required=True, reason="test")
        assert state.level == 2
        assert state.halt_required is True
        assert state.reason == "test"


class TestEvaluateAndEngageKillSwitch:
    def test_engages_on_halt(self) -> None:
        ks = MagicMock()
        ks.is_engaged = False
        state = evaluate_and_engage_kill_switch(Decimal("10"), ks, _NOW)
        ks.engage.assert_called_once()
        assert state.halt_required is True

    def test_does_not_engage_when_no_halt(self) -> None:
        ks = MagicMock()
        ks.is_engaged = False
        state = evaluate_and_engage_kill_switch(Decimal("5"), ks, _NOW)
        ks.engage.assert_not_called()
        assert state.halt_required is False

    def test_does_not_engage_already_engaged(self) -> None:
        ks = MagicMock()
        ks.is_engaged = True
        state = evaluate_and_engage_kill_switch(Decimal("10"), ks, _NOW)
        ks.engage.assert_not_called()
        assert state.halt_required is True

    def test_level3_triggers_engage(self) -> None:
        ks = MagicMock()
        ks.is_engaged = False
        state = evaluate_and_engage_kill_switch(Decimal("20"), ks, _NOW)
        ks.engage.assert_called_once()
        assert state.level == 3
