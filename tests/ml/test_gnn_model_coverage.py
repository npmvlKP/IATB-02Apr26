"""Coverage tests for iatb.ml.gnn_model - GNNModel and helpers."""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
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
            _validate_graph_inputs(
                [[Decimal("1")], [Decimal("2")]], [(0, 1)], [Decimal("1")]
            )

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
