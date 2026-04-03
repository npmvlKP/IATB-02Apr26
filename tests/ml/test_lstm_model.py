from decimal import Decimal
from types import SimpleNamespace

import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.lstm_model import LSTMConfig, LSTMModel


def test_lstm_model_train_and_predict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("iatb.ml.lstm_model.importlib.import_module", lambda _: SimpleNamespace())
    model = LSTMModel(LSTMConfig(sequence_length=3))
    sequences = [[Decimal("0.1"), Decimal("0.2"), Decimal("0.3")] for _ in range(4)]
    targets = [Decimal("0.2"), Decimal("0.25"), Decimal("0.3"), Decimal("0.35")]
    mae = model.train(sequences, targets, seed=7)
    prediction = model.predict([Decimal("0.1"), Decimal("0.2"), Decimal("0.3")])
    assert mae >= Decimal("0")
    assert prediction.confidence <= Decimal("1")


def test_lstm_model_validates_state_and_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    model = LSTMModel(LSTMConfig(sequence_length=3))
    with pytest.raises(ConfigError, match="trained before predict"):
        model.predict([Decimal("0.1"), Decimal("0.2"), Decimal("0.3")])
    with pytest.raises(ConfigError, match="cannot be empty"):
        model.train([], [], seed=1)
    with pytest.raises(ConfigError, match="equal length"):
        model.train(
            [[Decimal("0.1"), Decimal("0.2"), Decimal("0.3")]],
            [Decimal("0.2"), Decimal("0.3")],
            seed=1,
        )
    with pytest.raises(ConfigError, match="sequence_length"):
        model.train([[Decimal("0.1")]], [Decimal("0.1")], seed=1)
    monkeypatch.setattr(
        "iatb.ml.lstm_model.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    with pytest.raises(ConfigError, match="torch dependency"):
        model.initialize()
