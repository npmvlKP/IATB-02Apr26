"""Tests for instrument auto-selection module."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.enums import Exchange, OrderSide
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs
from iatb.market_strength.volume_profile import VolumeProfile
from iatb.selection._util import DirectionalIntent, confidence_ramp, rank_percentile
from iatb.selection.composite_score import (
    RegimeWeights,
    SignalScores,
    _weights_for_regime,
    compute_composite_score,
)
from iatb.selection.decay import temporal_decay
from iatb.selection.drl_signal import BacktestConclusion, compute_drl_signal
from iatb.selection.instrument_scorer import (
    InstrumentScorer,
    InstrumentSignals,
)
from iatb.selection.ranking import (
    RankedInstrument,
    RankingConfig,
    SelectionResult,
    rank_and_select,
)
from iatb.selection.sentiment_signal import SentimentSignalOutput
from iatb.selection.strength_signal import StrengthSignalOutput
from iatb.selection.volume_profile_signal import (
    ProfileShape,
    VolumeProfileSignalInput,
    VolumeProfileSignalOutput,
    classify_profile_shape,
    compute_volume_profile_signal,
)

_NOW = datetime(2026, 4, 5, 10, 0, 0, tzinfo=UTC)
_RECENT = _NOW - timedelta(minutes=30)
_OLD = _NOW - timedelta(hours=12)


# ── decay.py ──


class TestTemporalDecay:
    def test_zero_elapsed_returns_one(self) -> None:
        result = temporal_decay(_NOW, _NOW, "sentiment")
        assert result == Decimal("1")

    def test_positive_elapsed_reduces_score(self) -> None:
        result = temporal_decay(_RECENT, _NOW, "sentiment")
        assert Decimal("0") < result < Decimal("1")

    def test_large_elapsed_approaches_zero(self) -> None:
        old = _NOW - timedelta(hours=100)
        result = temporal_decay(old, _NOW, "sentiment")
        assert result < Decimal("0.01")

    def test_sentiment_decays_faster_than_drl(self) -> None:
        sentiment = temporal_decay(_OLD, _NOW, "sentiment")
        drl = temporal_decay(_OLD, _NOW, "drl")
        assert sentiment < drl

    def test_unknown_signal_name_raises(self) -> None:
        with pytest.raises(ConfigError, match="unknown signal_name"):
            temporal_decay(_NOW, _NOW, "unknown")

    def test_future_timestamp_raises(self) -> None:
        future = _NOW + timedelta(hours=1)
        with pytest.raises(ConfigError, match="cannot be in the future"):
            temporal_decay(future, _NOW, "sentiment")

    def test_non_utc_raises(self) -> None:
        naive = datetime(2026, 1, 1, 0, 0, 0, tzinfo=None)  # noqa: DTZ001
        with pytest.raises(ConfigError, match="must be UTC"):
            temporal_decay(naive, _NOW, "sentiment")

    def test_current_timestamp_non_utc_raises(self) -> None:
        naive_current = datetime(2026, 1, 1, 0, 0, 0, tzinfo=None)  # noqa: DTZ001
        with pytest.raises(ConfigError, match="current_timestamp must be UTC"):
            temporal_decay(_NOW, naive_current, "sentiment")


# ── volume_profile_signal.py ──


def _sample_profile(poc: str, vah: str, val: str) -> VolumeProfile:
    return VolumeProfile(
        poc=Decimal(poc),
        vah=Decimal(vah),
        val=Decimal(val),
        total_volume=Decimal("100000"),
    )


class TestProfileShape:
    def test_p_shape_when_poc_near_vah(self) -> None:
        profile = _sample_profile("195", "200", "180")
        assert classify_profile_shape(profile) == ProfileShape.P_BULLISH

    def test_b_shape_when_poc_near_val(self) -> None:
        profile = _sample_profile("183", "200", "180")
        assert classify_profile_shape(profile) == ProfileShape.B_BEARISH

    def test_d_shape_when_poc_centered(self) -> None:
        profile = _sample_profile("190", "200", "180")
        assert classify_profile_shape(profile) == ProfileShape.D_BALANCED

    def test_zero_range_returns_balanced(self) -> None:
        profile = _sample_profile("100", "100", "100")
        assert classify_profile_shape(profile) == ProfileShape.D_BALANCED


class TestVolumeProfileSignal:
    def test_price_at_poc_gives_high_score(self) -> None:
        profile = _sample_profile("100", "110", "90")
        inputs = VolumeProfileSignalInput(
            profile=profile,
            current_price=Decimal("100"),
            instrument_symbol="NIFTY",
            timestamp_utc=_NOW,
        )
        result = compute_volume_profile_signal(inputs, _NOW)
        assert result.score > Decimal("0.5")

    def test_price_far_from_poc_gives_lower_score(self) -> None:
        profile = _sample_profile("100", "110", "90")
        close = VolumeProfileSignalInput(
            profile=profile,
            current_price=Decimal("100"),
            instrument_symbol="NIFTY",
            timestamp_utc=_NOW,
        )
        far = VolumeProfileSignalInput(
            profile=profile,
            current_price=Decimal("130"),
            instrument_symbol="NIFTY",
            timestamp_utc=_NOW,
        )
        close_result = compute_volume_profile_signal(close, _NOW)
        far_result = compute_volume_profile_signal(far, _NOW)
        assert close_result.score > far_result.score

    def test_negative_price_raises(self) -> None:
        profile = _sample_profile("100", "110", "90")
        inputs = VolumeProfileSignalInput(
            profile=profile,
            current_price=Decimal("-1"),
            instrument_symbol="NIFTY",
            timestamp_utc=_NOW,
        )
        with pytest.raises(ConfigError, match="current_price must be positive"):
            compute_volume_profile_signal(inputs, _NOW)

    def test_short_intent_inverts_shape_scores(self) -> None:
        profile = _sample_profile("183", "200", "180")
        inputs = VolumeProfileSignalInput(
            profile=profile,
            current_price=Decimal("185"),
            instrument_symbol="NIFTY",
            timestamp_utc=_NOW,
        )
        long_result = compute_volume_profile_signal(inputs, _NOW, DirectionalIntent.LONG)
        short_result = compute_volume_profile_signal(inputs, _NOW, DirectionalIntent.SHORT)
        assert short_result.score > long_result.score

    def test_poc_proximity_zero_va_range_at_poc(self) -> None:
        """Test _poc_proximity when va_range is 0 and price equals POC."""
        from iatb.selection.volume_profile_signal import _poc_proximity

        profile = VolumeProfile(
            poc=Decimal("100"),
            vah=Decimal("100"),
            val=Decimal("100"),
            total_volume=Decimal("100000"),
        )
        result = _poc_proximity(Decimal("100"), profile)
        assert result == Decimal("1")

    def test_poc_proximity_zero_va_range_not_at_poc(self) -> None:
        """Test _poc_proximity when va_range is 0 and price != POC."""
        from iatb.selection.volume_profile_signal import _poc_proximity

        profile = VolumeProfile(
            poc=Decimal("100"),
            vah=Decimal("100"),
            val=Decimal("100"),
            total_volume=Decimal("100000"),
        )
        result = _poc_proximity(Decimal("105"), profile)
        assert result == Decimal("0")

    def test_va_width_ratio_zero_price_returns_zero(self) -> None:
        """Test _va_width_ratio when price is 0."""
        from iatb.selection.volume_profile_signal import _va_width_ratio

        profile = _sample_profile("100", "110", "90")
        result = _va_width_ratio(Decimal("0"), profile)
        assert result == Decimal("0")

    def test_poc_distance_pct_zero_price_returns_zero(self) -> None:
        """Test _poc_distance_pct when price is 0."""
        from iatb.selection.volume_profile_signal import _poc_distance_pct

        profile = _sample_profile("100", "110", "90")
        result = _poc_distance_pct(Decimal("0"), profile)
        assert result == Decimal("0")

    def test_va_width_pct_zero_price_returns_zero(self) -> None:
        """Test _va_width_pct when price is 0."""
        from iatb.selection.volume_profile_signal import _va_width_pct

        profile = _sample_profile("100", "110", "90")
        result = _va_width_pct(Decimal("0"), profile)
        assert result == Decimal("0")

    def test_validate_input_non_utc_timestamp_raises(self) -> None:
        """Test _validate_input raises for non-UTC timestamp (lines 158-159)."""
        from datetime import timezone

        from iatb.selection.volume_profile_signal import VolumeProfileSignalInput, _validate_input

        profile = _sample_profile("100", "110", "90")
        # Non-UTC timestamp
        inputs = VolumeProfileSignalInput(
            profile=profile,
            current_price=Decimal("100"),
            instrument_symbol="NIFTY",
            timestamp_utc=datetime(2026, 4, 7, 10, 0, 0, tzinfo=timezone(timedelta(hours=1))),
        )
        current = datetime(2026, 4, 7, 10, 30, 0, tzinfo=UTC)

        with pytest.raises(ConfigError, match="timestamp_utc must be UTC"):
            _validate_input(inputs, current)

    def test_validate_input_non_utc_current_raises(self) -> None:
        """Test _validate_input raises for non-UTC current (lines 161-162)."""
        from datetime import timezone

        from iatb.selection.volume_profile_signal import VolumeProfileSignalInput, _validate_input

        profile = _sample_profile("100", "110", "90")
        inputs = VolumeProfileSignalInput(
            profile=profile,
            current_price=Decimal("100"),
            instrument_symbol="NIFTY",
            timestamp_utc=datetime(2026, 4, 7, 10, 0, 0, tzinfo=UTC),
        )
        # Non-UTC current time
        current = datetime(2026, 4, 7, 10, 30, 0, tzinfo=timezone(timedelta(hours=1)))

        with pytest.raises(ConfigError, match="current_utc must be UTC"):
            _validate_input(inputs, current)

    def test_validate_input_empty_symbol_raises(self) -> None:
        """Test _validate_input raises for empty instrument_symbol (lines 164-165)."""
        from iatb.selection.volume_profile_signal import VolumeProfileSignalInput, _validate_input

        profile = _sample_profile("100", "110", "90")
        inputs = VolumeProfileSignalInput(
            profile=profile,
            current_price=Decimal("100"),
            instrument_symbol="  ",  # Whitespace only
            timestamp_utc=datetime(2026, 4, 7, 10, 0, 0, tzinfo=UTC),
        )
        current = datetime(2026, 4, 7, 10, 30, 0, tzinfo=UTC)

        with pytest.raises(ConfigError, match="instrument_symbol cannot be empty"):
            _validate_input(inputs, current)


# ── drl_signal.py ──


def _sample_conclusion(**kwargs: object) -> BacktestConclusion:
    defaults: dict[str, object] = {
        "instrument_symbol": "BANKNIFTY",
        "out_of_sample_sharpe": Decimal("1.5"),
        "max_drawdown_pct": Decimal("5"),
        "win_rate": Decimal("0.55"),
        "total_trades": 80,
        "monte_carlo_robust": True,
        "walk_forward_overfit_detected": False,
        "mean_overfit_ratio": Decimal("1.5"),
        "timestamp_utc": _NOW,
    }
    defaults.update(kwargs)
    return BacktestConclusion(**defaults)  # type: ignore[arg-type]


class TestDRLSignal:
    def test_robust_conclusion_yields_high_score(self) -> None:
        result = compute_drl_signal(_sample_conclusion(), _NOW)
        assert result.score > Decimal("0.3")
        assert result.robust is True

    def test_overfit_penalty_reduces_score(self) -> None:
        robust = compute_drl_signal(_sample_conclusion(), _NOW)
        overfit = compute_drl_signal(
            _sample_conclusion(
                walk_forward_overfit_detected=True,
                mean_overfit_ratio=Decimal("4.0"),
            ),
            _NOW,
        )
        assert robust.score > overfit.score
        assert overfit.robust is False

    def test_non_robust_monte_carlo_reduces_score(self) -> None:
        robust = compute_drl_signal(_sample_conclusion(), _NOW)
        fragile = compute_drl_signal(_sample_conclusion(monte_carlo_robust=False), _NOW)
        assert robust.score > fragile.score

    def test_negative_sharpe_yields_low_score(self) -> None:
        result = compute_drl_signal(_sample_conclusion(out_of_sample_sharpe=Decimal("-2")), _NOW)
        assert result.score < Decimal("0.3")

    def test_invalid_win_rate_raises(self) -> None:
        with pytest.raises(ConfigError, match="win_rate must be in"):
            compute_drl_signal(_sample_conclusion(win_rate=Decimal("1.5")), _NOW)

    def test_negative_trades_raises(self) -> None:
        with pytest.raises(ConfigError, match="total_trades cannot be negative"):
            compute_drl_signal(_sample_conclusion(total_trades=-1), _NOW)

    def test_high_drawdown_penalizes_score(self) -> None:
        low_dd = compute_drl_signal(
            _sample_conclusion(max_drawdown_pct=Decimal("3")),
            _NOW,
        )
        high_dd = compute_drl_signal(
            _sample_conclusion(max_drawdown_pct=Decimal("18")),
            _NOW,
        )
        assert low_dd.score > high_dd.score

    def test_extreme_drawdown_zeroes_drl(self) -> None:
        result = compute_drl_signal(
            _sample_conclusion(max_drawdown_pct=Decimal("25")),
            _NOW,
        )
        assert result.score == Decimal("0")

    def test_zero_trades_yields_zero_confidence(self) -> None:
        result = compute_drl_signal(
            _sample_conclusion(total_trades=0),
            _NOW,
        )
        assert result.confidence == Decimal("0")

    def test_graduated_overfit_mild_vs_severe(self) -> None:
        mild = compute_drl_signal(
            _sample_conclusion(
                walk_forward_overfit_detected=True,
                mean_overfit_ratio=Decimal("2.5"),
            ),
            _NOW,
        )
        severe = compute_drl_signal(
            _sample_conclusion(
                walk_forward_overfit_detected=True,
                mean_overfit_ratio=Decimal("7.0"),
            ),
            _NOW,
        )
        assert mild.score > severe.score


# ── rank_percentile ──


class TestRankPercentile:
    def test_clamp_01_below_zero(self) -> None:
        """Test clamp_01 with value below 0."""
        from iatb.selection._util import clamp_01

        result = clamp_01(Decimal("-0.5"))
        assert result == Decimal("0")

    def test_clamp_01_above_one(self) -> None:
        """Test clamp_01 with value above 1."""
        from iatb.selection._util import clamp_01

        result = clamp_01(Decimal("1.5"))
        assert result == Decimal("1")

    def test_clamp_01_within_range(self) -> None:
        """Test clamp_01 with value within [0, 1]."""
        from iatb.selection._util import clamp_01

        result = clamp_01(Decimal("0.5"))
        assert result == Decimal("0.5")

    def test_clamp_01_at_boundaries(self) -> None:
        """Test clamp_01 at 0 and 1."""
        from iatb.selection._util import clamp_01

        assert clamp_01(Decimal("0")) == Decimal("0")
        assert clamp_01(Decimal("1")) == Decimal("1")

    def test_ascending_values_zero_indexed(self) -> None:
        result = rank_percentile(
            [Decimal("0.1"), Decimal("0.5"), Decimal("0.9")],
        )
        assert result[0] == Decimal("0")
        assert result[0] < result[1] < result[2]
        assert result[2] == Decimal("1")

    def test_ties_share_rank(self) -> None:
        result = rank_percentile(
            [Decimal("0.5"), Decimal("0.5"), Decimal("0.9")],
        )
        assert result[0] == result[1]
        assert result[0] == Decimal("0")

    def test_single_element(self) -> None:
        result = rank_percentile([Decimal("0.7")])
        assert result == [Decimal("1")]

    def test_empty_list(self) -> None:
        assert rank_percentile([]) == []


# ── volume profile regime-dependent POC ──


class TestRegimePOC:
    def test_bull_regime_rewards_far_from_poc(self) -> None:
        profile = _sample_profile("100", "110", "90")
        inputs = VolumeProfileSignalInput(
            profile=profile,
            current_price=Decimal("125"),
            instrument_symbol="NIFTY",
            timestamp_utc=_NOW,
        )
        bull = compute_volume_profile_signal(
            inputs,
            _NOW,
            regime=MarketRegime.BULL,
        )
        side = compute_volume_profile_signal(
            inputs,
            _NOW,
            regime=MarketRegime.SIDEWAYS,
        )
        assert bull.score > side.score

    def test_sideways_regime_rewards_near_poc(self) -> None:
        profile = _sample_profile("100", "110", "90")
        inputs = VolumeProfileSignalInput(
            profile=profile,
            current_price=Decimal("100"),
            instrument_symbol="NIFTY",
            timestamp_utc=_NOW,
        )
        side = compute_volume_profile_signal(
            inputs,
            _NOW,
            regime=MarketRegime.SIDEWAYS,
        )
        bull = compute_volume_profile_signal(
            inputs,
            _NOW,
            regime=MarketRegime.BULL,
        )
        assert side.score > bull.score


# ── composite_score.py ──


def _sample_signals(**kwargs: Decimal) -> SignalScores:
    defaults = {
        "sentiment_score": Decimal("0.7"),
        "sentiment_confidence": Decimal("0.8"),
        "strength_score": Decimal("0.6"),
        "strength_confidence": Decimal("0.9"),
        "volume_profile_score": Decimal("0.5"),
        "volume_profile_confidence": Decimal("0.7"),
        "drl_score": Decimal("0.8"),
        "drl_confidence": Decimal("0.85"),
    }
    defaults.update(kwargs)
    return SignalScores(**defaults)  # type: ignore[arg-type]


class TestCompositeScore:
    def test_bull_regime_weights_drl_highest(self) -> None:
        result = compute_composite_score(_sample_signals(), MarketRegime.BULL)
        assert result.regime == MarketRegime.BULL
        assert result.component_contributions["drl"] >= result.component_contributions["sentiment"]

    def test_sideways_regime_weights_volume_profile_highest(self) -> None:
        result = compute_composite_score(_sample_signals(), MarketRegime.SIDEWAYS)
        vp = result.component_contributions["volume_profile"]
        sent = result.component_contributions["sentiment"]
        assert vp >= sent

    def test_composite_score_in_zero_one(self) -> None:
        result = compute_composite_score(_sample_signals(), MarketRegime.BULL)
        assert Decimal("0") <= result.composite_score <= Decimal("1")

    def test_realistic_inputs_pass_default_threshold(self) -> None:
        """R1 regression: realistic signals must produce composites above min_score."""
        result = compute_composite_score(_sample_signals(), MarketRegime.BULL)
        assert result.composite_score >= Decimal("0.20")

    def test_low_confidence_gates_to_zero(self) -> None:
        """Confidence below 0.20 should zero out via soft ramp."""
        low_conf = SignalScores(
            sentiment_score=Decimal("0.9"),
            sentiment_confidence=Decimal("0.10"),
            strength_score=Decimal("0.9"),
            strength_confidence=Decimal("0.10"),
            volume_profile_score=Decimal("0.9"),
            volume_profile_confidence=Decimal("0.10"),
            drl_score=Decimal("0.9"),
            drl_confidence=Decimal("0.10"),
        )
        result = compute_composite_score(low_conf, MarketRegime.BULL)
        assert result.composite_score == Decimal("0")

    def test_soft_ramp_produces_partial_contribution(self) -> None:
        """Confidence above threshold but below 1.0 should partially scale."""
        mid_conf = _sample_signals(
            sentiment_confidence=Decimal("0.60"),
            strength_confidence=Decimal("0.60"),
            volume_profile_confidence=Decimal("0.60"),
            drl_confidence=Decimal("0.60"),
        )
        full_conf = _sample_signals(
            sentiment_confidence=Decimal("1.0"),
            strength_confidence=Decimal("1.0"),
            volume_profile_confidence=Decimal("1.0"),
            drl_confidence=Decimal("1.0"),
        )
        mid_result = compute_composite_score(mid_conf, MarketRegime.BULL)
        full_result = compute_composite_score(full_conf, MarketRegime.BULL)
        assert mid_result.composite_score < full_result.composite_score
        assert mid_result.composite_score > Decimal("0")

    def test_confidence_ramp_values(self) -> None:
        assert confidence_ramp(Decimal("0.10")) == Decimal("0")
        assert confidence_ramp(Decimal("0.20")) == Decimal("0")
        assert confidence_ramp(Decimal("1.0")) == Decimal("1")
        mid = confidence_ramp(Decimal("0.60"))
        assert Decimal("0") < mid < Decimal("1")

    def test_confidence_ramp_threshold_ge_one(self) -> None:
        """Test confidence_ramp with threshold >= 1 when confidence >= threshold."""
        # When threshold is 1.0, ceiling becomes 0, so function returns 1 if confidence >= threshold
        result = confidence_ramp(Decimal("1.0"), threshold=Decimal("1.0"))
        assert result == Decimal("1")

        # Same with threshold > 1, if confidence >= threshold
        result = confidence_ramp(Decimal("1.5"), threshold=Decimal("1.5"))
        assert result == Decimal("1")

        # When confidence < threshold, returns 0
        result = confidence_ramp(Decimal("0.9"), threshold=Decimal("1.0"))
        assert result == Decimal("0")

    def test_all_zero_signals_yield_zero(self) -> None:
        zeros = SignalScores(
            sentiment_score=Decimal("0"),
            sentiment_confidence=Decimal("0"),
            strength_score=Decimal("0"),
            strength_confidence=Decimal("0"),
            volume_profile_score=Decimal("0"),
            volume_profile_confidence=Decimal("0"),
            drl_score=Decimal("0"),
            drl_confidence=Decimal("0"),
        )
        result = compute_composite_score(zeros, MarketRegime.BULL)
        assert result.composite_score == Decimal("0")

    def test_invalid_score_raises(self) -> None:
        with pytest.raises(ConfigError, match="must be in"):
            compute_composite_score(
                _sample_signals(sentiment_score=Decimal("1.5")),
                MarketRegime.BULL,
            )

    def test_invalid_score_upper_bound_raises(self) -> None:
        """Test that score > 1 raises ConfigError."""
        with pytest.raises(ConfigError, match="must be in"):
            compute_composite_score(
                _sample_signals(strength_score=Decimal("1.1")),
                MarketRegime.BULL,
            )

    def test_invalid_confidence_raises(self) -> None:
        """Test that confidence > 1 raises ConfigError."""
        with pytest.raises(ConfigError, match="must be in"):
            compute_composite_score(
                _sample_signals(sentiment_confidence=Decimal("1.5")),
                MarketRegime.BULL,
            )

    def test_bear_regime_weights_sentiment_highest(self) -> None:
        """Test BEAR regime weights sentiment highest."""
        result = compute_composite_score(_sample_signals(), MarketRegime.BEAR)
        assert result.regime == MarketRegime.BEAR
        sent = result.component_contributions["sentiment"]
        vp = result.component_contributions["volume_profile"]
        assert sent > vp

    def test_custom_weights_override(self) -> None:
        custom = RegimeWeights(
            sentiment=Decimal("0.50"),
            strength=Decimal("0.20"),
            volume_profile=Decimal("0.20"),
            drl=Decimal("0.10"),
        )
        result = compute_composite_score(_sample_signals(), MarketRegime.BULL, custom)
        assert result.weights_used == custom

    def test_weights_must_sum_to_one(self) -> None:
        with pytest.raises(ConfigError, match="must sum to 1.0"):
            RegimeWeights(
                sentiment=Decimal("0.50"),
                strength=Decimal("0.50"),
                volume_profile=Decimal("0.50"),
                drl=Decimal("0.50"),
            )

    def test_negative_weight_raises(self) -> None:
        """Test that negative weights raise ConfigError."""
        with pytest.raises(ConfigError, match="weight sentiment cannot be negative"):
            RegimeWeights(
                sentiment=Decimal("-0.10"),
                strength=Decimal("0.60"),
                volume_profile=Decimal("0.30"),
                drl=Decimal("0.20"),
            )

    def test_unknown_regime_raises(self) -> None:
        """Test that unknown regime raises ConfigError."""
        # Create a fake regime not in presets
        fake_regime = "UNKNOWN_REGIME"  # type: ignore
        with pytest.raises(ConfigError, match="no weight preset for regime"):
            _weights_for_regime(fake_regime)  # type: ignore


# ── ranking.py ──


class TestRanking:
    def test_empty_candidates_returns_empty(self) -> None:
        result = rank_and_select([])
        assert result.selected == []
        assert result.total_candidates == 0

    def test_threshold_filters_low_scores(self) -> None:
        candidates = [
            ("A", Exchange.NSE, Decimal("0.70"), {}),
            ("B", Exchange.NSE, Decimal("0.10"), {}),
            ("C", Exchange.NSE, Decimal("0.60"), {}),
        ]
        config = RankingConfig(min_score=Decimal("0.20"), top_n=5)
        result = rank_and_select(candidates, config)
        symbols = [r.symbol for r in result.selected]
        assert "B" not in symbols
        assert "A" in symbols
        assert "C" in symbols

    def test_top_n_limits_selection(self) -> None:
        candidates = [
            ("A", Exchange.NSE, Decimal("0.90"), {}),
            ("B", Exchange.NSE, Decimal("0.80"), {}),
            ("C", Exchange.NSE, Decimal("0.70"), {}),
        ]
        config = RankingConfig(min_score=Decimal("0.50"), top_n=2)
        result = rank_and_select(candidates, config)
        assert len(result.selected) == 2
        assert result.selected[0].symbol == "A"
        assert result.selected[0].rank == 1

    def test_correlation_filter_drops_correlated(self) -> None:
        candidates = [
            ("A", Exchange.NSE, Decimal("0.90"), {}),
            ("B", Exchange.NSE, Decimal("0.85"), {}),
            ("C", Exchange.NSE, Decimal("0.70"), {}),
        ]
        correlations = {("A", "B"): Decimal("0.95")}
        config = RankingConfig(
            min_score=Decimal("0.50"),
            top_n=5,
            correlation_limit=Decimal("0.80"),
        )
        result = rank_and_select(candidates, config, correlations)
        symbols = [r.symbol for r in result.selected]
        assert "A" in symbols
        assert "B" not in symbols
        assert "C" in symbols

    def test_invalid_config_raises(self) -> None:
        with pytest.raises(ConfigError, match="top_n must be positive"):
            RankingConfig(top_n=0)
        with pytest.raises(ConfigError, match="min_score must be in"):
            RankingConfig(min_score=Decimal("1.5"))
        with pytest.raises(ConfigError, match="correlation_limit must be in"):
            RankingConfig(correlation_limit=Decimal("1.5"))
        with pytest.raises(ConfigError, match="correlation_limit must be in"):
            RankingConfig(correlation_limit=Decimal("-0.1"))


# ── instrument_scorer.py (integration) ──


def _make_signals(
    symbol: str,
    exchange: Exchange,
    scores: tuple[Decimal, ...],
) -> InstrumentSignals:
    return InstrumentSignals(
        symbol=symbol,
        exchange=exchange,
        sentiment=SentimentSignalOutput(
            score=scores[0],
            confidence=Decimal("0.8"),
            directional_bias="BULLISH",
            metadata={},
        ),
        strength=StrengthSignalOutput(
            score=scores[1],
            confidence=Decimal("0.9"),
            regime=MarketRegime.BULL,
            tradable=True,
            metadata={},
        ),
        volume_profile=VolumeProfileSignalOutput(
            score=scores[2],
            confidence=Decimal("0.7"),
            shape=ProfileShape.D_BALANCED,
            poc_distance_pct=Decimal("2"),
            va_width_pct=Decimal("5"),
            metadata={},
        ),
        drl=compute_drl_signal(_sample_conclusion(instrument_symbol=symbol), _NOW),
    )


class TestInstrumentScorer:
    def test_score_and_select_returns_ranked_instruments(self) -> None:
        scorer = InstrumentScorer()
        signals = [
            _make_signals(
                "NIFTY",
                Exchange.NSE,
                (Decimal("0.8"), Decimal("0.7"), Decimal("0.6")),
            ),
            _make_signals(
                "BANKNIFTY",
                Exchange.NSE,
                (Decimal("0.3"), Decimal("0.3"), Decimal("0.2")),
            ),
            _make_signals(
                "BTCUSDT",
                Exchange.BINANCE,
                (Decimal("0.9"), Decimal("0.8"), Decimal("0.7")),
            ),
        ]
        result = scorer.score_and_select(signals, MarketRegime.BULL)
        assert result.total_candidates == 3
        assert len(result.selected) >= 1
        assert result.selected[0].rank == 1

    def test_empty_signals_returns_empty_selection(self) -> None:
        scorer = InstrumentScorer()
        result = scorer.score_and_select([], MarketRegime.BULL)
        assert result.selected == []

    def test_custom_weights_propagate(self) -> None:
        custom = {
            MarketRegime.BULL: RegimeWeights(
                sentiment=Decimal("0.50"),
                strength=Decimal("0.20"),
                volume_profile=Decimal("0.20"),
                drl=Decimal("0.10"),
            ),
        }
        scorer = InstrumentScorer(custom_weights=custom)
        signals = [
            _make_signals("NIFTY", Exchange.NSE, (Decimal("0.8"), Decimal("0.7"), Decimal("0.6"))),
        ]
        scored = scorer.score_instruments(signals, MarketRegime.BULL)
        assert scored[0].composite.weights_used == custom[MarketRegime.BULL]

    def test_rank_normalization_discriminates_clustered_scores(self) -> None:
        """Phase 2A: clustered raw scores should produce spread ranks."""
        scorer = InstrumentScorer()
        signals = [
            _make_signals(
                "A",
                Exchange.NSE,
                (Decimal("0.70"), Decimal("0.70"), Decimal("0.70")),
            ),
            _make_signals(
                "B",
                Exchange.NSE,
                (Decimal("0.71"), Decimal("0.71"), Decimal("0.71")),
            ),
            _make_signals(
                "C",
                Exchange.BINANCE,
                (Decimal("0.72"), Decimal("0.72"), Decimal("0.72")),
            ),
        ]
        scored = scorer.score_instruments(signals, MarketRegime.BULL)
        composites = [s.composite.composite_score for s in scored]
        assert composites[0] != composites[2]


# ── StrategyContext selection fields ──


class TestStrategyContextSelection:
    def _context(
        self,
        rank: int | None = None,
        score: Decimal | None = None,
    ) -> object:
        from iatb.strategies.base import StrategyContext

        return StrategyContext(
            exchange=Exchange.NSE,
            symbol="NIFTY",
            side=OrderSide.BUY,
            strength_inputs=StrengthInputs(
                breadth_ratio=Decimal("1.5"),
                regime=MarketRegime.BULL,
                adx=Decimal("30"),
                volume_ratio=Decimal("1.5"),
                volatility_atr_pct=Decimal("0.02"),
            ),
            composite_score=score,
            selection_rank=rank,
        )

    def test_context_with_valid_rank_passes(self) -> None:
        from iatb.strategies.base import StrategyBase

        ctx = self._context(rank=1, score=Decimal("0.5"))
        assert StrategyBase().can_emit_signal(ctx) is True

    def test_context_with_zero_rank_blocked(self) -> None:
        from iatb.strategies.base import StrategyBase

        ctx = self._context(rank=0)
        assert StrategyBase().can_emit_signal(ctx) is False

    def test_context_without_rank_passes(self) -> None:
        from iatb.strategies.base import StrategyBase

        ctx = self._context(rank=None)
        assert StrategyBase().can_emit_signal(ctx) is True


# ── correlation_matrix.py ──


class TestCorrelationMatrix:
    def test_identical_series_correlation_near_one(self) -> None:
        from iatb.selection.correlation_matrix import compute_pairwise_correlations

        prices = [Decimal(str(i)) for i in range(100, 110)]
        result = compute_pairwise_correlations({"A": prices, "B": prices})
        assert result[("A", "B")] > Decimal("0.99")

    def test_single_instrument_returns_empty(self) -> None:
        from iatb.selection.correlation_matrix import compute_pairwise_correlations

        result = compute_pairwise_correlations(
            {"A": [Decimal("100"), Decimal("101")]},
        )
        assert result == {}

    def test_three_instruments_produce_three_pairs(self) -> None:
        from iatb.selection.correlation_matrix import compute_pairwise_correlations

        prices = [Decimal(str(i)) for i in range(100, 106)]
        result = compute_pairwise_correlations(
            {"A": prices, "B": prices, "C": prices},
        )
        assert len(result) == 3

    def test_anti_correlated_returns(self) -> None:
        from iatb.selection.correlation_matrix import compute_pairwise_correlations

        base = Decimal("100")
        a_prices: list[Decimal] = [base]
        b_prices: list[Decimal] = [base]
        for i in range(1, 30):
            delta = Decimal(i % 5) - Decimal("2")
            a_prices.append(a_prices[-1] + delta)
            b_prices.append(b_prices[-1] - delta)
        result = compute_pairwise_correlations({"A": a_prices, "B": b_prices})
        assert result[("A", "B")] < Decimal("-0.5")

    def test_prices_must_have_at_least_2_points(self) -> None:
        """Test that price series with less than 2 points raises ConfigError."""
        from iatb.selection.correlation_matrix import compute_pairwise_correlations

        with pytest.raises(ConfigError, match="must have at least 2 points"):
            compute_pairwise_correlations({"A": [Decimal("100")], "B": [Decimal("100")]})

    def test_single_price_returns_empty_correlations(self) -> None:
        """Test that single instrument returns empty dict."""
        from iatb.selection.correlation_matrix import compute_pairwise_correlations

        result = compute_pairwise_correlations(
            {"A": [Decimal("100"), Decimal("101")]},
        )
        assert result == {}

    def test_zero_denominator_returns_zero_correlation(self) -> None:
        """Test that zero denominator returns zero correlation (line 67)."""
        from iatb.selection.correlation_matrix import compute_pairwise_correlations

        # When variance is zero (constant prices), denom will be 0
        result = compute_pairwise_correlations(
            {
                "A": [Decimal("100"), Decimal("100"), Decimal("100")],
                "B": [Decimal("200"), Decimal("200"), Decimal("200")],
            }
        )
        # Both have zero variance, so denom = 0, should return 0
        assert result[("A", "B")] == Decimal("0")

    def test_mean_empty_list_returns_zero(self) -> None:
        """Test _mean returns Decimal("0") for empty list (line 74)."""
        from iatb.selection.correlation_matrix import _mean

        result = _mean([])
        assert result == Decimal("0")


# ── decay overrides ──


class TestDecayOverrides:
    def test_override_changes_decay_rate(self) -> None:
        fast = temporal_decay(
            _OLD,
            _NOW,
            "sentiment",
            decay_overrides={"sentiment": Decimal("0.50")},
        )
        default = temporal_decay(_OLD, _NOW, "sentiment")
        assert fast < default

    def test_override_for_unknown_signal_works(self) -> None:
        result = temporal_decay(
            _NOW,
            _NOW,
            "custom_signal",
            decay_overrides={"custom_signal": Decimal("0.10")},
        )
        assert result == Decimal("1")


# ── ic_monitor.py ──


class TestICMonitor:
    def test_perfect_correlation_yields_high_ic(self) -> None:
        from iatb.selection.ic_monitor import compute_information_coefficient

        scores = [Decimal(str(i)) for i in range(10)]
        returns = [Decimal(str(i)) for i in range(10)]
        result = compute_information_coefficient(scores, returns)
        assert result.ic == Decimal("1")
        assert result.above_threshold is True

    def test_inverse_correlation_yields_negative_ic(self) -> None:
        from iatb.selection.ic_monitor import compute_information_coefficient

        scores = [Decimal(str(i)) for i in range(10)]
        returns = [Decimal(str(9 - i)) for i in range(10)]
        result = compute_information_coefficient(scores, returns)
        assert result.ic == Decimal("-1")

    def test_alpha_decay_detects_low_ic(self) -> None:
        from iatb.selection.ic_monitor import check_alpha_decay

        # Scores inversely ordered vs returns → negative IC < threshold
        scores = [Decimal(str(9 - i)) for i in range(10)]
        returns = [Decimal(str(i)) for i in range(10)]
        assert check_alpha_decay(scores, returns) is True

    def test_too_few_observations_raises(self) -> None:
        from iatb.selection.ic_monitor import compute_information_coefficient

        with pytest.raises(ConfigError, match="at least 3"):
            compute_information_coefficient(
                [Decimal("1"), Decimal("2")],
                [Decimal("1"), Decimal("2")],
            )

    def test_length_mismatch_raises(self) -> None:
        from iatb.selection.ic_monitor import compute_information_coefficient

        with pytest.raises(ConfigError, match="equal length"):
            compute_information_coefficient(
                [Decimal("1")] * 5,
                [Decimal("1")] * 3,
            )

    def test_assign_ranks_handles_ties(self) -> None:
        """Test _assign_ranks handles tied values correctly (lines 92-105)."""
        from iatb.selection.ic_monitor import _assign_ranks

        # Three values: 1, 1, 2 - the two 1's should share rank 1.5
        ranks = _assign_ranks([Decimal("1"), Decimal("1"), Decimal("2")])
        # Sorted: [0:1, 1:1, 2:2]
        # Ranks: [1.5, 1.5, 3] (average of 1+2=3/2=1.5 for the two 1's)
        assert ranks[0] == Decimal("1.5")
        assert ranks[1] == Decimal("1.5")
        assert ranks[2] == Decimal("3")

    def test_assign_ranks_all_same_returns_same_rank(self) -> None:
        """Test _assign_ranks when all values are the same."""
        from iatb.selection.ic_monitor import _assign_ranks

        ranks = _assign_ranks([Decimal("5"), Decimal("5"), Decimal("5"), Decimal("5")])
        # All should get the same average rank
        assert ranks[0] == ranks[1] == ranks[2] == ranks[3]
        assert ranks[0] == Decimal("2.5")  # (1+2+3+4)/4 = 2.5

    def test_spearman_zero_denominator_returns_zero(self) -> None:
        """Test _spearman_rank_correlation with n=1 returns 0 (line 87)."""
        from iatb.selection.ic_monitor import _spearman_rank_correlation

        # When n=1, denom = 1 * (1 - 1) = 0, should return 0
        result = _spearman_rank_correlation([Decimal("5")], [Decimal("10")])
        assert result == Decimal("0")


# ── ADX sqrt normalization ──


class TestADXSqrtNormalization:
    def test_sqrt_emphasizes_early_trend(self) -> None:
        from iatb.market_strength.strength_scorer import StrengthScorer

        scorer = StrengthScorer()
        low_adx = StrengthInputs(
            breadth_ratio=Decimal("1.0"),
            regime=MarketRegime.BULL,
            adx=Decimal("15"),
            volume_ratio=Decimal("1.0"),
            volatility_atr_pct=Decimal("0.03"),
        )
        mid_adx = StrengthInputs(
            breadth_ratio=Decimal("1.0"),
            regime=MarketRegime.BULL,
            adx=Decimal("30"),
            volume_ratio=Decimal("1.0"),
            volatility_atr_pct=Decimal("0.03"),
        )
        low_score = scorer.score(Exchange.NSE, low_adx)
        mid_score = scorer.score(Exchange.NSE, mid_adx)
        gap = mid_score - low_score
        # sqrt makes the 15→30 jump smaller than linear would
        # Linear: (30/40 - 15/40)*0.25 = 0.09375
        # Sqrt: (sqrt(0.75) - sqrt(0.375))*0.25 ≈ 0.063
        assert gap < Decimal("0.08")
        assert gap > Decimal("0")

    def test_concave_normalize_at_zero(self) -> None:
        from iatb.market_strength.strength_scorer import StrengthScorer

        scorer = StrengthScorer(cache_enabled=False)
        result = scorer._normalize_concave(Decimal("0"), cap=Decimal("40"))
        assert result == Decimal("0")

    def test_concave_normalize_at_cap(self) -> None:
        from iatb.market_strength.strength_scorer import StrengthScorer

        scorer = StrengthScorer(cache_enabled=False)
        result = scorer._normalize_concave(Decimal("40"), cap=Decimal("40"))
        assert result == Decimal("1")


# ── predict_with_confidence (unit, no SB3 dep) ──


class TestPredictWithConfidence:
    def test_no_model_raises(self) -> None:
        from iatb.rl.agent import RLAgent

        agent = RLAgent()
        with pytest.raises(ConfigError, match="not initialized"):
            agent.predict_with_confidence([Decimal("1")])


# ── selection_bridge.py ──


class TestSelectionBridge:
    def _bull_strength(self) -> StrengthInputs:
        return StrengthInputs(
            breadth_ratio=Decimal("1.5"),
            regime=MarketRegime.BULL,
            adx=Decimal("30"),
            volume_ratio=Decimal("1.5"),
            volatility_atr_pct=Decimal("0.02"),
        )

    def test_builds_contexts_from_selection(self) -> None:
        from iatb.selection.selection_bridge import build_strategy_contexts

        selection = SelectionResult(
            selected=[
                RankedInstrument(
                    symbol="NIFTY",
                    exchange=Exchange.NSE,
                    composite_score=Decimal("0.80"),
                    rank=1,
                    metadata={},
                ),
                RankedInstrument(
                    symbol="BANKNIFTY",
                    exchange=Exchange.NSE,
                    composite_score=Decimal("0.60"),
                    rank=2,
                    metadata={},
                ),
            ],
            filtered_count=1,
            total_candidates=3,
        )
        strength_map = {
            "NIFTY": self._bull_strength(),
            "BANKNIFTY": self._bull_strength(),
        }
        contexts = build_strategy_contexts(selection, strength_map)
        assert len(contexts) == 2
        assert contexts[0].symbol == "NIFTY"
        assert contexts[0].composite_score == Decimal("0.80")
        assert contexts[0].selection_rank == 1
        assert contexts[1].selection_rank == 2

    def test_empty_selection_returns_empty(self) -> None:
        from iatb.selection.selection_bridge import build_strategy_contexts

        empty = SelectionResult(selected=[], filtered_count=0, total_candidates=0)
        assert build_strategy_contexts(empty, {}) == []

    def test_missing_strength_raises(self) -> None:
        from iatb.selection.selection_bridge import build_strategy_contexts

        selection = SelectionResult(
            selected=[
                RankedInstrument(
                    symbol="UNKNOWN",
                    exchange=Exchange.NSE,
                    composite_score=Decimal("0.50"),
                    rank=1,
                    metadata={},
                ),
            ],
            filtered_count=0,
            total_candidates=1,
        )
        with pytest.raises(ConfigError, match="no StrengthInputs"):
            build_strategy_contexts(selection, {})

    def test_scale_quantity_by_rank(self) -> None:
        from iatb.selection.selection_bridge import scale_quantity_by_rank

        rank1 = scale_quantity_by_rank(Decimal("100"), rank=1, total_selected=3)
        rank3 = scale_quantity_by_rank(Decimal("100"), rank=3, total_selected=3)
        assert rank1 == Decimal("100")

        assert rank3 < rank1
        assert rank3 > Decimal("0")

    def test_extract_strength_map(self) -> None:
        from iatb.selection.selection_bridge import extract_strength_map

        bull = self._bull_strength()
        signals = [
            _make_signals_with_strength(
                "NIFTY",
                Exchange.NSE,
                (Decimal("0.7"), Decimal("0.7"), Decimal("0.7")),
                bull,
            ),
        ]
        result = extract_strength_map(signals)
        assert "NIFTY" in result
        assert result["NIFTY"] == bull

    def test_extract_strength_map_missing_raises(self) -> None:
        from iatb.selection.selection_bridge import extract_strength_map

        signals = [
            _make_signals(
                "NIFTY",
                Exchange.NSE,
                (Decimal("0.7"), Decimal("0.7"), Decimal("0.7")),
            ),
        ]
        with pytest.raises(ConfigError, match="no strength_inputs"):
            extract_strength_map(signals)

    def test_extract_strength_map_missing_symbol_raises(self) -> None:
        """Test extract_strength_map raises when signal lacks symbol."""
        from iatb.selection.selection_bridge import extract_strength_map

        class FakeSignal:
            def __init__(self) -> None:
                self.strength_inputs = StrengthInputs(
                    breadth_ratio=Decimal("1.5"),
                    regime=MarketRegime.BULL,
                    adx=Decimal("30"),
                    volume_ratio=Decimal("1.5"),
                    volatility_atr_pct=Decimal("0.02"),
                )

        signals = [FakeSignal()]
        with pytest.raises(ConfigError, match="signal missing symbol"):
            extract_strength_map(signals)

    def test_scale_quantity_total_selected_zero_raises(self) -> None:
        """Test scale_quantity_by_rank raises for zero total_selected."""
        from iatb.selection.selection_bridge import scale_quantity_by_rank

        with pytest.raises(ConfigError, match="total_selected must be positive"):
            scale_quantity_by_rank(Decimal("100"), rank=1, total_selected=0)

    def test_scale_quantity_rank_out_of_range_raises(self) -> None:
        """Test scale_quantity_by_rank raises for invalid rank."""
        from iatb.selection.selection_bridge import scale_quantity_by_rank

        # Rank < 1
        with pytest.raises(ConfigError, match="rank 0 out of range"):
            scale_quantity_by_rank(Decimal("100"), rank=0, total_selected=3)

        # Rank > total_selected
        with pytest.raises(ConfigError, match="rank 4 out of range"):
            scale_quantity_by_rank(Decimal("100"), rank=4, total_selected=3)

    def test_scale_quantity_zero_base_raises(self) -> None:
        """Test scale_quantity_by_rank raises for zero base_quantity."""
        from iatb.selection.selection_bridge import scale_quantity_by_rank

        with pytest.raises(ConfigError, match="base_quantity must be positive"):
            scale_quantity_by_rank(Decimal("0"), rank=1, total_selected=3)

    def test_scale_quantity_negative_base_raises(self) -> None:
        """Test scale_quantity_by_rank raises for negative base_quantity."""
        from iatb.selection.selection_bridge import scale_quantity_by_rank

        with pytest.raises(ConfigError, match="base_quantity must be positive"):
            scale_quantity_by_rank(Decimal("-100"), rank=1, total_selected=3)


def _make_signals_with_strength(
    symbol: str,
    exchange: Exchange,
    scores: tuple[Decimal, ...],
    strength_inputs: StrengthInputs,
) -> InstrumentSignals:
    return InstrumentSignals(
        symbol=symbol,
        exchange=exchange,
        sentiment=SentimentSignalOutput(
            score=scores[0],
            confidence=Decimal("0.8"),
            directional_bias="BULLISH",
            metadata={},
        ),
        strength=StrengthSignalOutput(
            score=scores[1],
            confidence=Decimal("0.9"),
            regime=MarketRegime.BULL,
            tradable=True,
            metadata={},
        ),
        volume_profile=VolumeProfileSignalOutput(
            score=scores[2],
            confidence=Decimal("0.7"),
            shape=ProfileShape.D_BALANCED,
            poc_distance_pct=Decimal("2"),
            va_width_pct=Decimal("5"),
            metadata={},
        ),
        drl=compute_drl_signal(
            _sample_conclusion(instrument_symbol=symbol),
            _NOW,
        ),
        strength_inputs=strength_inputs,
    )


# ── weight_optimizer.py (validation only, no Optuna dep) ──


class TestWeightOptimizerValidation:
    def test_too_few_observations_raises(self) -> None:
        from iatb.selection.weight_optimizer import optimize_weights_for_regime

        with pytest.raises(ConfigError, match="at least 10"):
            optimize_weights_for_regime(
                MarketRegime.BULL,
                [{"sentiment": Decimal("0.5")}] * 5,
                [Decimal("0.01")] * 5,
            )

    def test_length_mismatch_raises(self) -> None:
        from iatb.selection.weight_optimizer import optimize_weights_for_regime

        with pytest.raises(ConfigError, match="equal length"):
            optimize_weights_for_regime(
                MarketRegime.BULL,
                [{"sentiment": Decimal("0.5")}] * 20,
                [Decimal("0.01")] * 10,
            )
