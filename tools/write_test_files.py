"""Helper script to write all ML and backtesting test coverage files with proper newlines."""
import os

FILES = {}

FILES["tests/ml/test_trainer_coverage.py"] = r'''"""Coverage tests for iatb.ml.trainer - UnifiedTrainer and helpers."""
from decimal import Decimal
from unittest.mock import MagicMock
import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.trainer import (
    TrainingRunResult,
    UnifiedTrainer,
    _evaluate_model,
    _extract_score,
    _fit_model,
    _log_mlflow,
    _validate_dataset,
)


class TestValidateDataset:
    def test_empty_features_raises(self) -> None:
        with pytest.raises(ConfigError, match="train features"):
            _validate_dataset([], [Decimal("1")], "train")

    def test_empty_targets_raises(self) -> None:
        with pytest.raises(ConfigError, match="train features"):
            _validate_dataset([[Decimal("1")]], [], "train")

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ConfigError, match="equal length"):
            _validate_dataset(
                [[Decimal("1")], [Decimal("2")]], [Decimal("1")], "train"
            )

    def test_empty_feature_row_raises(self) -> None:
        with pytest.raises(ConfigError, match="feature rows cannot be empty"):
            _validate_dataset(
                [[Decimal("1")], []], [Decimal("1"), Decimal("2")], "train"
            )

    def test_valid_dataset_passes(self) -> None:
        _validate_dataset(
            [[Decimal("1")], [Decimal("2")]],
            [Decimal("1"), Decimal("2")],
            "validation",
        )


class TestExtractScore:
    def test_decimal_passthrough(self) -> None:
        assert _extract_score(Decimal("0.5")) == Decimal("0.5")

    def test_object_with_score_attribute(self) -> None:
        obj = MagicMock()
        obj.score = Decimal("0.75")
        assert _extract_score(obj) == Decimal("0.75")

    def test_invalid_result_raises(self) -> None:
        with pytest.raises(ConfigError, match="Decimal or expose Decimal score"):
            _extract_score("invalid")


class TestEvaluateModel:
    def test_computes_mae_correctly(self) -> None:
        model = MagicMock()
        model.predict.side_effect = [Decimal("10"), Decimal("20")]
        features = [[Decimal("1")], [Decimal("2")]]
        targets = [Decimal("12"), Decimal("18")]
        mae = _evaluate_model(model, features, targets)
        expected = (Decimal("2") + Decimal("2")) / Decimal("2")
        assert mae == expected


class TestFitModel:
    def test_train_method_returns_decimal(self) -> None:
        model = MagicMock()
        model.train.return_value = Decimal("0.15")
        result = _fit_model(model, [[Decimal("1")]], [Decimal("1")])
        assert result == Decimal("0.15")

    def test_no_train_or_fit_raises(self) -> None:
        model = MagicMock(spec=["predict"])
        model.predict.return_value = Decimal("1")
        with pytest.raises(ConfigError, match=r"train\(\) or fit\(\)"):
            _fit_model(model, [[Decimal("1")]], [Decimal("1")])


class TestLogMlflow:
    def test_tracking_disabled_returns_placeholder(self) -> None:
        result = _log_mlflow("exp", Decimal("0.1"), Decimal("0.2"), False)
        assert result == "tracking-disabled"


class TestUnifiedTrainer:
    def test_init_defaults(self) -> None:
        trainer = UnifiedTrainer(enable_tracking=False)
        assert trainer._experiment_name == "iatb_ml"
        assert trainer._enable_tracking is False

    def test_train_and_evaluate_empty_train_raises(self) -> None:
        trainer = UnifiedTrainer(enable_tracking=False)
        with pytest.raises(ConfigError, match="train features"):
            trainer.train_and_evaluate(
                MagicMock(), [], [Decimal("1")], [[Decimal("1")]], [Decimal("1")]
            )


class TestTrainingRunResult:
    def test_creation(self) -> None:
        result = TrainingRunResult(
            train_mae=Decimal("0.1"),
            validation_mae=Decimal("0.2"),
            experiment_name="test",
            run_id="run-123",
        )
        assert result.train_mae == Decimal("0.1")
'''

