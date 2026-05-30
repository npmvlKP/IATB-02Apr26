"""Coverage tests for iatb.ml.lstm_model - LSTMModel and helpers."""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.lstm_model import (
    LSTMConfig,
    LSTMModel,
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
        config = LSTMConfig(
            sequence_length=30, hidden_size=64, num_layers=1, dropout=Decimal("0.1")
        )
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
            _validate_training_inputs(
                [[Decimal("1")] * 60], [Decimal("1"), Decimal("2")], 60
            )

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
