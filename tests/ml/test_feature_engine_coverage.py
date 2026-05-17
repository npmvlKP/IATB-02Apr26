"""
Comprehensive test coverage for FeatureEngineer class.
Tests all public functions and edge cases as per coverage requirements.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.feature_engine import FeatureEngineer

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def valid_ohlcv_rows() -> list[dict[str, Decimal]]:
    """Fixture providing valid OHLCV rows for testing."""
    return [
        {
            "open": Decimal("100"),
            "high": Decimal("101"),
            "low": Decimal("99"),
            "close": Decimal("100"),
            "volume": Decimal("1000"),
        },
        {
            "open": Decimal("101"),
            "high": Decimal("102"),
            "low": Decimal("100"),
            "close": Decimal("101"),
            "volume": Decimal("1200"),
        },
        {
            "open": Decimal("100"),
            "high": Decimal("103"),
            "low": Decimal("99"),
            "close": Decimal("102"),
            "volume": Decimal("1100"),
        },
        {
            "open": Decimal("102"),
            "high": Decimal("104"),
            "low": Decimal("101"),
            "close": Decimal("103"),
            "volume": Decimal("1500"),
        },
        {
            "open": Decimal("103"),
            "high": Decimal("105"),
            "low": Decimal("102"),
            "close": Decimal("104"),
            "volume": Decimal("1300"),
        },
    ]


@pytest.fixture()
def valid_sentiment_scores() -> list[Decimal]:
    """Fixture providing valid sentiment scores."""
    return [
        Decimal("0.0"),
        Decimal("0.2"),
        Decimal("0.1"),
        Decimal("-0.1"),
        Decimal("0.3"),
    ]


@pytest.fixture()
def valid_regime_labels() -> list[str]:
    """Fixture providing valid regime labels."""
    return ["NEUTRAL", "BULL", "BEAR", "NEUTRAL", "BULL"]


@pytest.fixture()
def valid_timestamps_utc() -> list[datetime]:
    """Fixture providing valid UTC timestamps."""
    start = datetime(2024, 1, 1, 9, 30, tzinfo=UTC)
    return [start + timedelta(minutes=idx) for idx in range(5)]


@pytest.fixture()
def feature_engineer() -> FeatureEngineer:
    """Fixture providing a FeatureEngineer instance with default volatility_window."""
    return FeatureEngineer(volatility_window=14)


@pytest.fixture()
def feature_engineer_min_window() -> FeatureEngineer:
    """Fixture providing a FeatureEngineer instance with minimum volatility_window."""
    return FeatureEngineer(volatility_window=2)


# =============================================================================
# Test Scenarios
# =============================================================================


# Scenario 1: 3+ rows of valid OHLCV/sentiment/regime/timestamps
class TestScenario01ValidInputs:
    """Test valid inputs produce correctly shaped feature vectors."""

    def test_valid_inputs_correct_shape(
        self,
        feature_engineer: FeatureEngineer,
        valid_ohlcv_rows: list[dict[str, Decimal]],
        valid_sentiment_scores: list[Decimal],
        valid_regime_labels: list[str],
        valid_timestamps_utc: list[datetime],
    ) -> None:
        """Test that valid inputs produce feature vectors with correct shape."""
        result = feature_engineer.build_features(
            valid_ohlcv_rows,
            valid_sentiment_scores,
            valid_regime_labels,
            valid_timestamps_utc,
        )
        # Should have n-1 vectors (one less than input rows)
        assert len(result) == len(valid_ohlcv_rows) - 1
        # Each vector should have 10 features:
        # ret, vol, trend, sentiment, volume_ratio, regime_bull, regime_bear,
        # regime_neutral, hour, minute
        assert len(result[0]) == 10
        # All values should be Decimal
        for row in result:
            for value in row:
                assert isinstance(value, Decimal)


# Scenario 2: Regime one-hot encoding verification (test utility directly)
class TestScenario02RegimeOneHot:
    """Test regime one-hot encoding via _regime_one_hot function."""

    def test_regime_bull_encoding(self) -> None:
        """Test BULL regime encoding."""
        from iatb.ml.feature_engine import _regime_one_hot

        bull = _regime_one_hot("BULL")
        assert bull == (Decimal("1"), Decimal("0"), Decimal("0"))

    def test_regime_bear_encoding(self) -> None:
        """Test BEAR regime encoding."""
        from iatb.ml.feature_engine import _regime_one_hot

        bear = _regime_one_hot("BEAR")
        assert bear == (Decimal("0"), Decimal("1"), Decimal("0"))

    def test_regime_neutral_encoding(self) -> None:
        """Test NEUTRAL regime encoding."""
        from iatb.ml.feature_engine import _regime_one_hot

        neutral = _regime_one_hot("NEUTRAL")
        assert neutral == (Decimal("0"), Decimal("0"), Decimal("1"))

    def test_regime_case_insensitive(self) -> None:
        """Test regime encoding is case-insensitive."""
        from iatb.ml.feature_engine import _regime_one_hot

        bull_lower = _regime_one_hot("bull")
        assert bull_lower == (Decimal("1"), Decimal("0"), Decimal("0"))

        bear_upper = _regime_one_hot("BEAR")
        assert bear_upper == (Decimal("0"), Decimal("1"), Decimal("0"))

        neutral_mixed = _regime_one_hot("NeuTrAl")
        assert neutral_mixed == (Decimal("0"), Decimal("0"), Decimal("1"))

    def test_regime_whitespace_stripped(self) -> None:
        """Test regime encoding strips whitespace."""
        from iatb.ml.feature_engine import _regime_one_hot

        bull_spaces = _regime_one_hot("  BULL  ")
        assert bull_spaces == (Decimal("1"), Decimal("0"), Decimal("0"))


# Scenario 3: Time features normalized to [0,1] range (test utility directly)
class TestScenario03TimeFeatures:
    """Test time feature normalization via _time_features function."""

    def test_time_features_normalization(self) -> None:
        """Test that hour and minute are normalized to [0,1]."""
        from iatb.ml.feature_engine import _time_features

        # Hour 12, minute 30
        stamp = datetime(2024, 1, 1, 12, 30, tzinfo=UTC)
        hour, minute = _time_features(stamp)
        expected_hour = Decimal("12") / Decimal("23")
        expected_minute = Decimal("30") / Decimal("59")
        assert hour == expected_hour
        assert minute == expected_minute

    def test_time_features_boundary_values(self) -> None:
        """Test time features at boundary values."""
        from iatb.ml.feature_engine import _time_features

        # Test hour=0, minute=0
        stamp = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        hour, minute = _time_features(stamp)
        assert hour == Decimal("0")
        assert minute == Decimal("0")

        # Test hour=23, minute=59
        stamp = datetime(2024, 1, 1, 23, 59, tzinfo=UTC)
        hour, minute = _time_features(stamp)
        assert hour == Decimal("23") / Decimal("23")
        assert minute == Decimal("59") / Decimal("59")


# Scenario 4: Edge case - volatility_window=2 (minimum)
class TestScenario04MinVolatilityWindow:
    """Test minimum volatility window."""

    def test_volatility_window_minimum(self) -> None:
        """Test that volatility_window=2 works correctly."""
        engineer = FeatureEngineer(volatility_window=2)
        ohlcv = [
            {
                "open": Decimal("100"),
                "high": Decimal("101"),
                "low": Decimal("99"),
                "close": Decimal("100"),
                "volume": Decimal("1000"),
            },
            {
                "open": Decimal("101"),
                "high": Decimal("102"),
                "low": Decimal("100"),
                "close": Decimal("101"),
                "volume": Decimal("1200"),
            },
            {
                "open": Decimal("100"),
                "high": Decimal("103"),
                "low": Decimal("99"),
                "close": Decimal("102"),
                "volume": Decimal("1100"),
            },
        ]
        sentiments = [Decimal("0.0"), Decimal("0.2"), Decimal("0.1")]
        regimes = ["NEUTRAL", "BULL", "BEAR"]
        stamps = [
            datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 9, 1, tzinfo=UTC),
            datetime(2024, 1, 1, 9, 2, tzinfo=UTC),
        ]

        result = engineer.build_features(ohlcv, sentiments, regimes, stamps)
        assert len(result) == 2
        assert len(result[0]) == 10


# Scenario 5: Edge case - Exactly 2 rows (minimum for returns)
class TestScenario05MinRows:
    """Test exactly 2 rows."""

    def test_exactly_two_rows(self) -> None:
        """Test that exactly 2 rows produces 1 feature vector."""
        engineer = FeatureEngineer()
        ohlcv = [
            {
                "open": Decimal("100"),
                "high": Decimal("101"),
                "low": Decimal("99"),
                "close": Decimal("100"),
                "volume": Decimal("1000"),
            },
            {
                "open": Decimal("101"),
                "high": Decimal("102"),
                "low": Decimal("100"),
                "close": Decimal("101"),
                "volume": Decimal("1200"),
            },
        ]
        sentiments = [Decimal("0.0"), Decimal("0.5")]
        regimes = ["NEUTRAL", "BULL"]
        stamps = [
            datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 12, 1, tzinfo=UTC),
        ]

        result = engineer.build_features(ohlcv, sentiments, regimes, stamps)
        assert len(result) == 1
        assert len(result[0]) == 10


# Scenario 6: Edge case - IQR=0
class TestScenario06ZeroIQR:
    """Test IQR=0 handling."""

    def test_iqr_zero_handling(self) -> None:
        """Test that IQR=0 is handled by replacing divisor with 1."""
        engineer = FeatureEngineer()
        # Create data where all values in a column are the same (IQR=0)
        ohlcv = [
            {
                "open": Decimal("100"),
                "high": Decimal("101"),
                "low": Decimal("99"),
                "close": Decimal("100"),
                "volume": Decimal("1000"),
            },
            {
                "open": Decimal("100"),
                "high": Decimal("101"),
                "low": Decimal("99"),
                "close": Decimal("100"),
                "volume": Decimal("1000"),
            },
            {
                "open": Decimal("100"),
                "high": Decimal("101"),
                "low": Decimal("99"),
                "close": Decimal("100"),
                "volume": Decimal("1000"),
            },
        ]
        sentiments = [Decimal("0.5"), Decimal("0.5"), Decimal("0.5")]
        regimes = ["NEUTRAL", "NEUTRAL", "NEUTRAL"]
        stamps = [
            datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 12, 1, tzinfo=UTC),
            datetime(2024, 1, 1, 12, 2, tzinfo=UTC),
        ]

        # Should not raise an error
        result = engineer.build_features(ohlcv, sentiments, regimes, stamps)
        assert len(result) == 2
        # All values should be valid Decimals
        for row in result:
            for value in row:
                assert isinstance(value, Decimal)


# Scenario 7: Edge case - volume_prev=0
class TestScenario07ZeroVolumePrev:
    """Test volume_prev=0 handling."""

    def test_volume_prev_zero_handling(self) -> None:
        """Test that volume_prev=0 is handled by replacing divisor with 1."""
        engineer = FeatureEngineer()
        ohlcv = [
            {
                "open": Decimal("100"),
                "high": Decimal("101"),
                "low": Decimal("99"),
                "close": Decimal("100"),
                "volume": Decimal("0"),
            },
            {
                "open": Decimal("101"),
                "high": Decimal("102"),
                "low": Decimal("100"),
                "close": Decimal("101"),
                "volume": Decimal("1000"),
            },
        ]
        sentiments = [Decimal("0.0"), Decimal("0.5")]
        regimes = ["NEUTRAL", "BULL"]
        stamps = [
            datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 12, 1, tzinfo=UTC),
        ]

        # Should not raise an error
        result = engineer.build_features(ohlcv, sentiments, regimes, stamps)
        assert len(result) == 1
        assert len(result[0]) == 10
        # Ensure the volume_ratio is a valid Decimal (not inf or NaN)
        assert isinstance(result[0][4], Decimal)


# Scenario 8: Error - volatility_window < 2
class TestScenario08InvalidVolatilityWindow:
    """Test invalid volatility window raises ConfigError."""

    def test_volatility_window_less_than_two(self) -> None:
        """Test that volatility_window < 2 raises ConfigError."""
        with pytest.raises(ConfigError, match="volatility_window must be >= 2"):
            FeatureEngineer(volatility_window=1)

    def test_volatility_window_zero(self) -> None:
        """Test that volatility_window=0 raises ConfigError."""
        with pytest.raises(ConfigError, match="volatility_window must be >= 2"):
            FeatureEngineer(volatility_window=0)

    def test_volatility_window_negative(self) -> None:
        """Test that negative volatility_window raises ConfigError."""
        with pytest.raises(ConfigError, match="volatility_window must be >= 2"):
            FeatureEngineer(volatility_window=-5)


# Scenario 9: Error - Mismatched input lengths
class TestScenario09MismatchedLengths:
    """Test mismatched input lengths raise ConfigError."""

    def test_mismatched_lengths_ohlcv_sentiment(self) -> None:
        """Test mismatched ohlcv and sentiment lengths."""
        engineer = FeatureEngineer()
        ohlcv = [
            {
                "open": Decimal("100"),
                "high": Decimal("101"),
                "low": Decimal("99"),
                "close": Decimal("100"),
                "volume": Decimal("1000"),
            },
            {
                "open": Decimal("101"),
                "high": Decimal("102"),
                "low": Decimal("100"),
                "close": Decimal("101"),
                "volume": Decimal("1200"),
            },
        ]
        sentiments = [Decimal("0.0")]  # Only 1 sentiment for 2 ohlcv rows
        regimes = ["NEUTRAL", "BULL"]
        stamps = [
            datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 12, 1, tzinfo=UTC),
        ]

        with pytest.raises(ConfigError, match="share equal length"):
            engineer.build_features(ohlcv, sentiments, regimes, stamps)

    def test_mismatched_lengths_regime_timestamps(self) -> None:
        """Test mismatched regime and timestamp lengths."""
        engineer = FeatureEngineer()
        ohlcv = [
            {
                "open": Decimal("100"),
                "high": Decimal("101"),
                "low": Decimal("99"),
                "close": Decimal("100"),
                "volume": Decimal("1000"),
            },
            {
                "open": Decimal("101"),
                "high": Decimal("102"),
                "low": Decimal("100"),
                "close": Decimal("101"),
                "volume": Decimal("1200"),
            },
        ]
        sentiments = [Decimal("0.0"), Decimal("0.5")]
        regimes = ["NEUTRAL"]  # Only 1 regime for 2 rows
        stamps = [
            datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 12, 1, tzinfo=UTC),
        ]

        with pytest.raises(ConfigError, match="share equal length"):
            engineer.build_features(ohlcv, sentiments, regimes, stamps)


# Scenario 10: Error - Fewer than 2 rows
class TestScenario10FewerThanTwoRows:
    """Test fewer than 2 rows raises ConfigError."""

    def test_single_row(self) -> None:
        """Test that single row raises ConfigError."""
        engineer = FeatureEngineer()
        ohlcv = [
            {
                "open": Decimal("100"),
                "high": Decimal("101"),
                "low": Decimal("99"),
                "close": Decimal("100"),
                "volume": Decimal("1000"),
            },
        ]
        sentiments = [Decimal("0.0")]
        regimes = ["NEUTRAL"]
        stamps = [datetime(2024, 1, 1, 12, 0, tzinfo=UTC)]

        with pytest.raises(ConfigError, match="at least two rows are required"):
            engineer.build_features(ohlcv, sentiments, regimes, stamps)

    def test_empty_rows(self) -> None:
        """Test that empty rows raises ConfigError."""
        engineer = FeatureEngineer()
        ohlcv: list[dict[str, Decimal]] = []
        sentiments: list[Decimal] = []
        regimes: list[str] = []
        stamps: list[datetime] = []

        with pytest.raises(ConfigError, match="at least two rows are required"):
            engineer.build_features(ohlcv, sentiments, regimes, stamps)


# Scenario 11: Error - Non-UTC timestamps
class TestScenario11NonUTCTimestamps:
    """Test non-UTC timestamps raise ConfigError."""

    def test_naive_datetime(self) -> None:
        """Test that naive datetime raises ConfigError."""
        engineer = FeatureEngineer()
        ohlcv = [
            {
                "open": Decimal("100"),
                "high": Decimal("101"),
                "low": Decimal("99"),
                "close": Decimal("100"),
                "volume": Decimal("1000"),
            },
            {
                "open": Decimal("101"),
                "high": Decimal("102"),
                "low": Decimal("100"),
                "close": Decimal("101"),
                "volume": Decimal("1200"),
            },
        ]
        sentiments = [Decimal("0.0"), Decimal("0.5")]
        regimes = ["NEUTRAL", "BULL"]
        stamps = [
            datetime(2024, 1, 1, 12, 0),  # noqa: DTZ001 Naive datetime for error test
            datetime(2024, 1, 1, 12, 1),  # noqa: DTZ001 Naive datetime for error test
        ]

        with pytest.raises(ConfigError, match="timezone-aware UTC"):
            engineer.build_features(ohlcv, sentiments, regimes, stamps)

    def test_non_utc_timezone(self) -> None:
        """Test that non-UTC timezone raises ConfigError."""
        from datetime import timezone

        engineer = FeatureEngineer()
        ohlcv = [
            {
                "open": Decimal("100"),
                "high": Decimal("101"),
                "low": Decimal("99"),
                "close": Decimal("100"),
                "volume": Decimal("1000"),
            },
            {
                "open": Decimal("101"),
                "high": Decimal("102"),
                "low": Decimal("100"),
                "close": Decimal("101"),
                "volume": Decimal("1200"),
            },
        ]
        sentiments = [Decimal("0.0"), Decimal("0.5")]
        regimes = ["NEUTRAL", "BULL"]
        # Use IST timezone (UTC+5:30)
        ist = timezone(timedelta(hours=5, minutes=30))
        stamps = [
            datetime(2024, 1, 1, 12, 0, tzinfo=ist),
            datetime(2024, 1, 1, 12, 1, tzinfo=ist),
        ]

        with pytest.raises(ConfigError, match="timezone-aware UTC"):
            engineer.build_features(ohlcv, sentiments, regimes, stamps)


# Scenario 12: Error - Missing OHLCV key
class TestScenario12MissingOHLCVKey:
    """Test missing OHLCV key raises ConfigError."""

    def test_missing_close_key(self) -> None:
        """Test that missing 'close' key raises ConfigError."""
        engineer = FeatureEngineer()
        ohlcv = [
            {
                "open": Decimal("100"),
                "high": Decimal("101"),
                "low": Decimal("99"),
                "volume": Decimal("1000"),
            },  # Missing 'close'
            {
                "open": Decimal("101"),
                "high": Decimal("102"),
                "low": Decimal("100"),
                "close": Decimal("101"),
                "volume": Decimal("1200"),
            },
        ]
        sentiments = [Decimal("0.0"), Decimal("0.5")]
        regimes = ["NEUTRAL", "BULL"]
        stamps = [
            datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 12, 1, tzinfo=UTC),
        ]

        with pytest.raises(ConfigError, match="missing OHLCV key: close"):
            engineer.build_features(ohlcv, sentiments, regimes, stamps)

    def test_missing_volume_key(self) -> None:
        """Test that missing 'volume' key raises ConfigError."""
        engineer = FeatureEngineer()
        ohlcv = [
            {
                "open": Decimal("100"),
                "high": Decimal("101"),
                "low": Decimal("99"),
                "close": Decimal("100"),
            },  # Missing 'volume'
            {
                "open": Decimal("101"),
                "high": Decimal("102"),
                "low": Decimal("100"),
                "close": Decimal("101"),
                "volume": Decimal("1200"),
            },
        ]
        sentiments = [Decimal("0.0"), Decimal("0.5")]
        regimes = ["NEUTRAL", "BULL"]
        stamps = [
            datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 12, 1, tzinfo=UTC),
        ]

        with pytest.raises(ConfigError, match="missing OHLCV key: volume"):
            engineer.build_features(ohlcv, sentiments, regimes, stamps)


# Additional: Test utility functions directly
class TestUtilityFunctions:
    """Test utility functions directly."""

    def test_median_odd_length(self) -> None:
        """Test median with odd number of values."""
        from iatb.ml.feature_engine import _median

        values = [Decimal("1"), Decimal("3"), Decimal("2")]
        result = _median(values)
        assert result == Decimal("2")

    def test_median_even_length(self) -> None:
        """Test median with even number of values."""
        from iatb.ml.feature_engine import _median

        values = [Decimal("1"), Decimal("3"), Decimal("2"), Decimal("4")]
        result = _median(values)
        assert result == Decimal("2.5")

    def test_iqr_calculation(self) -> None:
        """Test IQR calculation."""
        from iatb.ml.feature_engine import _iqr

        values = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")]
        result = _iqr(values)
        # Q1 = 2, Q3 = 4, IQR = 4 - 2 = 2
        assert result == Decimal("2")

    def test_mean_calculation(self) -> None:
        """Test mean calculation."""
        from iatb.ml.feature_engine import _mean

        values = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")]
        result = _mean(values)
        assert result == Decimal("3")

    def test_mean_single_value(self) -> None:
        """Test mean with single value."""
        from iatb.ml.feature_engine import _mean

        values = [Decimal("42")]
        result = _mean(values)
        assert result == Decimal("42")


# =============================================================================
# End of test file
# =============================================================================