FILES["tests/ml/test_predictor_coverage.py"] = r'''"""Coverage tests for iatb.ml.predictor - EnsemblePredictor and helpers."""
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

    def test_single_predictor(self, mock_predictor: object, sample_features: list[Decimal]) -> None:
        ensemble = EnsemblePredictor([mock_predictor])
        result = ensemble.predict(sample_features)
        assert isinstance(result, PredictionResult)
        assert result.symbol == "RELIANCE"

    def test_multiple_predictors(self, sample_features: list[Decimal]) -> None:
        p1 = MagicMock()
        p1.predict.return_value = PredictionResult("A", Decimal("0.6"), Decimal("0.7"), "BULL")
        p2 = MagicMock()
        p2.predict.return_value = PredictionResult("A", Decimal("0.4"), Decimal("0.5"), "BEAR")
        ensemble = EnsemblePredictor([p1, p2])
        result = ensemble.predict(sample_features)
        assert isinstance(result.score, Decimal)
        assert isinstance(result.confidence, Decimal)
        assert result.regime_label in {"BULL", "BEAR"}

    def test_custom_weights(self, sample_features: list[Decimal]) -> None:
        p1 = MagicMock()
        p1.predict.return_value = PredictionResult("A", Decimal("1"), Decimal("1"), "BULL")
        p2 = MagicMock()
        p2.predict.return_value = PredictionResult("A", Decimal("0"), Decimal("0"), "BEAR")
        ensemble = EnsemblePredictor([p1, p2], weights=[Decimal("3"), Decimal("1")])
        result = ensemble.predict(sample_features)
        assert result.score == Decimal("0.75")

    def test_weighted_confidence_clamped(self) -> None:
        p1 = MagicMock()
        p1.predict.return_value = PredictionResult("A", Decimal("0"), Decimal("1.5"), "BULL")
        ensemble = EnsemblePredictor([p1])
        result = ensemble.predict([Decimal("1")])
        assert result.confidence <= Decimal("1")
'''

FILES["tests/ml/test_hmm_model_coverage.py"] = r'''"""Coverage tests for iatb.ml.hmm_model - HMMRegimeModel and helpers."""
from decimal import Decimal
from unittest.mock import MagicMock
import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.hmm_model import (
    HMMConfig,
    HMMRegimeModel,
    _nearest_state,
    _state_label,
    _validate_observations,
)


class TestHMMConfig:
    def test_defaults(self) -> None:
        config = HMMConfig()
        assert config.n_components == 3

    def test_custom_n_components(self) -> None:
        config = HMMConfig(n_components=5)
        assert config.n_components == 5


class TestNearestState:
    def test_first_centroid(self) -> None:
        centroids = (Decimal("-1"), Decimal("0"), Decimal("1"))
        assert _nearest_state(Decimal("-0.9"), centroids) == 0

    def test_second_centroid(self) -> None:
        centroids = (Decimal("-1"), Decimal("0"), Decimal("1"))
        assert _nearest_state(Decimal("0.1"), centroids) == 1

    def test_third_centroid(self) -> None:
        centroids = (Decimal("-1"), Decimal("0"), Decimal("1"))
        assert _nearest_state(Decimal("0.9"), centroids) == 2

    def test_exact_centroid_match(self) -> None:
        centroids = (Decimal("-1"), Decimal("0"), Decimal("1"))
        assert _nearest_state(Decimal("0"), centroids) == 1


class TestStateLabel:
    def test_state_zero_is_bear(self) -> None:
        assert _state_label(0) == "BEAR"

    def test_state_one_is_sideways(self) -> None:
        assert _state_label(1) == "SIDEWAYS"

    def test_state_two_is_bull(self) -> None:
        assert _state_label(2) == "BULL"

    def test_state_three_is_bull(self) -> None:
        assert _state_label(3) == "BULL"


class TestValidateObservations:
    def test_empty_observations_raises(self) -> None:
        with pytest.raises(ConfigError, match="observations cannot be empty"):
            _validate_observations([])

    def test_empty_row_raises(self) -> None:
        with pytest.raises(ConfigError, match="observation rows cannot be empty"):
            _validate_observations([[Decimal("1")], []])

    def test_valid_observations_pass(self) -> None:
        _validate_observations([[Decimal("1"), Decimal("2")]])


class TestHMMRegimeModel:
    def test_init_defaults(self) -> None:
        model = HMMRegimeModel()
        assert model._config.n_components == 3
        assert model._initialized is False
        assert model._fitted is False

    def test_predict_regime_before_fit_raises(self) -> None:
        model = HMMRegimeModel()
        model._fitted = False
        with pytest.raises(ConfigError, match="fitted before predict_regime"):
            model.predict_regime([Decimal("1")])

    def test_predict_regime_empty_features_raises(self) -> None:
        model = HMMRegimeModel()
        model._fitted = True
        with pytest.raises(ConfigError, match="features cannot be empty"):
            model.predict_regime([])

    def test_predict_regime_returns_valid_label(self) -> None:
        model = HMMRegimeModel()
        model._fitted = True
        model._centroids = (Decimal("-1"), Decimal("0"), Decimal("1"))
        label = model.predict_regime([Decimal("0.5")])
        assert label in {"BEAR", "SIDEWAYS", "BULL"}

    def test_predict_regime_bear_label(self) -> None:
        model = HMMRegimeModel()
        model._fitted = True
        model._centroids = (Decimal("-10"), Decimal("0"), Decimal("10"))
        label = model.predict_regime([Decimal("-9")])
        assert label == "BEAR"

    def test_predict_regime_bull_label(self) -> None:
        model = HMMRegimeModel()
        model._fitted = True
        model._centroids = (Decimal("-10"), Decimal("0"), Decimal("10"))
        label = model.predict_regime([Decimal("9")])
        assert label == "BULL"

    def test_load_hmmlearn_missing_raises(self) -> None:
        import iatb.ml.hmm_model as hmm_mod
        original = hmm_mod.importlib.import_module
        def _fake_import(name: str) -> object:
            raise ModuleNotFoundError(name)
        hmm_mod.importlib.import_module = _fake_import
        try:
            with pytest.raises(ConfigError, match="hmmlearn dependency"):
                hmm_mod._load_hmmlearn()
        finally:
            hmm_mod.importlib.import_module = original
'''

