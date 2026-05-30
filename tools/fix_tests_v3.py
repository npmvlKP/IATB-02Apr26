"""Write fixed test files with proper newlines."""
import os

def write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    lc = len(content.splitlines())
    print(f"Written: {path} ({lc} lines)")


# 1. test_predictor_coverage.py
write_file("tests/ml/test_predictor_coverage.py", '''\
"""Coverage tests for iatb.ml.predictor - EnsemblePredictor and helpers."""
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from iatb.core.exceptions import ConfigError
from iatb.ml.base import PredictionResult
from iatb.ml.predictor import (
    EnsemblePredictor,
    _clamp_01,
    _normalize_weights,
    _regime_vote,
    _weighted_average,
)


class TestNormalizeWeights:
    def test_none_returns_uniform_weights(self) -> None:
        result = _normalize_weights(None, 3)
        assert result == [Decimal("1"), Decimal("1"), Decimal("1")]

    def test_valid_weights_returned(self) -> None:
        result = _normalize_weights([Decimal("2"), Decimal("3")], 2)
        assert result == [Decimal("2"), Decimal("3")]

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ConfigError, match="weights must match"):
            _normalize_weights([Decimal("1")], 2)

    def test_zero_weight_raises(self) -> None:
        with pytest.raises(ConfigError, match="weights must be positive"):
            _normalize_weights([Decimal("1"), Decimal("0")], 2)

    def test_negative_weight_raises(self) -> None:
        with pytest.raises(ConfigError, match="weights must be positive"):
            _normalize_weights([Decimal("1"), Decimal("-1")], 2)


class TestWeightedAverage:
    def test_uniform_weights(self) -> None:
        values = [Decimal("10"), Decimal("20")]
        weights = [Decimal("1"), Decimal("1")]
        result = _weighted_average(values, weights)
        assert result == Decimal("15")

    def test_custom_weights(self) -> None:
        values = [Decimal("10"), Decimal("20")]
        weights = [Decimal("3"), Decimal("1")]
        result = _weighted_average(values, weights)
        expected = (Decimal("30") + Decimal("20")) / Decimal("4")
        assert result == expected


class TestRegimeVote:
    def test_majority_vote(self) -> None:
        predictions = [
            PredictionResult("A", Decimal("0"), Decimal("0.5"), "BULL"),
            PredictionResult("A", Decimal("0"), Decimal("0.5"), "BULL"),
            PredictionResult("A", Decimal("0"), Decimal("0.5"), "BEAR"),
        ]
        result = _regime_vote(predictions, [Decimal("1")] * 3)
        assert result == "BULL"

    def test_weighted_vote(self) -> None:
        predictions = [
            PredictionResult("A", Decimal("0"), Decimal("0.5"), "BEAR"),
            PredictionResult("A", Decimal("0"), Decimal("0.5"), "BULL"),
        ]
        weights = [Decimal("3"), Decimal("1")]
        result = _regime_vote(predictions, weights)
        assert result == "BEAR"


class TestClamp01:
    def test_value_within_range(self) -> None:
        assert _clamp_01(Decimal("0.5")) == Decimal("0.5")

    def test_value_below_zero_clamped(self) -> None:
        assert _clamp_01(Decimal("-0.5")) == Decimal("0")

    def test_value_above_one_clamped(self) -> None:
        assert _clamp_01(Decimal("1.5")) == Decimal("1")

    def test_exact_zero(self) -> None:
        assert _clamp_01(Decimal("0")) == Decimal("0")

    def test_exact_one(self) -> None:
        assert _clamp_01(Decimal("1")) == Decimal("1")


class TestEnsemblePredictor:
    def test_empty_predictors_raises(self) -> None:
        with pytest.raises(ConfigError, match="predictors cannot be empty"):
            EnsemblePredictor([])

    def test_single_predictor(
        self, mock_predictor: object, sample_features: list[Decimal],
    ) -> None:
        ensemble = EnsemblePredictor([mock_predictor])
        result = ensemble.predict(sample_features)
        assert isinstance(result, PredictionResult)
        assert result.symbol == "RELIANCE"

    def test_multiple_predictors(
        self, sample_features: list[Decimal],
    ) -> None:
        p1 = MagicMock()
        p1.predict.return_value = PredictionResult(
            "A", Decimal("0.6"), Decimal("0.7"), "BULL",
        )
        p2 = MagicMock()
        p2.predict.return_value = PredictionResult(
            "A", Decimal("0.4"), Decimal("0.5"), "BEAR",
        )
        ensemble = EnsemblePredictor([p1, p2])
        result = ensemble.predict(sample_features)
        assert isinstance(result.score, Decimal)
        assert isinstance(result.confidence, Decimal)
        assert result.regime_label in {"BULL", "BEAR"}

    def test_custom_weights(
        self, sample_features: list[Decimal],
    ) -> None:
        p1 = MagicMock()
        p1.predict.return_value = PredictionResult(
            "A", Decimal("1"), Decimal("1"), "BULL",
        )
        p2 = MagicMock()
        p2.predict.return_value = PredictionResult(
            "A", Decimal("0"), Decimal("0"), "BEAR",
        )
        ensemble = EnsemblePredictor(
            [p1, p2], weights=[Decimal("3"), Decimal("1")],
        )
        result = ensemble.predict(sample_features)
        assert result.score == Decimal("0.75")

    def test_confidence_clamped_at_boundary(self) -> None:
        p1 = MagicMock()
        p1.predict.return_value = PredictionResult(
            "A", Decimal("0"), Decimal("1"), "BULL",
        )
        ensemble = EnsemblePredictor([p1])
        result = ensemble.predict([Decimal("1")])
        assert result.confidence == Decimal("1")
''')

