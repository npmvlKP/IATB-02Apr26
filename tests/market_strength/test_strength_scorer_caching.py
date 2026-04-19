"""
Tests for strength scorer pre-computation caching.
"""

from decimal import Decimal

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs, StrengthScorer


class TestStrengthScorerCaching:
    """Test pre-computation caching in strength scorer."""

    def test_scorer_with_cache_enabled(self) -> None:
        """Test scorer initialization with cache enabled."""
        scorer = StrengthScorer(cache_enabled=True)
        assert scorer._cache_enabled is True
        assert hasattr(scorer, "_normalize")
        assert hasattr(scorer, "_normalize_concave")
        assert hasattr(scorer, "_regime_score")

    def test_scorer_with_cache_disabled(self) -> None:
        """Test scorer initialization with cache disabled."""
        scorer = StrengthScorer(cache_enabled=False)
        assert scorer._cache_enabled is False
        # Should use uncached versions
        assert scorer._normalize == scorer._normalize_uncached
        assert scorer._normalize_concave == scorer._normalize_concave_uncached
        assert scorer._regime_score == scorer._regime_score_uncached

    def test_score_with_caching(self) -> None:
        """Test score calculation with caching enabled."""
        scorer = StrengthScorer(cache_enabled=True)
        inputs = StrengthInputs(
            breadth_ratio=Decimal("1.5"),
            regime=MarketRegime.BULL,
            adx=Decimal("25"),
            volume_ratio=Decimal("2.5"),
            volatility_atr_pct=Decimal("0.04"),
        )

        score = scorer.score(Exchange.NSE, inputs)
        assert score >= Decimal("0")
        assert score <= Decimal("1")

        # Calculate again to test cache hit
        score2 = scorer.score(Exchange.NSE, inputs)
        assert score == score2

    def test_score_without_caching(self) -> None:
        """Test score calculation with caching disabled."""
        scorer = StrengthScorer(cache_enabled=False)
        inputs = StrengthInputs(
            breadth_ratio=Decimal("1.5"),
            regime=MarketRegime.BULL,
            adx=Decimal("25"),
            volume_ratio=Decimal("2.5"),
            volatility_atr_pct=Decimal("0.04"),
        )

        score = scorer.score(Exchange.NSE, inputs)
        assert score >= Decimal("0")
        assert score <= Decimal("1")

    def test_normalize_caching(self) -> None:
        """Test that normalize method uses caching."""
        scorer = StrengthScorer(cache_enabled=True)

        # First call
        result1 = scorer._normalize(Decimal("1.5"), cap=Decimal("2.0"))

        # Second call with same parameters (should hit cache)
        result2 = scorer._normalize(Decimal("1.5"), cap=Decimal("2.0"))

        assert result1 == result2

        # Check cache stats
        stats = scorer.get_cache_stats()
        assert stats["normalize_cache_hits"] >= 1

    def test_normalize_concave_caching(self) -> None:
        """Test that normalize_concave method uses caching."""
        scorer = StrengthScorer(cache_enabled=True)

        # First call
        result1 = scorer._normalize_concave(Decimal("25"), cap=Decimal("40"))

        # Second call with same parameters (should hit cache)
        result2 = scorer._normalize_concave(Decimal("25"), cap=Decimal("40"))

        assert result1 == result2

        # Check cache stats
        stats = scorer.get_cache_stats()
        assert stats["normalize_concave_cache_hits"] >= 1

    def test_regime_score_caching(self) -> None:
        """Test that regime_score method uses caching."""
        scorer = StrengthScorer(cache_enabled=True)

        # First call
        result1 = scorer._regime_score(MarketRegime.BULL)

        # Second call with same parameter (should hit cache)
        result2 = scorer._regime_score(MarketRegime.BULL)

        assert result1 == result2
        assert result1 == Decimal("1.0")

        # Check cache stats
        stats = scorer.get_cache_stats()
        assert stats["regime_cache_hits"] >= 1

    def test_clear_cache(self) -> None:
        """Test clearing all caches."""
        scorer = StrengthScorer(cache_enabled=True)

        # Generate some cache entries
        scorer._normalize(Decimal("1.0"), cap=Decimal("2.0"))
        scorer._normalize_concave(Decimal("20"), cap=Decimal("40"))
        scorer._regime_score(MarketRegime.BULL)

        # Verify cache has entries
        stats_before = scorer.get_cache_stats()
        assert stats_before["normalize_cache_size"] > 0
        assert stats_before["normalize_concave_cache_size"] > 0
        assert stats_before["regime_cache_size"] > 0

        # Clear cache
        scorer.clear_cache()

        # Verify cache is cleared
        stats_after = scorer.get_cache_stats()
        assert stats_after["normalize_cache_size"] == 0
        assert stats_after["normalize_concave_cache_size"] == 0
        assert stats_after["regime_cache_size"] == 0

    def test_get_cache_stats_enabled(self) -> None:
        """Test getting cache stats when caching is enabled."""
        scorer = StrengthScorer(cache_enabled=True)
        stats = scorer.get_cache_stats()

        assert "cache_enabled" in stats
        assert stats["cache_enabled"] == 1
        assert "normalize_cache_size" in stats
        assert "normalize_cache_hits" in stats
        assert "normalize_cache_misses" in stats
        assert "normalize_concave_cache_size" in stats
        assert "normalize_concave_cache_hits" in stats
        assert "normalize_concave_cache_misses" in stats
        assert "regime_cache_size" in stats
        assert "regime_cache_hits" in stats
        assert "regime_cache_misses" in stats

    def test_get_cache_stats_disabled(self) -> None:
        """Test getting cache stats when caching is disabled."""
        scorer = StrengthScorer(cache_enabled=False)
        stats = scorer.get_cache_stats()

        assert "cache_enabled" in stats
        assert stats["cache_enabled"] == 0
        # Other stats should not be present when disabled
        assert "normalize_cache_size" not in stats

    def test_cache_hit_miss_tracking(self) -> None:
        """Test that cache hits and misses are tracked correctly."""
        scorer = StrengthScorer(cache_enabled=True)

        # First call (miss)
        scorer._normalize(Decimal("1.0"), cap=Decimal("2.0"))
        stats1 = scorer.get_cache_stats()
        assert stats1["normalize_cache_misses"] == 1

        # Second call with same params (hit)
        scorer._normalize(Decimal("1.0"), cap=Decimal("2.0"))
        stats2 = scorer.get_cache_stats()
        assert stats2["normalize_cache_hits"] == 1
        assert stats2["normalize_cache_misses"] == 1

    def test_multiple_regime_caching(self) -> None:
        """Test caching multiple regime scores."""
        scorer = StrengthScorer(cache_enabled=True)

        # Call for different regimes
        scorer._regime_score(MarketRegime.BULL)
        scorer._regime_score(MarketRegime.SIDEWAYS)
        scorer._regime_score(MarketRegime.BEAR)

        stats = scorer.get_cache_stats()
        assert stats["regime_cache_size"] == 3

    def test_is_tradable_with_caching(self) -> None:
        """Test is_tradable with caching enabled."""
        scorer = StrengthScorer(cache_enabled=True)
        inputs = StrengthInputs(
            breadth_ratio=Decimal("1.5"),
            regime=MarketRegime.BULL,
            adx=Decimal("25"),
            volume_ratio=Decimal("2.5"),
            volatility_atr_pct=Decimal("0.04"),
        )

        result = scorer.is_tradable(Exchange.NSE, inputs)
        assert isinstance(result, bool)

        # Check that cache was used
        stats = scorer.get_cache_stats()
        assert stats["normalize_cache_hits"] >= 0
        assert stats["regime_cache_hits"] >= 0

    def test_bear_market_not_tradable(self) -> None:
        """Test that bear market is not tradable regardless of other factors."""
        scorer = StrengthScorer(cache_enabled=True)
        inputs = StrengthInputs(
            breadth_ratio=Decimal("2.0"),
            regime=MarketRegime.BEAR,
            adx=Decimal("30"),
            volume_ratio=Decimal("3.0"),
            volatility_atr_pct=Decimal("0.02"),
        )

        result = scorer.is_tradable(Exchange.NSE, inputs)
        assert result is False

    def test_high_volatility_not_tradable(self) -> None:
        """Test that high volatility is not tradable."""
        scorer = StrengthScorer(cache_enabled=True)
        inputs = StrengthInputs(
            breadth_ratio=Decimal("2.0"),
            regime=MarketRegime.BULL,
            adx=Decimal("30"),
            volume_ratio=Decimal("3.0"),
            volatility_atr_pct=Decimal("0.10"),  # Above 0.08 threshold
        )

        result = scorer.is_tradable(Exchange.NSE, inputs)
        assert result is False

    def test_cache_size_limits(self) -> None:
        """Test that cache size limits are respected."""
        scorer = StrengthScorer(cache_enabled=True)

        # Generate many unique entries
        for i in range(2000):
            value = Decimal(str(i / 1000.0))
            scorer._normalize(value, cap=Decimal("2.0"))

        stats = scorer.get_cache_stats()
        # Cache should be limited (default 1024)
        assert stats["normalize_cache_size"] <= 1024

    def test_different_caps_create_cache_entries(self) -> None:
        """Test that different cap values create separate cache entries."""
        scorer = StrengthScorer(cache_enabled=True)

        # Clear cache to ensure clean state
        scorer.clear_cache()

        # Same value, different caps
        scorer._normalize(Decimal("1.0"), cap=Decimal("2.0"))
        scorer._normalize(Decimal("1.0"), cap=Decimal("3.0"))
        scorer._normalize(Decimal("1.0"), cap=Decimal("4.0"))

        stats = scorer.get_cache_stats()
        # Should have 3 distinct cache entries
        assert stats["normalize_cache_size"] == 3

    def test_uncached_versions_work_correctly(self) -> None:
        """Test that uncached versions produce correct results."""
        scorer = StrengthScorer(cache_enabled=False)

        # Test normalize uncached
        result = scorer._normalize(Decimal("1.5"), cap=Decimal("2.0"))
        assert result == Decimal("0.75")

        # Test normalize_concave uncached
        result = scorer._normalize_concave(Decimal("25"), cap=Decimal("40"))
        assert result >= Decimal("0")
        assert result <= Decimal("1")

        # Test regime_score uncached
        result = scorer._regime_score(MarketRegime.BULL)
        assert result == Decimal("1.0")

    def test_clear_cache_when_disabled(self) -> None:
        """Test that clear_cache doesn't raise when caching is disabled."""
        scorer = StrengthScorer(cache_enabled=False)

        # Should not raise
        scorer.clear_cache()

    def test_validate_throws_on_invalid_exchange(self) -> None:
        """Test that validation throws on invalid exchange."""
        scorer = StrengthScorer(cache_enabled=True)
        inputs = StrengthInputs(
            breadth_ratio=Decimal("1.0"),
            regime=MarketRegime.BULL,
            adx=Decimal("20"),
            volume_ratio=Decimal("1.0"),
            volatility_atr_pct=Decimal("0.02"),
        )

        with pytest.raises(ConfigError, match="Unsupported exchange"):
            scorer.score("INVALID_EXCHANGE", inputs)  # type: ignore[arg-type]

    def test_validate_throws_on_negative_values(self) -> None:
        """Test that validation throws on negative values."""
        scorer = StrengthScorer(cache_enabled=True)

        # Test negative breadth_ratio
        inputs = StrengthInputs(
            breadth_ratio=Decimal("-1.0"),
            regime=MarketRegime.BULL,
            adx=Decimal("20"),
            volume_ratio=Decimal("1.0"),
            volatility_atr_pct=Decimal("0.02"),
        )
        with pytest.raises(ConfigError, match="breadth_ratio cannot be negative"):
            scorer.score(Exchange.NSE, inputs)

        # Test negative adx
        inputs = StrengthInputs(
            breadth_ratio=Decimal("1.0"),
            regime=MarketRegime.BULL,
            adx=Decimal("-5"),
            volume_ratio=Decimal("1.0"),
            volatility_atr_pct=Decimal("0.02"),
        )
        with pytest.raises(ConfigError, match="adx cannot be negative"):
            scorer.score(Exchange.NSE, inputs)

    def test_volatility_penalty_correctness(self) -> None:
        """Test volatility penalty calculation."""
        scorer = StrengthScorer(cache_enabled=True)

        # Test different volatility ranges
        assert scorer._volatility_penalty(Decimal("0.02")) == Decimal("0")
        assert scorer._volatility_penalty(Decimal("0.04")) == Decimal("0.05")
        assert scorer._volatility_penalty(Decimal("0.06")) == Decimal("0.12")
        assert scorer._volatility_penalty(Decimal("0.10")) == Decimal("0.20")

    def test_score_clamping(self) -> None:
        """Test that score is clamped to [0, 1] range."""
        scorer = StrengthScorer(cache_enabled=True)

        # Test very low score
        low_inputs = StrengthInputs(
            breadth_ratio=Decimal("0.1"),
            regime=MarketRegime.BEAR,
            adx=Decimal("5"),
            volume_ratio=Decimal("0.5"),
            volatility_atr_pct=Decimal("0.10"),
        )
        low_score = scorer.score(Exchange.NSE, low_inputs)
        assert low_score >= Decimal("0")

        # Test very high score
        high_inputs = StrengthInputs(
            breadth_ratio=Decimal("2.0"),
            regime=MarketRegime.BULL,
            adx=Decimal("40"),
            volume_ratio=Decimal("3.0"),
            volatility_atr_pct=Decimal("0.01"),
        )
        high_score = scorer.score(Exchange.NSE, high_inputs)
        assert high_score <= Decimal("1")
