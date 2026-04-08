"""
Tests for core event definitions.
"""

import random
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.events import (
    MarketTickEvent,
    OrderUpdateEvent,
    RegimeChangeEvent,
    SignalEvent,
)
from iatb.core.exceptions import ValidationError
from iatb.core.types import create_price, create_quantity

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class TestMarketTickEvent:
    """Test MarketTickEvent."""

    def test_default_values(self) -> None:
        """Test event with default values."""
        event = MarketTickEvent()
        assert isinstance(event.event_id, UUID)
        assert event.timestamp.tzinfo == UTC
        assert event.exchange == Exchange.NSE
        assert event.symbol == "UNKNOWN"
        assert event.price == create_price("0.0")
        assert event.quantity == create_quantity("0.0")

    def test_custom_values(self) -> None:
        """Test event with custom values."""
        event = MarketTickEvent(
            exchange=Exchange.BSE,
            symbol="RELIANCE",
            price=create_price("2500.50"),
            quantity=create_quantity("100"),
        )
        assert event.exchange == Exchange.BSE
        assert event.symbol == "RELIANCE"
        assert event.price == create_price("2500.50")
        assert event.quantity == create_quantity("100")

    def test_event_is_frozen(self) -> None:
        """Test that event is immutable."""
        event = MarketTickEvent()
        with pytest.raises(FrozenInstanceError):  # noqa: B017
            event.symbol = "NEW_SYMBOL"  # type: ignore[misc]

    def test_non_utc_timestamp_rejected(self) -> None:
        """Test fail-closed rejection of non-UTC timestamp."""
        ist = timezone(timedelta(hours=5, minutes=30))
        with pytest.raises(ValidationError, match="Invalid event timestamp"):
            MarketTickEvent(
                timestamp=datetime(2026, 1, 1, 9, 15, tzinfo=ist),
                symbol="RELIANCE",
            )

    def test_naive_timestamp_rejected(self) -> None:
        """Test fail-closed rejection of naive timestamp."""
        with pytest.raises(ValidationError, match="Invalid event timestamp"):
            MarketTickEvent(
                timestamp=datetime(2026, 1, 1, 9, 15, 0),  # noqa: DTZ001
                symbol="RELIANCE",
            )

    def test_bid_ask_domain_validation(self) -> None:
        """Test bid/ask domain validation."""
        with pytest.raises(ValidationError, match="bid_price cannot be greater than ask_price"):
            MarketTickEvent(
                symbol="RELIANCE",
                bid_price=create_price("101.00"),
                ask_price=create_price("100.00"),
            )


class TestOrderUpdateEvent:
    """Test OrderUpdateEvent."""

    def test_default_values(self) -> None:
        """Test event with default values."""
        event = OrderUpdateEvent()
        assert isinstance(event.event_id, UUID)
        assert event.timestamp.tzinfo == UTC
        assert event.order_id == "UNKNOWN_ORDER"
        assert event.exchange == Exchange.NSE
        assert event.side == OrderSide.BUY
        assert event.status == OrderStatus.PENDING

    def test_custom_values(self) -> None:
        """Test event with custom values."""
        event = OrderUpdateEvent(
            order_id="ORD123",
            exchange=Exchange.MCX,
            symbol="GOLD",
            side=OrderSide.SELL,
            quantity=create_quantity("50"),
            filled_quantity=create_quantity("50"),
            status=OrderStatus.FILLED,
        )
        assert event.order_id == "ORD123"
        assert event.exchange == Exchange.MCX
        assert event.symbol == "GOLD"
        assert event.side == OrderSide.SELL
        assert event.status == OrderStatus.FILLED

    def test_event_is_frozen(self) -> None:
        """Test that event is immutable."""
        event = OrderUpdateEvent()
        with pytest.raises(FrozenInstanceError):  # noqa: B017
            event.status = OrderStatus.FILLED  # type: ignore[misc]

    def test_filled_quantity_cannot_exceed_quantity(self) -> None:
        """Test fail-closed quantity consistency."""
        with pytest.raises(ValidationError, match="filled_quantity cannot exceed quantity"):
            OrderUpdateEvent(
                order_id="ORD-001",
                symbol="RELIANCE",
                quantity=create_quantity("10"),
                filled_quantity=create_quantity("12"),
            )


class TestSignalEvent:
    """Test SignalEvent."""

    def test_default_values(self) -> None:
        """Test event with default values."""
        event = SignalEvent()
        assert isinstance(event.event_id, UUID)
        assert event.timestamp.tzinfo == UTC
        assert event.strategy_id == "UNKNOWN_STRATEGY"
        assert event.exchange == Exchange.NSE
        assert event.side == OrderSide.BUY
        assert event.confidence == Decimal("0.0")

    def test_custom_values(self) -> None:
        """Test event with custom values."""
        event = SignalEvent(
            strategy_id="STRAT001",
            exchange=Exchange.CDS,
            symbol="USDINR",
            side=OrderSide.BUY,
            quantity=create_quantity("1000"),
            confidence=Decimal("0.85"),
        )
        assert event.strategy_id == "STRAT001"
        assert event.exchange == Exchange.CDS
        assert event.symbol == "USDINR"
        assert event.confidence == Decimal("0.85")

    def test_event_is_frozen(self) -> None:
        """Test that event is immutable."""
        event = SignalEvent()
        with pytest.raises(FrozenInstanceError):  # noqa: B017
            event.confidence = Decimal("0.5")  # type: ignore[misc]

    def test_confidence_bounds_validation(self) -> None:
        """Test fail-closed confidence domain bounds."""
        with pytest.raises(ValidationError, match="confidence="):
            SignalEvent(
                strategy_id="STRAT001",
                symbol="USDINR",
                confidence=Decimal("1.10"),
            )


class TestRegimeChangeEvent:
    """Test RegimeChangeEvent."""

    def test_default_values(self) -> None:
        """Test event with default values."""
        event = RegimeChangeEvent()
        assert isinstance(event.event_id, UUID)
        assert event.timestamp.tzinfo == UTC
        assert event.regime_type == "UNSPECIFIED"
        assert event.description == "UNSPECIFIED"
        assert event.confidence == Decimal("0.0")
        assert event.metadata == {}

    def test_custom_values(self) -> None:
        """Test event with custom values."""
        event = RegimeChangeEvent(
            regime_type="BULLISH",
            description="Market trending upward",
            confidence=Decimal("0.90"),
            metadata={"indicator": "RSI", "value": "70"},
        )
        assert event.regime_type == "BULLISH"
        assert event.description == "Market trending upward"
        assert event.confidence == Decimal("0.90")
        assert event.metadata == {"indicator": "RSI", "value": "70"}

    def test_event_is_frozen(self) -> None:
        """Test that event is immutable."""
        event = RegimeChangeEvent()
        with pytest.raises(FrozenInstanceError):  # noqa: B017
            event.regime_type = "BEARISH"  # type: ignore[misc]

    def test_regime_description_cannot_be_empty(self) -> None:
        """Test fail-closed regime domain validation."""
        with pytest.raises(ValidationError, match="description cannot be empty"):
            RegimeChangeEvent(regime_type="VOLATILITY", description="   ")