# 2. test_model_registry_coverage.py
write_file("tests/ml/test_model_registry_coverage.py", '''\
"""Coverage tests for iatb.ml.model_registry - ModelRegistry and helpers."""
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from iatb.core.exceptions import ConfigError
from iatb.ml.model_registry import (
    ModelHealth,
    ModelRegistry,
    ModelStatus,
    RegistryStatus,
    get_registry,
)


class TestModelStatus:
    def test_available_value(self) -> None:
        assert ModelStatus.AVAILABLE.value == "available"

    def test_unavailable_value(self) -> None:
        assert ModelStatus.UNAVAILABLE.value == "unavailable"

    def test_degraded_value(self) -> None:
        assert ModelStatus.DEGRADED.value == "degraded"

    def test_error_value(self) -> None:
        assert ModelStatus.ERROR.value == "error"


class TestModelHealth:
    def test_creation_with_defaults(self) -> None:
        health = ModelHealth(
            model_name="test",
            status=ModelStatus.AVAILABLE,
            last_check=datetime.now(UTC),
        )
        assert health.error_message is None
        assert health.dll_loaded is True
        assert health.fallback_available is False

    def test_creation_with_all_fields(self) -> None:
        health = ModelHealth(
            model_name="finbert",
            status=ModelStatus.ERROR,
            last_check=datetime.now(UTC),
            error_message="DLL missing",
            load_time_ms=Decimal("1500"),
            dll_loaded=False,
            fallback_available=True,
        )
        assert health.error_message == "DLL missing"
        assert health.dll_loaded is False


class TestRegistryStatus:
    def test_creation(self) -> None:
        status = RegistryStatus(
            timestamp=datetime.now(UTC),
            total_models=3,
            available_models=1,
            degraded_models=0,
            unavailable_models=2,
            model_health={},
        )
        assert status.total_models == 3


class TestModelRegistry:
    def test_init(self) -> None:
        registry = ModelRegistry()
        assert registry._initialized is False
        assert registry._health == {}

    def test_check_pytorch_availability_error(self) -> None:
        registry = ModelRegistry()
        with patch.dict("sys.modules", {"torch": None}):
            status = registry.check_pytorch_availability()
            assert status in (ModelStatus.UNAVAILABLE, ModelStatus.ERROR)

    def test_check_vader_availability_success(self) -> None:
        registry = ModelRegistry()
        mock_module = MagicMock()
        mock_analyzer = MagicMock()
        mock_analyzer.polarity_scores.return_value = {"compound": 0.5}
        mock_module.SentimentIntensityAnalyzer = MagicMock(
            return_value=mock_analyzer,
        )
        with patch(
            "iatb.ml.model_registry.importlib.import_module",
            return_value=mock_module,
        ):
            health = registry.check_vader_availability()
            assert health.model_name == "vader"
            assert health.status == ModelStatus.AVAILABLE

    def test_check_finbert_transformers_unavailable(self) -> None:
        registry = ModelRegistry()
        with patch.dict("sys.modules", {"transformers": None}):
            health = registry.check_finbert_availability()
            assert health.status == ModelStatus.UNAVAILABLE
            assert health.fallback_available is True

    def test_create_health_result(self) -> None:
        registry = ModelRegistry()
        health = registry._create_health_result(
            model_name="test", status=ModelStatus.AVAILABLE,
        )
        assert health.model_name == "test"
        assert health.status == ModelStatus.AVAILABLE

    def test_is_model_available_initialized(self) -> None:
        registry = ModelRegistry()
        registry._initialized = True
        registry._health = {
            "finbert": ModelHealth(
                model_name="finbert",
                status=ModelStatus.AVAILABLE,
                last_check=datetime.now(UTC),
            ),
        }
        assert registry.is_model_available("finbert") is True
        assert registry.is_model_available("nonexistent") is False

    def test_get_fallback_chain(self) -> None:
        registry = ModelRegistry()
        assert registry.get_fallback_chain("finbert") == ["vader"]
        assert registry.get_fallback_chain("vader") == []


class TestGetRegistry:
    def test_returns_existing(self) -> None:
        import iatb.ml.model_registry as mod
        existing = ModelRegistry()
        original = mod._registry
        mod._registry = existing
        try:
            assert get_registry() is existing
        finally:
            mod._registry = original
''')

