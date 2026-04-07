from decimal import Decimal
from types import SimpleNamespace

import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.hmm_model import HMMRegimeModel


def test_hmm_model_fit_and_predict_regime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "iatb.ml.hmm_model.importlib.import_module",
        lambda _: SimpleNamespace(GaussianHMM=lambda *args, **kwargs: object()),
    )
    model = HMMRegimeModel()
    observations = [[Decimal("-0.5")], [Decimal("0.0")], [Decimal("0.6")]]
    model.fit(observations)
    assert model.predict_regime([Decimal("-0.4")]) == "BEAR"
    assert model.predict_regime([Decimal("0.0")]) == "SIDEWAYS"
    assert model.predict_regime([Decimal("0.8")]) == "BULL"


def test_hmm_model_validates_inputs_and_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    model = HMMRegimeModel()
    with pytest.raises(ConfigError, match="fitted before predict_regime"):
        model.predict_regime([Decimal("0.1")])
    with pytest.raises(ConfigError, match="cannot be empty"):
        model.fit([])
    with pytest.raises(ConfigError, match="cannot be empty"):
        model.fit([[]])
    monkeypatch.setattr(
        "iatb.ml.hmm_model.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    with pytest.raises(ConfigError, match="hmmlearn dependency"):
        model.initialize()
