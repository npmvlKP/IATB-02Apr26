"""Coverage tests for iatb.backtesting.session_masks - session masking functions."""

from datetime import UTC, date, datetime, time
from unittest.mock import patch

import pytest
from iatb.backtesting.session_masks import (
    MIS_REQUIRED_ASSETS,
    _next_date,
    _validate_exchange,
    create_mis_session_mask,
    filter_timestamps_in_session,
    get_mis_session_window,
    is_in_session,
    is_mis_trading_allowed,
    validate_trade_product,
)
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError


class TestValidateExchange:
    def test_nse_passes(self) -> None:
        _validate_exchange(Exchange.NSE)

    def test_bse_passes(self) -> None:
        _validate_exchange(Exchange.BSE)

    def test_unsupported_binance_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unsupported session exchange"):
            _validate_exchange(Exchange.BINANCE)


class TestNextDate:
    def test_mid_month(self) -> None:
        result = _next_date(date(2026, 1, 15))
        assert result == date(2026, 1, 16)

    def test_month_boundary(self) -> None:
        result = _next_date(date(2026, 1, 31))
        assert result == date(2026, 2, 1)

    def test_year_boundary(self) -> None:
        result = _next_date(date(2026, 12, 31))
        assert result == date(2027, 1, 1)


class TestIsInSession:
    def test_unsupported_exchange_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unsupported session exchange"):
            is_in_session(datetime.now(UTC), Exchange.BINANCE)

    def test_calls_trading_sessions(self) -> None:
        with patch("iatb.backtesting.session_masks.TradingSessions") as mock_ts:
            mock_ts.is_market_open.return_value = True
            result = is_in_session(
                datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
                Exchange.NSE,
            )
            assert result is True


class TestFilterTimestampsInSession:
    def test_unsupported_exchange_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unsupported session exchange"):
            filter_timestamps_in_session([datetime.now(UTC)], Exchange.COINDCX)


class TestIsMisTradingAllowed:
    def test_unsupported_exchange_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unsupported session exchange"):
            is_mis_trading_allowed(datetime.now(UTC), Exchange.BINANCE, "STOCKS")

    def test_non_mis_asset_returns_false(self) -> None:
        with patch("iatb.backtesting.session_masks.TradingSessions"):
            result = is_mis_trading_allowed(
                datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
                Exchange.NSE,
                "BONDS",
            )
            assert result is False


class TestValidateTradeProduct:
    def test_unsupported_exchange_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unsupported session exchange"):
            validate_trade_product(datetime.now(UTC), Exchange.BINANCE, "STOCKS", "MIS")


class TestGetMisSessionWindow:
    def test_bse_returns_window(self) -> None:
        result = get_mis_session_window(Exchange.BSE, date(2026, 1, 5))
        assert result is not None
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_nse_returns_window(self) -> None:
        result = get_mis_session_window(Exchange.NSE, date(2026, 1, 5))
        assert result is not None

    def test_unsupported_exchange_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unsupported session exchange"):
            get_mis_session_window(Exchange.BINANCE, date(2026, 1, 5))


class TestCreateMisSessionMask:
    def test_bse_returns_dates(self) -> None:
        result = create_mis_session_mask(
            Exchange.BSE,
            date(2026, 1, 5),
            date(2026, 1, 9),
        )
        assert len(result) > 0
        assert all(isinstance(d, date) for d in result)

    def test_unsupported_exchange_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unsupported session exchange"):
            create_mis_session_mask(
                Exchange.BINANCE,
                date(2026, 1, 5),
                date(2026, 1, 9),
            )

    def test_returns_valid_dates(self) -> None:
        with patch(
            "iatb.backtesting.session_masks.get_mis_session_window",
        ) as mock_window:
            mock_window.return_value = (time(9, 15), time(15, 0))
            result = create_mis_session_mask(
                Exchange.NSE,
                date(2026, 1, 5),
                date(2026, 1, 7),
            )
            assert len(result) == 3


class TestMisRequiredAssets:
    def test_contains_stocks(self) -> None:
        assert "STOCKS" in MIS_REQUIRED_ASSETS

    def test_contains_options(self) -> None:
        assert "OPTIONS" in MIS_REQUIRED_ASSETS