# 3. test_session_masks_coverage.py
write_file("tests/backtesting/test_session_masks_coverage.py", '''\
"""Coverage tests for iatb.backtesting.session_masks - session masking functions."""
from datetime import UTC, date, datetime, time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
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
                datetime(2026, 1, 5, 10, 0, tzinfo=UTC), Exchange.NSE,
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
                datetime(2026, 1, 5, 10, 0, tzinfo=UTC), Exchange.NSE, "BONDS",
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
            Exchange.BSE, date(2026, 1, 5), date(2026, 1, 9),
        )
        assert len(result) > 0
        assert all(isinstance(d, date) for d in result)

    def test_unsupported_exchange_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unsupported session exchange"):
            create_mis_session_mask(
                Exchange.BINANCE, date(2026, 1, 5), date(2026, 1, 9),
            )

    def test_returns_valid_dates(self) -> None:
        with patch(
            "iatb.backtesting.session_masks.get_mis_session_window",
        ) as mock_window:
            mock_window.return_value = (time(9, 15), time(15, 0))
            result = create_mis_session_mask(
                Exchange.NSE, date(2026, 1, 5), date(2026, 1, 7),
            )
            assert len(result) == 3


class TestMisRequiredAssets:
    def test_contains_stocks(self) -> None:
        assert "STOCKS" in MIS_REQUIRED_ASSETS

    def test_contains_options(self) -> None:
        assert "OPTIONS" in MIS_REQUIRED_ASSETS
''')