FILES["tests/ml/test_gnn_model_coverage.py"] = r'''"""Coverage tests for iatb.ml.gnn_model - GNNModel and helpers."""
from decimal import Decimal
from unittest.mock import MagicMock
import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.base import PredictionResult
from iatb.ml.gnn_model import (
    GNNConfig,
    GNNModel,
    _mae,
    _mean,
    _validate_graph_inputs,
)


class TestGNNConfig:
    def test_defaults(self) -> None:
        config = GNNConfig()
        assert config.hidden_channels == 32
        assert config.num_layers == 2

    def test_custom_config(self) -> None:
        config = GNNConfig(hidden_channels=64, num_layers=3)
        assert config.hidden_channels == 64


class TestMean:
    def test_basic_average(self) -> None:
        assert _mean([Decimal("10"), Decimal("20")]) == Decimal("15")

    def test_single_value(self) -> None:
        assert _mean([Decimal("5")]) == Decimal("5")


class TestMae:
    def test_zero_error(self) -> None:
        assert _mae([Decimal("5")], [Decimal("5")]) == Decimal("0")

    def test_nonzero_error(self) -> None:
        result = _mae([Decimal("3"), Decimal("7")], [Decimal("5"), Decimal("5")])
        assert result == Decimal("2")


class TestValidateGraphInputs:
    def test_empty_node_features_raises(self) -> None:
        with pytest.raises(ConfigError, match="node_features and targets"):
            _validate_graph_inputs([], [(0, 1)], [Decimal("1")])

    def test_empty_targets_raises(self) -> None:
        with pytest.raises(ConfigError, match="node_features and targets"):
            _validate_graph_inputs([[Decimal("1")]], [(0, 1)], [])

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ConfigError, match="equal length"):
            _validate_graph_inputs([[Decimal("1")], [Decimal("2")]], [(0, 1)], [Decimal("1")])

    def test_empty_edge_index_raises(self) -> None:
        with pytest.raises(ConfigError, match="edge_index cannot be empty"):
            _validate_graph_inputs([[Decimal("1")]], [], [Decimal("1")])

    def test_valid_inputs_pass(self) -> None:
        _validate_graph_inputs([[Decimal("1")]], [(0, 1)], [Decimal("1")])


class TestGNNModel:
    def test_init_defaults(self) -> None:
        model = GNNModel()
        assert model._initialized is False
        assert model._trained is False

    def test_predict_before_train_raises(self) -> None:
        model = GNNModel()
        with pytest.raises(ConfigError, match="trained before predict"):
            model.predict([Decimal("1")])

    def test_fit_empty_node_features_raises(self) -> None:
        model = GNNModel()
        with pytest.raises(ConfigError, match="node_features and targets"):
            model.fit([], [(0, 1)], [])

    def test_load_torch_geometric_missing_raises(self) -> None:
        import iatb.ml.gnn_model as gnn_mod
        original = gnn_mod.importlib.import_module
        def _fake_import(name: str) -> object:
            raise ModuleNotFoundError(name)
        gnn_mod.importlib.import_module = _fake_import
        try:
            with pytest.raises(ConfigError, match="torch-geometric dependency"):
                gnn_mod._load_torch_geometric()
        finally:
            gnn_mod.importlib.import_module = original
'''

