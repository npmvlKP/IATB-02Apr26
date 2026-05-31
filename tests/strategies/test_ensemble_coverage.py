"""Coverage tests for strategies.ensemble."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.enums import Exchange, OrderSide
from iatb.core.events import SignalEvent
from iatb.strategies.ensemble import EnsembleStrategy, WeightedSignal


def _make_signal(
    symbol: str = "RELIANCE",
    side: OrderSide = OrderSide.BUY,
    confidence: Decimal = Decimal("0.8"),
) -> SignalEvent:
    return SignalEvent(
        strategy_id="test",
        exchange=Exchange.NSE,
        symbol=symbol,
        side=side,
        confidence=confidence,
    )


class TestWeightedSignal:
    def test_init(self) -> None:
        signal = _make_signal()
        ws = WeightedSignal(signal=signal, weight=Decimal("0.6"))
        assert ws.signal is signal
        assert ws.weight == Decimal("0.6")

    def test_frozen(self) -> None:
        signal = _make_signal()
        ws = WeightedSignal(signal=signal, weight=Decimal("0.6"))
        with pytest.raises(AttributeError):
            ws.weight = Decimal("0.9")  # type: ignore[misc]


class TestEnsembleStrategy:
    def test_init_default(self) -> None:
        es = EnsembleStrategy()
        assert es._vote_threshold == Decimal("0.55")

    def test_init_custom_threshold(self) -> None:
        es = EnsembleStrategy(vote_threshold=Decimal("0.7"))
        assert es._vote_threshold == Decimal("0.7")

    def test_on_signals_no_signals(self) -> None:
        es = EnsembleStrategy()
        mock_ctx = MagicMock()
        mock_ctx.exchange = Exchange.NSE
        with patch.object(es, "can_emit_signal", return_value=True):
            result = es.on_signals(context=mock_ctx, weighted_signals=[])
            assert result is None

    def test_on_signals_buy_consensus(self) -> None:
        es = EnsembleStrategy()
        mock_ctx = MagicMock()
        mock_ctx.exchange = Exchange.NSE
        signal = _make_signal(side=OrderSide.BUY, confidence=Decimal("0.9"))
        ws = WeightedSignal(signal=signal, weight=Decimal("0.7"))
        with (
            patch.object(es, "can_emit_signal", return_value=True),
            patch.object(es, "build_signal", return_value=signal),
        ):
            result = es.on_signals(context=mock_ctx, weighted_signals=[ws])
            assert result is not None

    def test_accumulate(self) -> None:
        signal1 = _make_signal(side=OrderSide.BUY, confidence=Decimal("0.9"))
        signal2 = _make_signal(side=OrderSide.BUY, confidence=Decimal("0.7"))
        ws1 = WeightedSignal(signal=signal1, weight=Decimal("0.6"))
        ws2 = WeightedSignal(signal=signal2, weight=Decimal("0.4"))
        buy, sell, total, wprice = EnsembleStrategy._accumulate([ws1, ws2])
        assert buy > Decimal("0")
        assert sell == Decimal("0")
        assert total == Decimal("1.0")

    def test_accumulate_sell_signals(self) -> None:
        signal1 = _make_signal(side=OrderSide.SELL, confidence=Decimal("0.8"))
        ws1 = WeightedSignal(signal=signal1, weight=Decimal("1.0"))
        buy, sell, total, wprice = EnsembleStrategy._accumulate([ws1])
        assert buy == Decimal("0")
        assert sell > Decimal("0")

    def test_winning_side_buy(self) -> None:
        side, score = EnsembleStrategy._winning_side(Decimal("0.8"), Decimal("0.2"))
        assert side == OrderSide.BUY
        assert score == Decimal("0.8")

    def test_winning_side_sell(self) -> None:
        side, score = EnsembleStrategy._winning_side(Decimal("0.2"), Decimal("0.8"))
        assert side == OrderSide.SELL
        assert score == Decimal("0.8")

    def test_winning_side_tie(self) -> None:
        side, score = EnsembleStrategy._winning_side(Decimal("0.5"), Decimal("0.5"))
        assert side is None
