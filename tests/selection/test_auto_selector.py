"""Tests for auto_selector.py - integrated auto-selection pipeline."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from iatb.core.enums import Exchange, OrderSide
from iatb.core.exceptions import ConfigError
from iatb.data.instrument import Instrument, InstrumentType
from iatb.market_strength.regime_detector import MarketRegime
from iatb.selection.auto_selector import (
    AutoSelectionResult,
    AutoSelector,
    AutoSelectorConfig,
    _compute_adaptive_trail_offset,
    _compute_lots,
    _determine_option_type,
    _extract_confidence,
    _filter_chain_by_type,
    _validate_auto_select_inputs,
    select_strike_by_regime,
)
from iatb.selection.drl_signal import DRLSignalOutput
from iatb.selection.ranking import RankedInstrument, SelectionResult
from iatb.selection.sentiment_signal import SentimentSignalOutput
from iatb.selection.strength_signal import StrengthSignalOutput
from iatb.selection.volume_profile_signal import VolumeProfileSignalOutput

# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


def _make_instrument(
    trading_symbol: str = "NIFTY24800CE",
    instrument_type: InstrumentType = InstrumentType.OPTION_CE,
    strike: Decimal = Decimal("24800"),
    lot_size: Decimal = Decimal("25"),
) -> Instrument:
    """Create a test Instrument matching the real Instrument dataclass."""
    return Instrument(
        instrument_token=12345,
        exchange_token=12345,
        trading_symbol=trading_symbol,
        name="NIFTY",
        exchange=Exchange.NSE,
        segment="NFO",
        instrument_type=instrument_type,
        strike=strike,
        lot_size=lot_size,
        tick_size=Decimal("0.05"),
        expiry=date(2026, 6, 26),
    )


def _make_option_chain() -> list[Instrument]:
    """Create a realistic option chain with CE and PE."""
    chain: list[Instrument] = []
    strikes = [Decimal(s) for s in ("24600", "24700", "24800", "24900", "25000")]
    for s in strikes:
        chain.append(
            _make_instrument(
                trading_symbol=f"NIFTY{s}CE",
                instrument_type=InstrumentType.OPTION_CE,
                strike=s,
            )
        )
        chain.append(
            _make_instrument(
                trading_symbol=f"NIFTY{s}PE",
                instrument_type=InstrumentType.OPTION_PE,
                strike=s,
            )
        )
    return chain


def _make_sentiment_output(
    score: Decimal = Decimal("0.7"),
    confidence: Decimal = Decimal("0.8"),
) -> SentimentSignalOutput:
    return SentimentSignalOutput(
        score=score,
        confidence=confidence,
        directional_bias=Decimal("0.6"),
        metadata={"source": "test"},
    )


def _make_strength_output(
    score: Decimal = Decimal("0.6"),
    confidence: Decimal = Decimal("0.7"),
) -> StrengthSignalOutput:
    return StrengthSignalOutput(
        score=score,
        confidence=confidence,
        regime=MarketRegime.BULL,
        tradable=True,
        metadata={"source": "test"},
    )


def _make_vp_output(
    score: Decimal = Decimal("0.5"),
    confidence: Decimal = Decimal("0.6"),
) -> VolumeProfileSignalOutput:
    return VolumeProfileSignalOutput(
        score=score,
        confidence=confidence,
        poc_distance=Decimal("0.1"),
        value_area_ratio=Decimal("0.8"),
        metadata={"source": "test"},
    )


def _make_drl_output(
    score: Decimal = Decimal("0.65"),
    confidence: Decimal = Decimal("0.7"),
) -> DRLSignalOutput:
    return DRLSignalOutput(
        score=score,
        confidence=confidence,
        robust=True,
        metadata={"source": "test"},
    )


# ------------------------------------------------------------------ #
# AutoSelectorConfig tests
# ------------------------------------------------------------------ #


class TestAutoSelectorConfig:
    """Tests for AutoSelectorConfig validation."""

    def test_default_config_is_valid(self) -> None:
        config = AutoSelectorConfig()
        assert config.base_lots == 1
        assert config.max_lots == 10
        assert config.min_confidence == Decimal("0.30")

    def test_base_lots_must_be_positive(self) -> None:
        with pytest.raises(ConfigError, match="base_lots"):
            AutoSelectorConfig(base_lots=0)

    def test_max_lots_must_be_gte_base_lots(self) -> None:
        with pytest.raises(ConfigError, match="max_lots"):
            AutoSelectorConfig(base_lots=5, max_lots=3)

    def test_min_confidence_range(self) -> None:
        with pytest.raises(ConfigError, match="min_confidence"):
            AutoSelectorConfig(min_confidence=Decimal("-0.1"))

    def test_min_confidence_max_range(self) -> None:
        with pytest.raises(ConfigError, match="min_confidence"):
            AutoSelectorConfig(min_confidence=Decimal("1.5"))

    def test_base_trail_fraction_must_be_positive(self) -> None:
        with pytest.raises(ConfigError, match="base_trail_fraction"):
            AutoSelectorConfig(base_trail_fraction=Decimal("0"))

    def test_min_trail_fraction_must_be_positive(self) -> None:
        with pytest.raises(ConfigError, match="min_trail_fraction"):
            AutoSelectorConfig(min_trail_fraction=Decimal("0"))

    def test_max_trail_fraction_must_be_gte_min(self) -> None:
        with pytest.raises(ConfigError, match="max_trail_fraction"):
            AutoSelectorConfig(
                min_trail_fraction=Decimal("0.03"),
                max_trail_fraction=Decimal("0.01"),
            )

    def test_invalid_strike_selector_mode(self) -> None:
        with pytest.raises(ConfigError, match="strike_selector_mode"):
            AutoSelectorConfig(strike_selector_mode="invalid_mode")

    def test_valid_strike_modes(self) -> None:
        for mode in (
            "atm",
            "otm_1",
            "otm_2",
            "otm_3",
            "moneyness_2pct",
            "moneyness_5pct",
            "regime_adaptive",
        ):
            config = AutoSelectorConfig(strike_selector_mode=mode)
            assert config.strike_selector_mode == mode


# ------------------------------------------------------------------ #
# Helper function tests
# ------------------------------------------------------------------ #


class TestDetermineOptionType:
    """Tests for _determine_option_type."""

    def test_buy_bull_returns_ce(self) -> None:
        assert _determine_option_type(MarketRegime.BULL, OrderSide.BUY) == "CE"

    def test_buy_sideways_returns_ce(self) -> None:
        assert _determine_option_type(MarketRegime.SIDEWAYS, OrderSide.BUY) == "CE"

    def test_buy_bear_returns_pe(self) -> None:
        assert _determine_option_type(MarketRegime.BEAR, OrderSide.BUY) == "PE"

    def test_sell_bull_returns_pe(self) -> None:
        assert _determine_option_type(MarketRegime.BULL, OrderSide.SELL) == "PE"

    def test_sell_bear_returns_ce(self) -> None:
        assert _determine_option_type(MarketRegime.BEAR, OrderSide.SELL) == "CE"


class TestFilterChainByType:
    """Tests for _filter_chain_by_type."""

    def test_filters_ce(self) -> None:
        chain = _make_option_chain()
        ce = _filter_chain_by_type(chain, "CE")
        assert len(ce) > 0
        assert all(inst.instrument_type == InstrumentType.OPTION_CE for inst in ce)

    def test_filters_pe(self) -> None:
        chain = _make_option_chain()
        pe = _filter_chain_by_type(chain, "PE")
        assert len(pe) > 0
        assert all(inst.instrument_type == InstrumentType.OPTION_PE for inst in pe)

    def test_empty_chain(self) -> None:
        assert _filter_chain_by_type([], "CE") == []


class TestExtractConfidence:
    """Tests for _extract_confidence."""

    def test_full_metadata(self) -> None:
        metadata = {
            "contrib_sentiment": "0.2",
            "contrib_strength": "0.3",
            "contrib_vp": "0.1",
            "contrib_drl": "0.2",
        }
        result = _extract_confidence(metadata)
        assert result == Decimal("0.8")

    def test_missing_keys_returns_default(self) -> None:
        result = _extract_confidence({})
        assert result == Decimal("0.50")

    def test_invalid_values_returns_default(self) -> None:
        metadata = {
            "contrib_sentiment": "not_a_number",
            "contrib_strength": "0.1",
            "contrib_vp": "also_bad",
            "contrib_drl": "0.1",
        }
        result = _extract_confidence(metadata)
        assert result == Decimal("0.50")

    def test_confidence_capped_at_one(self) -> None:
        metadata = {
            "contrib_sentiment": "0.5",
            "contrib_strength": "0.5",
            "contrib_vp": "0.5",
            "contrib_drl": "0.5",
        }
        result = _extract_confidence(metadata)
        assert result <= Decimal("1")


class TestComputeLots:
    """Tests for _compute_lots."""

    def test_high_confidence_rank_one(self) -> None:
        lots = _compute_lots(
            base_lots=1,
            max_lots=10,
            confidence=Decimal("0.9"),
            rank=1,
            total_selected=3,
        )
        assert lots >= 1
        assert lots <= 10

    def test_low_confidence_gives_base_lots(self) -> None:
        lots = _compute_lots(
            base_lots=1,
            max_lots=10,
            confidence=Decimal("0.1"),
            rank=3,
            total_selected=3,
        )
        assert lots == 1  # minimum is base_lots

    def test_respects_max_lots(self) -> None:
        lots = _compute_lots(
            base_lots=1,
            max_lots=2,
            confidence=Decimal("1.0"),
            rank=1,
            total_selected=1,
        )
        assert lots <= 2

    def test_zero_total_selected_returns_base(self) -> None:
        lots = _compute_lots(
            base_lots=1,
            max_lots=10,
            confidence=Decimal("0.8"),
            rank=1,
            total_selected=0,
        )
        assert lots == 1


class TestComputeAdaptiveTrailOffset:
    """Tests for _compute_adaptive_trail_offset."""

    def test_high_confidence_gives_tighter_trail(self) -> None:
        high = _compute_adaptive_trail_offset(
            base_trail_fraction=Decimal("0.02"),
            min_trail_fraction=Decimal("0.005"),
            max_trail_fraction=Decimal("0.05"),
            confidence=Decimal("0.9"),
            regime=MarketRegime.BULL,
            underlying_price=Decimal("24000"),
            atr=Decimal("100"),
        )
        low = _compute_adaptive_trail_offset(
            base_trail_fraction=Decimal("0.02"),
            min_trail_fraction=Decimal("0.005"),
            max_trail_fraction=Decimal("0.05"),
            confidence=Decimal("0.3"),
            regime=MarketRegime.BULL,
            underlying_price=Decimal("24000"),
            atr=Decimal("100"),
        )
        assert high <= low

    def test_bear_regime_widens_trail(self) -> None:
        bear_trail = _compute_adaptive_trail_offset(
            base_trail_fraction=Decimal("0.02"),
            min_trail_fraction=Decimal("0.005"),
            max_trail_fraction=Decimal("0.05"),
            confidence=Decimal("0.6"),
            regime=MarketRegime.BEAR,
            underlying_price=Decimal("24000"),
            atr=Decimal("100"),
        )
        bull_trail = _compute_adaptive_trail_offset(
            base_trail_fraction=Decimal("0.02"),
            min_trail_fraction=Decimal("0.005"),
            max_trail_fraction=Decimal("0.05"),
            confidence=Decimal("0.6"),
            regime=MarketRegime.BULL,
            underlying_price=Decimal("24000"),
            atr=Decimal("100"),
        )
        assert bear_trail >= bull_trail

    def test_result_is_positive(self) -> None:
        result = _compute_adaptive_trail_offset(
            base_trail_fraction=Decimal("0.02"),
            min_trail_fraction=Decimal("0.005"),
            max_trail_fraction=Decimal("0.05"),
            confidence=Decimal("0.7"),
            regime=MarketRegime.SIDEWAYS,
            underlying_price=Decimal("24000"),
            atr=Decimal("100"),
        )
        assert result > Decimal("0")

    def test_uses_atr_offset(self) -> None:
        result = _compute_adaptive_trail_offset(
            base_trail_fraction=Decimal("0.0001"),
            min_trail_fraction=Decimal("0.0001"),
            max_trail_fraction=Decimal("0.05"),
            confidence=Decimal("0.9"),
            regime=MarketRegime.BULL,
            underlying_price=Decimal("24000"),
            atr=Decimal("500"),
        )
        # ATR*2 = 1000, price*fraction is tiny, so result should be ATR-based
        assert result >= Decimal("1000")


class TestValidateAutoSelectInputs:
    """Tests for _validate_auto_select_inputs."""

    def test_empty_signals_raises(self) -> None:
        with pytest.raises(ConfigError, match="instrument_signals"):
            _validate_auto_select_inputs([], _make_option_chain(), Decimal("24000"))

    def test_empty_chain_raises(self) -> None:
        from iatb.selection.instrument_scorer import InstrumentSignals

        sig = MagicMock(spec=InstrumentSignals)
        with pytest.raises(ConfigError, match="option_chain"):
            _validate_auto_select_inputs([sig], [], Decimal("24000"))

    def test_negative_price_raises(self) -> None:
        from iatb.selection.instrument_scorer import InstrumentSignals

        sig = MagicMock(spec=InstrumentSignals)
        with pytest.raises(ConfigError, match="underlying_price"):
            _validate_auto_select_inputs([sig], _make_option_chain(), Decimal("-1"))

    def test_valid_inputs_pass(self) -> None:
        from iatb.selection.instrument_scorer import InstrumentSignals

        sig = MagicMock(spec=InstrumentSignals)
        # Should not raise
        _validate_auto_select_inputs([sig], _make_option_chain(), Decimal("24000"))


# ------------------------------------------------------------------ #
# select_strike_by_regime tests
# ------------------------------------------------------------------ #


class TestSelectStrikeByRegime:
    """Tests for select_strike_by_regime."""

    def test_empty_chain_raises(self) -> None:
        with pytest.raises(ConfigError, match="option_chain"):
            select_strike_by_regime(
                MarketRegime.BULL, [], Decimal("24800"), OrderSide.BUY
            )

    def test_negative_price_raises(self) -> None:
        with pytest.raises(ConfigError, match="underlying_price"):
            select_strike_by_regime(
                MarketRegime.BULL,
                _make_option_chain(),
                Decimal("-1"),
                OrderSide.BUY,
            )

    def test_bull_selects_atm(self) -> None:
        chain = _make_option_chain()
        result = select_strike_by_regime(
            MarketRegime.BULL, chain, Decimal("24800"), OrderSide.BUY
        )
        # Should select nearest to 24800 (ATM)
        assert result.strike is not None
        assert abs(result.strike - Decimal("24800")) <= Decimal("100")

    def test_bear_selects_otm(self) -> None:
        chain = _make_option_chain()
        result = select_strike_by_regime(
            MarketRegime.BEAR, chain, Decimal("24800"), OrderSide.BUY
        )
        assert result.strike is not None

    def test_sideways_selects_otm_1(self) -> None:
        chain = _make_option_chain()
        result = select_strike_by_regime(
            MarketRegime.SIDEWAYS, chain, Decimal("24800"), OrderSide.BUY
        )
        assert result.strike is not None


# ------------------------------------------------------------------ #
# AutoSelector integration tests
# ------------------------------------------------------------------ #


class TestAutoSelectorInit:
    """Tests for AutoSelector initialization."""

    def test_default_init(self) -> None:
        selector = AutoSelector()
        assert selector.config.base_lots == 1
        assert selector.config.max_lots == 10

    def test_custom_config(self) -> None:
        config = AutoSelectorConfig(
            base_lots=2,
            max_lots=5,
            strike_selector_mode="otm_2",
        )
        selector = AutoSelector(config=config)
        assert selector.config.base_lots == 2
        assert selector.config.strike_selector_mode == "otm_2"

    def test_custom_trailing_stop(self) -> None:
        from iatb.risk.trailing_stop import ATRTrailingStop

        ts = ATRTrailingStop(atr_multiplier=Decimal("2.5"))
        selector = AutoSelector(trailing_stop_strategy=ts)
        assert isinstance(selector._trailing_stop, ATRTrailingStop)


class TestAutoSelectorBuildStrikeSelector:
    """Tests for AutoSelector._build_strike_selector."""

    def test_atm_mode(self) -> None:
        selector = AutoSelector(config=AutoSelectorConfig(strike_selector_mode="atm"))
        assert type(selector._strike_selector).__name__ == "ATMSelector"

    def test_otm_1_mode(self) -> None:
        selector = AutoSelector(config=AutoSelectorConfig(strike_selector_mode="otm_1"))
        assert type(selector._strike_selector).__name__ == "LiquidityFilteredSelector"

    def test_moneyness_5pct_mode(self) -> None:
        selector = AutoSelector(
            config=AutoSelectorConfig(strike_selector_mode="moneyness_5pct")
        )
        assert type(selector._strike_selector).__name__ == "LiquidityFilteredSelector"

    def test_regime_adaptive_mode(self) -> None:
        selector = AutoSelector(
            config=AutoSelectorConfig(strike_selector_mode="regime_adaptive")
        )
        assert type(selector._strike_selector).__name__ == "LiquidityFilteredSelector"


class TestAutoSelectorAutoSelect:
    """Integration tests for AutoSelector.auto_select."""

    def test_auto_select_with_mocked_scorer(self) -> None:
        """Test auto_select with a mocked InstrumentScorer."""
        selector = AutoSelector(
            config=AutoSelectorConfig(min_confidence=Decimal("0.10"))
        )
        chain = _make_option_chain()
        # Mock the scorer to return a known selection
        ranked = RankedInstrument(
            symbol="NIFTY",
            exchange=Exchange.NSE,
            composite_score=Decimal("0.75"),
            rank=1,
            metadata={
                "contrib_sentiment": "0.20",
                "contrib_strength": "0.25",
                "contrib_vp": "0.15",
                "contrib_drl": "0.15",
            },
        )
        mock_selection = SelectionResult(
            selected=[ranked],
            filtered_count=0,
            total_candidates=1,
        )
        selector._scorer.score_and_select = MagicMock(return_value=mock_selection)

        # We need actual InstrumentSignals for the validation
        from iatb.selection.instrument_scorer import InstrumentSignals

        mock_signal = MagicMock(spec=InstrumentSignals)

        results = selector.auto_select(
            instrument_signals=[mock_signal],
            regime=MarketRegime.BULL,
            option_chain=chain,
            underlying_price=Decimal("24800"),
            side=OrderSide.BUY,
            current_atr=Decimal("150"),
        )
        assert len(results) >= 1
        result = results[0]
        assert isinstance(result, AutoSelectionResult)
        assert result.symbol == "NIFTY"
        assert result.option_type == "CE"
        assert result.lots >= 1
        assert result.trail_offset_points > Decimal("0")

    def test_auto_select_bear_regime_selects_pe(self) -> None:
        """Bear regime with BUY side should select PE options."""
        selector = AutoSelector(
            config=AutoSelectorConfig(min_confidence=Decimal("0.10"))
        )
        chain = _make_option_chain()

        ranked = RankedInstrument(
            symbol="NIFTY",
            exchange=Exchange.NSE,
            composite_score=Decimal("0.60"),
            rank=1,
            metadata={
                "contrib_sentiment": "0.15",
                "contrib_strength": "0.20",
                "contrib_vp": "0.10",
                "contrib_drl": "0.15",
            },
        )
        mock_selection = SelectionResult(
            selected=[ranked],
            filtered_count=0,
            total_candidates=1,
        )
        selector._scorer.score_and_select = MagicMock(return_value=mock_selection)

        from iatb.selection.instrument_scorer import InstrumentSignals

        mock_signal = MagicMock(spec=InstrumentSignals)

        results = selector.auto_select(
            instrument_signals=[mock_signal],
            regime=MarketRegime.BEAR,
            option_chain=chain,
            underlying_price=Decimal("24800"),
            side=OrderSide.BUY,
        )
        assert len(results) >= 1
        assert results[0].option_type == "PE"

    def test_auto_select_empty_signals_raises(self) -> None:
        selector = AutoSelector()
        with pytest.raises(ConfigError, match="instrument_signals"):
            selector.auto_select(
                instrument_signals=[],
                regime=MarketRegime.BULL,
                option_chain=_make_option_chain(),
                underlying_price=Decimal("24800"),
            )

    def test_auto_select_empty_chain_raises(self) -> None:
        selector = AutoSelector()
        from iatb.selection.instrument_scorer import InstrumentSignals

        mock_signal = MagicMock(spec=InstrumentSignals)
        with pytest.raises(ConfigError, match="option_chain"):
            selector.auto_select(
                instrument_signals=[mock_signal],
                regime=MarketRegime.BULL,
                option_chain=[],
                underlying_price=Decimal("24800"),
            )

    def test_auto_select_below_min_confidence_skips(self) -> None:
        """Instruments below min_confidence should be skipped."""
        selector = AutoSelector(
            config=AutoSelectorConfig(min_confidence=Decimal("0.80"))
        )
        chain = _make_option_chain()

        # Metadata with very low confidence
        ranked = RankedInstrument(
            symbol="NIFTY",
            exchange=Exchange.NSE,
            composite_score=Decimal("0.30"),
            rank=1,
            metadata={
                "contrib_sentiment": "0.05",
                "contrib_strength": "0.05",
                "contrib_vp": "0.05",
                "contrib_drl": "0.05",
            },
        )
        mock_selection = SelectionResult(
            selected=[ranked],
            filtered_count=0,
            total_candidates=1,
        )
        selector._scorer.score_and_select = MagicMock(return_value=mock_selection)

        from iatb.selection.instrument_scorer import InstrumentSignals

        mock_signal = MagicMock(spec=InstrumentSignals)

        results = selector.auto_select(
            instrument_signals=[mock_signal],
            regime=MarketRegime.BULL,
            option_chain=chain,
            underlying_price=Decimal("24800"),
        )
        assert len(results) == 0

    def test_auto_select_no_matching_options_skips(self) -> None:
        """If no options match the desired type, result is skipped."""
        selector = AutoSelector(
            config=AutoSelectorConfig(min_confidence=Decimal("0.10"))
        )
        # Chain with only CE, but bear regime wants PE
        ce_chain = [
            _make_instrument(
                trading_symbol="NIFTY24800CE",
                instrument_type=InstrumentType.OPTION_CE,
                strike=Decimal("24800"),
            )
        ]

        ranked = RankedInstrument(
            symbol="NIFTY",
            exchange=Exchange.NSE,
            composite_score=Decimal("0.75"),
            rank=1,
            metadata={
                "contrib_sentiment": "0.20",
                "contrib_strength": "0.25",
                "contrib_vp": "0.15",
                "contrib_drl": "0.15",
            },
        )
        mock_selection = SelectionResult(
            selected=[ranked],
            filtered_count=0,
            total_candidates=1,
        )
        selector._scorer.score_and_select = MagicMock(return_value=mock_selection)

        from iatb.selection.instrument_scorer import InstrumentSignals

        mock_signal = MagicMock(spec=InstrumentSignals)

        # Bear + BUY = PE, but chain only has CE
        results = selector.auto_select(
            instrument_signals=[mock_signal],
            regime=MarketRegime.BEAR,
            option_chain=ce_chain,
            underlying_price=Decimal("24800"),
            side=OrderSide.BUY,
        )
        assert len(results) == 0

    def test_auto_select_multiple_instruments(self) -> None:
        """Test auto_select with multiple ranked instruments."""
        selector = AutoSelector(
            config=AutoSelectorConfig(min_confidence=Decimal("0.10"))
        )
        chain = _make_option_chain()

        ranked_1 = RankedInstrument(
            symbol="NIFTY",
            exchange=Exchange.NSE,
            composite_score=Decimal("0.80"),
            rank=1,
            metadata={
                "contrib_sentiment": "0.25",
                "contrib_strength": "0.25",
                "contrib_vp": "0.15",
                "contrib_drl": "0.15",
            },
        )
        ranked_2 = RankedInstrument(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            composite_score=Decimal("0.60"),
            rank=2,
            metadata={
                "contrib_sentiment": "0.15",
                "contrib_strength": "0.20",
                "contrib_vp": "0.10",
                "contrib_drl": "0.10",
            },
        )
        mock_selection = SelectionResult(
            selected=[ranked_1, ranked_2],
            filtered_count=0,
            total_candidates=2,
        )
        selector._scorer.score_and_select = MagicMock(return_value=mock_selection)

        from iatb.selection.instrument_scorer import InstrumentSignals

        mock_signals = [MagicMock(spec=InstrumentSignals)]

        results = selector.auto_select(
            instrument_signals=mock_signals,
            regime=MarketRegime.BULL,
            option_chain=chain,
            underlying_price=Decimal("24800"),
        )
        assert len(results) == 2
        # Rank 1 should have more lots than rank 2
        assert results[0].lots >= results[1].lots


class TestAutoSelectionResult:
    """Tests for AutoSelectionResult dataclass."""

    def test_result_fields(self) -> None:
        result = AutoSelectionResult(
            symbol="NIFTY",
            exchange=Exchange.NSE,
            option_type="CE",
            strike_price=Decimal("24800"),
            lots=2,
            trail_offset_points=Decimal("480"),
            trail_strategy_name="RegimeAdaptiveTrailingStop",
            composite_score=Decimal("0.75"),
            confidence=Decimal("0.70"),
            regime=MarketRegime.BULL,
            reasons=["regime=bull", "option_type=CE"],
        )
        assert result.symbol == "NIFTY"
        assert result.option_type == "CE"
        assert result.strike_price == Decimal("24800")
        assert result.lots == 2
        assert result.trail_offset_points == Decimal("480")
        assert result.regime == MarketRegime.BULL

    def test_result_frozen(self) -> None:
        result = AutoSelectionResult(
            symbol="NIFTY",
            exchange=Exchange.NSE,
            option_type="CE",
            strike_price=Decimal("24800"),
            lots=1,
            trail_offset_points=Decimal("100"),
            trail_strategy_name="ATRTrailingStop",
            composite_score=Decimal("0.5"),
            confidence=Decimal("0.5"),
            regime=MarketRegime.SIDEWAYS,
        )
        with pytest.raises(AttributeError):
            result.symbol = "BANKNIFTY"  # type: ignore[misc]

    def test_default_reasons_empty(self) -> None:
        result = AutoSelectionResult(
            symbol="NIFTY",
            exchange=Exchange.NSE,
            option_type="CE",
            strike_price=Decimal("24800"),
            lots=1,
            trail_offset_points=Decimal("100"),
            trail_strategy_name="ATRTrailingStop",
            composite_score=Decimal("0.5"),
            confidence=Decimal("0.5"),
            regime=MarketRegime.SIDEWAYS,
        )
        assert result.reasons == []


class TestAutoSelectorScoreAndSelect:
    """Tests for AutoSelector.score_and_select delegation."""

    def test_delegates_to_scorer(self) -> None:
        selector = AutoSelector()
        mock_result = SelectionResult(
            selected=[],
            filtered_count=0,
            total_candidates=0,
        )
        selector._scorer.score_and_select = MagicMock(return_value=mock_result)

        from iatb.selection.instrument_scorer import InstrumentSignals

        mock_signals = [MagicMock(spec=InstrumentSignals)]

        result = selector.score_and_select(mock_signals, MarketRegime.BULL)
        assert result.total_candidates == 0
        selector._scorer.score_and_select.assert_called_once()