FILES["tests/ml/test_transformer_model_coverage.py"] = r'''"""Coverage tests for iatb.ml.transformer_model - TransformerModel and helpers."""
from decimal import Decimal
from unittest.mock import MagicMock
import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.base import PredictionResult
from iatb.ml.transformer_model import (
    TransformerConfig,
    TransformerModel,
    _attention_proxy,
    _mae,
    _mean,
    _validate_inputs,
)


class TestTransformerConfig:
    def test_defaults(self) -> None:
        config = TransformerConfig()
        assert config.d_model == 64
        assert config.nhead == 4
        assert config.num_layers == 2

    def test_custom_config(self) -> None:
        config = TransformerConfig(d_model=128, nhead=8, num_layers=4)
        assert config.d_model == 128


class TestAttentionProxy:
    def test_single_feature(self) -> None:
        result = _attention_proxy([Decimal("10")])
        assert result == Decimal("10")

    def test_weighted_position(self) -> None:
        result = _attention_proxy([Decimal("1"), Decimal("1")])
        expected = (Decimal("1") + Decimal("2")) / Decimal("2")
        assert result == expected


class TestValidateInputs:
    def test_empty_feature_sequences_raises(self) -> None:
        with pytest.raises(ConfigError, match="feature_sequences and targets"):
            _validate_inputs([], [Decimal("1")])

    def test_empty_targets_raises(self) -> None:
        with pytest.raises(ConfigError, match="feature_sequences and targets"):
            _validate_inputs([[Decimal("1")]], [])

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ConfigError, match="equal length"):
            _validate_inputs([[Decimal("1")], [Decimal("2")]], [Decimal("1")])

    def test_empty_feature_sequence_row_raises(self) -> None:
        with pytest.raises(ConfigError, match="feature sequences cannot contain empty"):
            _validate_inputs([[Decimal("1")], []], [Decimal("1"), Decimal("2")])

    def test_valid_inputs_pass(self) -> None:
        _validate_inputs([[Decimal("1")], [Decimal("2")]], [Decimal("1"), Decimal("2")])


class TestTransformerModel:
    def test_init_defaults(self) -> None:
        model = TransformerModel()
        assert model._initialized is False
        assert model._trained is False
        assert model._scale == Decimal("1")
        assert model._offset == Decimal("0")

    def test_predict_before_train_raises(self) -> None:
        model = TransformerModel()
        with pytest.raises(ConfigError, match="trained before predict"):
            model.predict([Decimal("1")])

    def test_train_empty_sequences_raises(self) -> None:
        model = TransformerModel()
        with pytest.raises(ConfigError, match="feature_sequences and targets"):
            model.train([], [])

    def test_train_length_mismatch_raises(self) -> None:
        model = TransformerModel()
        with pytest.raises(ConfigError, match="equal length"):
            model.train([[Decimal("1")]], [Decimal("1"), Decimal("2")])

    def test_load_torch_missing_raises(self) -> None:
        import iatb.ml.transformer_model as tf_mod
        original = tf_mod.importlib.import_module
        def _fake_import(name: str) -> object:
            raise ModuleNotFoundError(name)
        tf_mod.importlib.import_module = _fake_import
        try:
            with pytest.raises(ConfigError, match="torch dependency"):
                tf_mod._load_torch()
        finally:
            tf_mod.importlib.import_module = original
'''