# 4. test_walk_forward_coverage.py
write_file("tests/backtesting/test_walk_forward_coverage.py", '''\
"""Coverage tests for iatb.backtesting.walk_forward - WalkForwardOptimizer and helpers."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from iatb.core.exceptions import ConfigError
from iatb.backtesting.walk_forward import (
    WalkForwardFold,
    WalkForwardOptimizer,
    WalkForwardResult,
    _default_sharpe_scorer,
    _overfit_ratio,
    _time_series_splits,
)


class TestWalkForwardFold:
    def test_creation(self) -> None:
        fold = WalkForwardFold(
            fold_index=1,
            in_sample_sharpe=Decimal("1.5"),
            out_sample_sharpe=Decimal("1.0"),
            overfit_ratio=Decimal("1.5"),
            overfit_flag=False,
        )
        assert fold.fold_index == 1
        assert fold.in_sample_sharpe == Decimal("1.5")
        assert fold.overfit_flag is False


class TestWalkForwardResult:
    def test_creation(self) -> None:
        fold = WalkForwardFold(
            fold_index=1,
            in_sample_sharpe=Decimal("1"),
            out_sample_sharpe=Decimal("0.5"),
            overfit_ratio=Decimal("2"),
            overfit_flag=True,
        )
        result = WalkForwardResult(
            folds=[fold],
            overfitting_detected=True,
            sampler_name="TPESampler",
        )
        assert result.overfitting_detected is True
        assert result.sampler_name == "TPESampler"


class TestDefaultSharpeScorer:
    def test_empty_returns_zero(self) -> None:
        assert _default_sharpe_scorer([]) == Decimal("0")

    def test_single_returns_zero(self) -> None:
        assert _default_sharpe_scorer([Decimal("5")]) == Decimal("0")

    def test_constant_returns_zero(self) -> None:
        assert _default_sharpe_scorer([Decimal("5"), Decimal("5")]) == Decimal("0")

    def test_varying_returns_nonzero(self) -> None:
        result = _default_sharpe_scorer([Decimal("1"), Decimal("2")])
        assert isinstance(result, Decimal)


class TestOverfitRatio:
    def test_zero_out_sample(self) -> None:
        result = _overfit_ratio(Decimal("1"), Decimal("0"))
        assert result == Decimal("1") / Decimal("0.0001")

    def test_normal_ratio(self) -> None:
        result = _overfit_ratio(Decimal("2"), Decimal("1"))
        assert result == Decimal("2")


class TestTimeSeriesSplits:
    def test_too_short_raises(self) -> None:
        with pytest.raises(ConfigError, match="returns length too short"):
            _time_series_splits([Decimal("1")] * 3, 5)

    def test_valid_splits(self) -> None:
        splits = _time_series_splits(
            [Decimal(str(i)) for i in range(12)], 3,
        )
        assert len(splits) == 3
        for in_s, out_s in splits:
            assert len(in_s) > 0
            assert len(out_s) > 0


class TestWalkForwardOptimizer:
    def test_init_defaults(self) -> None:
        opt = WalkForwardOptimizer()
        assert opt._n_splits == 5

    def test_init_n_splits_lt_2_raises(self) -> None:
        with pytest.raises(ConfigError, match="n_splits must be >= 2"):
            WalkForwardOptimizer(n_splits=1)

    def test_run_insufficient_returns_raises(self) -> None:
        opt = WalkForwardOptimizer(n_splits=2)
        with pytest.raises(ConfigError, match="returns length insufficient"):
            opt.run([Decimal("1"), Decimal("2")])

    def test_run_success(self) -> None:
        with patch(
            "iatb.backtesting.walk_forward._initialize_tpe_sampler",
            return_value="TPESampler",
        ):
            opt = WalkForwardOptimizer(n_splits=2)
            returns = [Decimal(str(i % 10)) for i in range(20)]
            result = opt.run(returns)
            assert isinstance(result, WalkForwardResult)
            assert len(result.folds) == 2
            assert result.sampler_name == "TPESampler"

    def test_run_overfitting_detected(self) -> None:
        with patch(
            "iatb.backtesting.walk_forward._initialize_tpe_sampler",
            return_value="TPESampler",
        ):
            opt = WalkForwardOptimizer(n_splits=2)
            returns = [Decimal(str(i % 5)) for i in range(20)]
            result = opt.run(returns)
            assert isinstance(result.overfitting_detected, bool)


class TestInitializeTpeSampler:
    def test_optuna_missing_raises(self) -> None:
        with patch.dict("sys.modules", {"optuna": None}):
            from iatb.backtesting.walk_forward import _initialize_tpe_sampler
            with pytest.raises(ConfigError, match="optuna dependency"):
                _initialize_tpe_sampler()
''')

print("All 4 fixed test files written successfully.")