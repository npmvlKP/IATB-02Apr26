"""Coverage tests for iatb.ml.transformer_model - TransformerModel and helpers."""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.transformer_model import (
    TransformerConfig,
    TransformerModel,
    _attention_proxy,
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