FILES["tests/ml/test_lstm_model_coverage.py"] = r'''"""Coverage tests for iatb.ml.lstm_model - LSTMModel and helpers."""
from decimal import Decimal
from unittest.mock import MagicMock
import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.base import PredictionResult
from iatb.ml.lstm_model import (
    LSTMConfig,
    LSTMModel,
    _mae,
    _mean,
    _validate_training_inputs,
)


class TestLSTMConfig:
    def test_defaults(self) -> None:
        config = LSTMConfig()
        assert config.sequence_length == 60
        assert config.hidden_size == 128
        assert config.num_layers == 2
        assert config.dropout == Decimal("0.3")

    def test_custom_config(self) -> None:
        config = LSTMConfig(sequence_length=30, hidden_size=64, num_layers=1, dropout=Decimal("0.1"))
        assert config.sequence_length == 30


class TestValidateTrainingInputs:
    def test_empty_sequences_raises(self) -> None:
        with pytest.raises(ConfigError, match="sequences and targets cannot be empty"):
            _validate_training_inputs([], [Decimal("1")], 60)

    def test_empty_targets_raises(self) -> None:
        with pytest.raises(ConfigError, match="sequences and targets cannot be empty"):
            _validate_training_inputs([[Decimal("1")] * 60], [], 60)

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ConfigError, match="equal length"):
            _validate_training_inputs([[Decimal("1")] * 60], [Decimal("1"), Decimal("2")], 60)

    def test_wrong_sequence_length_raises(self) -> None:
        with pytest.raises(ConfigError, match="match configured sequence_length"):
            _validate_training_inputs([[Decimal("1")] * 30], [Decimal("1")], 60)

    def test_valid_inputs_pass(self) -> None:
        _validate_training_inputs([[Decimal("1")] * 60], [Decimal("1")], 60)


class TestLSTMModel:
    def test_init_defaults(self) -> None:
        model = LSTMModel()
        assert model._initialized is False
        assert model._trained is False
        assert model._weight == Decimal("0")
        assert model._bias == Decimal("0")

    def test_predict_before_train_raises(self) -> None:
        model = LSTMModel()
        with pytest.raises(ConfigError, match="trained before predict"):
            model.predict([Decimal("1")])

    def test_train_empty_sequences_raises(self) -> None:
        model = LSTMModel()
        with pytest.raises(ConfigError, match="sequences and targets"):
            model.train([], [])

    def test_load_torch_missing_raises(self) -> None:
        import iatb.ml.lstm_model as lstm_mod
        original = lstm_mod.importlib.import_module
        def _fake_import(name: str) -> object:
            raise ModuleNotFoundError(name)
        lstm_mod.importlib.import_module = _fake_import
        try:
            with pytest.raises(ConfigError, match="torch dependency"):
                lstm_mod._load_torch()
        finally:
            lstm_mod.importlib.import_module = original
'''

FILES["tests/ml/test_model_registry_coverage.py"] = r'''"""Coverage tests for iatb.ml.model_registry - ModelRegistry and helpers."""
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
            model_name="test", status=ModelStatus.AVAILABLE, last_check=datetime.now(UTC)
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

    def test_check_pytorch_availability_import_error(self) -> None:
        registry = ModelRegistry()
        with patch(
            "iatb.ml.model_registry.importlib.import_module",
            side_effect=ImportError("no torch"),
        ):
            status = registry.check_pytorch_availability()
            assert status == ModelStatus.UNAVAILABLE

    def test_check_vader_availability_success(self) -> None:
        registry = ModelRegistry()
        mock_module = MagicMock()
        mock_analyzer = MagicMock()
        mock_analyzer.polarity_scores.return_value = {"compound": 0.5}
        mock_module.SentimentIntensityAnalyzer = MagicMock(return_value=mock_analyzer)
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
        health = registry._create_health_result(model_name="test", status=ModelStatus.AVAILABLE)
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
'''

FILES["tests/ml/test_tracking_coverage.py"] = r'''"""Coverage tests for iatb.ml.tracking - ExperimentTracker, HyperparameterOptimizer."""
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.tracking import (
    ExperimentMetrics,
    ExperimentTracker,
    HyperparameterOptimizer,
    MLflowConfig,
    OptunaConfig,
    create_default_optimizer,
    create_default_tracking,
)


class TestMLflowConfig:
    def test_defaults(self) -> None:
        config = MLflowConfig()
        assert config.tracking_uri == "file:///mlruns"
        assert config.experiment_name == "iatb-experiments"
        assert config.enable_tracking is True

    def test_custom_config(self) -> None:
        config = MLflowConfig(tracking_uri="http://localhost:5000", enable_tracking=False)
        assert config.tracking_uri == "http://localhost:5000"


class TestOptunaConfig:
    def test_defaults(self) -> None:
        config = OptunaConfig()
        assert config.n_trials == 100
        assert config.direction == "maximize"


class TestExperimentMetrics:
    def test_defaults(self) -> None:
        metrics = ExperimentMetrics()
        assert metrics.sharpe_ratio is None
        assert metrics.custom_metrics == {}

    def test_with_values(self) -> None:
        metrics = ExperimentMetrics(sharpe_ratio=Decimal("1.5"), num_trades=100)
        assert metrics.sharpe_ratio == Decimal("1.5")


class TestExperimentTracker:
    def test_init_disabled_tracking(self) -> None:
        config = MLflowConfig(enable_tracking=False)
        tracker = ExperimentTracker(config=config)
        assert tracker.config.enable_tracking is False

    def test_start_run_disabled(self) -> None:
        config = MLflowConfig(enable_tracking=False)
        tracker = ExperimentTracker(config=config)
        tracker.start_run(run_name="test")
        assert tracker.active_run is None

    def test_log_params_disabled(self) -> None:
        config = MLflowConfig(enable_tracking=False)
        tracker = ExperimentTracker(config=config)
        tracker.log_params({"lr": Decimal("0.01")})

    def test_log_metrics_disabled(self) -> None:
        config = MLflowConfig(enable_tracking=False)
        tracker = ExperimentTracker(config=config)
        tracker.log_metrics(ExperimentMetrics())

    def test_end_run_disabled(self) -> None:
        config = MLflowConfig(enable_tracking=False)
        tracker = ExperimentTracker(config=config)
        tracker.end_run()

    def test_start_run_enabled(self) -> None:
        with patch("iatb.ml.tracking.mlflow") as mock_mlflow:
            mock_run = MagicMock()
            mock_run.info.run_id = "test-run"
            mock_mlflow.start_run.return_value = mock_run
            config = MLflowConfig(enable_tracking=True)
            tracker = ExperimentTracker(config=config)
            tracker.start_run(run_name="test")
            assert tracker.active_run is not None

    def test_setup_mlflow_failure_raises(self) -> None:
        with patch("iatb.ml.tracking.mlflow") as mock_mlflow:
            mock_mlflow.set_tracking_uri.side_effect = Exception("conn fail")
            config = MLflowConfig(enable_tracking=True)
            with pytest.raises(ConfigError, match="Failed to setup MLflow"):
                ExperimentTracker(config=config)


class TestHyperparameterOptimizer:
    def test_invalid_direction_raises(self) -> None:
        config = OptunaConfig(direction="invalid")
        with pytest.raises(ConfigError, match="Invalid direction"):
            HyperparameterOptimizer(config=config)

    def test_get_best_params_no_study_raises(self) -> None:
        with patch("iatb.ml.tracking.optuna"):
            opt = HyperparameterOptimizer()
            opt.study = None
            with pytest.raises(ConfigError, match="Study has not been created"):
                opt.get_best_params()

    def test_get_best_params_success(self) -> None:
        with patch("iatb.ml.tracking.optuna"):
            opt = HyperparameterOptimizer()
            mock_study = MagicMock()
            mock_study.trials = [MagicMock()]
            mock_study.best_params = {"lr": 0.01}
            opt.study = mock_study
            result = opt.get_best_params()
            assert result == {"lr": 0.01}


class TestCreateDefaultTracking:
    def test_defaults(self) -> None:
        with patch("iatb.ml.tracking.mlflow"):
            tracker = create_default_tracking()
            assert isinstance(tracker, ExperimentTracker)
'''

FILES["tests/backtesting/test_session_masks_coverage.py"] = r'''"""Coverage tests for iatb.backtesting.session_masks - session masking functions."""
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
            result = is_in_session(datetime(2026, 1, 5, 10, 0, tzinfo=UTC), Exchange.NSE)
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
                datetime(2026, 1, 5, 10, 0, tzinfo=UTC), Exchange.NSE, "BONDS"
            )
            assert result is False


class TestValidateTradeProduct:
    def test_unsupported_exchange_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unsupported session exchange"):
            validate_trade_product(datetime.now(UTC), Exchange.BINANCE, "STOCKS", "MIS")


class TestGetMisSessionWindow:
    def test_unsupported_exchange_returns_none(self) -> None:
        result = get_mis_session_window(Exchange.BSE, date(2026, 1, 5))
        assert result is None

    def test_unsupported_exchange_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unsupported session exchange"):
            get_mis_session_window(Exchange.BINANCE, date(2026, 1, 5))


class TestCreateMisSessionMask:
    def test_unsupported_exchange_returns_empty(self) -> None:
        result = create_mis_session_mask(Exchange.BSE, date(2026, 1, 5), date(2026, 1, 9))
        assert result == []

    def test_unsupported_exchange_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unsupported session exchange"):
            create_mis_session_mask(Exchange.BINANCE, date(2026, 1, 5), date(2026, 1, 9))

    def test_returns_valid_dates(self) -> None:
        with patch("iatb.backtesting.session_masks.get_mis_session_window") as mock_window:
            mock_window.return_value = (time(9, 15), time(15, 0))
            result = create_mis_session_mask(Exchange.NSE, date(2026, 1, 5), date(2026, 1, 7))
            assert len(result) == 3


class TestMisRequiredAssets:
    def test_contains_stocks(self) -> None:
        assert "STOCKS" in MIS_REQUIRED_ASSETS

    def test_contains_options(self) -> None:
        assert "OPTIONS" in MIS_REQUIRED_ASSETS
'''

FILES["tests/backtesting/test_vectorbt_engine_coverage.py"] = r'''"""Coverage tests for iatb.backtesting.vectorbt_engine - VectorBTEngine and dataclasses."""
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.backtesting.vectorbt_engine import (
    BacktestResult,
    MonteCarloResult,
    VectorBTConfig,
    VectorBTEngine,
    WalkForwardResult,
)


class TestVectorBTConfig:
    def test_defaults(self) -> None:
        config = VectorBTConfig()
        assert config.exchange == Exchange.NSE
        assert config.initial_capital == Decimal("100000")

    def test_zero_capital_raises(self) -> None:
        with pytest.raises(ConfigError, match="initial_capital must be positive"):
            VectorBTConfig(initial_capital=Decimal("0"))

    def test_negative_capital_raises(self) -> None:
        with pytest.raises(ConfigError, match="initial_capital must be positive"):
            VectorBTConfig(initial_capital=Decimal("-100"))

    def test_negative_slippage_raises(self) -> None:
        with pytest.raises(ConfigError, match="slippage_pct cannot be negative"):
            VectorBTConfig(slippage_pct=Decimal("-0.1"))

    def test_negative_commission_raises(self) -> None:
        with pytest.raises(ConfigError, match="commission_pct cannot be negative"):
            VectorBTConfig(commission_pct=Decimal("-0.1"))

    def test_composite_score_below_zero_raises(self) -> None:
        with pytest.raises(ConfigError, match="min_composite_score"):
            VectorBTConfig(min_composite_score=Decimal("-0.1"))

    def test_composite_score_above_one_raises(self) -> None:
        with pytest.raises(ConfigError, match="min_composite_score"):
            VectorBTConfig(min_composite_score=Decimal("1.1"))

    def test_zero_simulations_raises(self) -> None:
        with pytest.raises(ConfigError, match="num_simulations must be positive"):
            VectorBTConfig(num_simulations=0)

    def test_valid_boundary_values(self) -> None:
        config = VectorBTConfig(min_composite_score=Decimal("0"), min_exit_probability=Decimal("1"))
        assert config.min_composite_score == Decimal("0")


class TestVectorBTEngineLoaders:
    def test_load_vectorbt_missing_raises(self) -> None:
        with patch(
            "iatb.backtesting.vectorbt_engine.importlib.import_module",
            side_effect=ModuleNotFoundError,
        ):
            with pytest.raises(ConfigError, match="vectorbt dependency"):
                VectorBTEngine._load_vectorbt()

    def test_load_pandas_ta_missing_raises(self) -> None:
        with patch(
            "iatb.backtesting.vectorbt_engine.importlib.import_module",
            side_effect=ModuleNotFoundError,
        ):
            with pytest.raises(ConfigError, match="pandas-ta-classic"):
                VectorBTEngine._load_pandas_ta()


class TestBacktestResult:
    def test_creation(self) -> None:
        result = BacktestResult(
            total_return=Decimal("0.1"),
            cagr=Decimal("0.08"),
            sharpe_ratio=Decimal("1.5"),
            max_drawdown=Decimal("-0.05"),
            win_rate=Decimal("0.6"),
            profit_factor=Decimal("1.8"),
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            avg_win=Decimal("500"),
            avg_loss=Decimal("-300"),
            total_costs=Decimal("100"),
            stt_total=Decimal("30"),
            sebi_total=Decimal("5"),
            exchange_txn_total=Decimal("10"),
            stamp_duty_total=Decimal("3"),
            gst_total=Decimal("2"),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            num_days=90,
            avg_composite_score=Decimal("0.7"),
            avg_exit_probability=Decimal("0.6"),
        )
        assert result.total_return == Decimal("0.1")


class TestMonteCarloResult:
    def test_creation(self) -> None:
        result = MonteCarloResult(
            mean_final_equity=Decimal("110000"),
            median_final_equity=Decimal("105000"),
            std_final_equity=Decimal("5000"),
            prob_profit=Decimal("0.7"),
            prob_5pct_return=Decimal("0.4"),
            prob_10pct_return=Decimal("0.2"),
            worst_case_equity=Decimal("90000"),
            best_case_equity=Decimal("130000"),
            p5_equity=Decimal("95000"),
            p25_equity=Decimal("100000"),
            p75_equity=Decimal("115000"),
            p95_equity=Decimal("125000"),
        )
        assert result.prob_profit == Decimal("0.7")
'''

FILES["tests/backtesting/test_walk_forward_coverage.py"] = r'''"""Coverage tests for iatb.backtesting.walk_forward - WalkForwardValidator and helpers."""
from datetime import UTC, datetime
from decimal import Decimal
import pytest
from iatb.core.exceptions import ConfigError
from iatb.backtesting.walk_forward import (
    WalkForwardConfig,
    WalkForwardValidator,
    _calculate_train_size,
    _validate_window_inputs,
    _validate_window_scores,
)


class TestWalkForwardConfig:
    def test_defaults(self) -> None:
        config = WalkForwardConfig()
        assert config.train_pct == Decimal("0.7")
        assert config.num_folds == 5

    def test_zero_train_pct_raises(self) -> None:
        with pytest.raises(ConfigError, match="train_pct must be between 0 and 1"):
            WalkForwardConfig(train_pct=Decimal("0"))

    def test_one_train_pct_raises(self) -> None:
        with pytest.raises(ConfigError, match="train_pct must be between 0 and 1"):
            WalkForwardConfig(train_pct=Decimal("1"))

    def test_zero_folds_raises(self) -> None:
        with pytest.raises(ConfigError, match="num_folds must be positive"):
            WalkForwardConfig(num_folds=0)


class TestValidateWindowInputs:
    def test_empty_prices_raises(self) -> None:
        with pytest.raises(ConfigError, match="at least 10 data points"):
            _validate_window_inputs([Decimal("1")] * 5, [datetime.now(UTC)] * 5)

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ConfigError, match="same length"):
            _validate_window_inputs([Decimal("1")] * 10, [datetime.now(UTC)] * 5)

    def test_valid_inputs_pass(self) -> None:
        _validate_window_inputs([Decimal("1")] * 15, [datetime.now(UTC)] * 15)


class TestValidateWindowScores:
    def test_empty_scores_raises(self) -> None:
        with pytest.raises(ConfigError, match="composite_scores cannot be empty"):
            _validate_window_scores([Decimal("1")] * 10, [])

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ConfigError, match="composite_scores must match"):
            _validate_window_scores([Decimal("1")] * 10, [Decimal("0.5")] * 5)


class TestCalculateTrainSize:
    def test_valid_calculation(self) -> None:
        result = _calculate_train_size(15, Decimal("0.7"))
        assert result == 10

    def test_custom_pct(self) -> None:
        result = _calculate_train_size(20, Decimal("0.8"))
        assert result == 16


class TestWalkForwardValidator:
    def test_init_defaults(self) -> None:
        validator = WalkForwardValidator()
        assert validator._config.train_pct == Decimal("0.7")

    def test_validate_too_few_prices_raises(self) -> None:
        validator = WalkForwardValidator()
        with pytest.raises(ConfigError, match="at least 10 data points"):
            validator.validate([Decimal("1")] * 5, [datetime.now(UTC)] * 5)

    def test_validate_length_mismatch_raises(self) -> None:
        validator = WalkForwardValidator()
        with pytest.raises(ConfigError, match="same length"):
            validator.validate([Decimal("1")] * 10, [datetime.now(UTC)] * 5)

    def test_validate_success_returns_results(self) -> None:
        config = WalkForwardConfig(train_pct=Decimal("0.7"), num_folds=2)
        validator = WalkForwardValidator(config=config)
        prices = [Decimal(str(100 + i)) for i in range(20)]
        timestamps = [datetime(2026, 1, 1, 10, i, tzinfo=UTC) for i in range(20)]
        result = validator.validate(prices, timestamps)
        assert len(result) == 2
        for fold in result:
            assert "train_start" in fold
            assert "train_pct" in fold
            assert fold["train_pct"] == Decimal("0.7")

    def test_validate_single_fold(self) -> None:
        config = WalkForwardConfig(train_pct=Decimal("0.7"), num_folds=1)
        validator = WalkForwardValidator(config=config)
        prices = [Decimal(str(100 + i)) for i in range(15)]
        timestamps = [datetime(2026, 1, 1, 10, i, tzinfo=UTC) for i in range(15)]
        result = validator.validate(prices, timestamps)
        assert len(result) == 1
        assert result[0]["fold"] == 1
'''


def main() -> None:
    for filepath, content in FILES.items():
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8", newline="\n") as f:
            f.write(content.lstrip("\n"))
        line_count = len(content.lstrip("\n").splitlines())
        print(f"Written: {filepath} ({line_count} lines)")


if __name__ == "__main__":
    main()
