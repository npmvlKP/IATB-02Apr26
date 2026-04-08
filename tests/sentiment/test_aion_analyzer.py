import random
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.sentiment.aion_analyzer import AionAnalyzer, _resolve_predict_fn

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_aion_analyzer_accepts_mapping_output() -> None:
    analyzer = AionAnalyzer(predict_fn=lambda text: {"label": "positive", "score": 0.88})
    result = analyzer.analyze("RBI keeps rates steady; banks rally.")
    assert result.score == Decimal("0.88")
    assert result.label == "POSITIVE"


def test_aion_analyzer_accepts_tuple_output() -> None:
    analyzer = AionAnalyzer(predict_fn=lambda text: ("negative", 0.75))
    result = analyzer.analyze("Rupee weakens and import costs climb.")
    assert result.score == Decimal("-0.75")
    assert result.label == "NEGATIVE"


def test_aion_analyzer_rejects_unknown_output() -> None:
    analyzer = AionAnalyzer(predict_fn=lambda text: object())
    with pytest.raises(ConfigError, match="Unsupported AION prediction output format"):
        analyzer.analyze("IT stocks mixed after earnings updates.")


def test_aion_analyzer_rejects_negative_confidence() -> None:
    analyzer = AionAnalyzer(predict_fn=lambda text: {"label": "positive", "score": -0.1})
    with pytest.raises(ConfigError, match="cannot be negative"):
        analyzer.analyze("Sensex opens higher.")


def test_aion_predictor_missing_dependency_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "iatb.sentiment.aion_analyzer.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    with pytest.raises(ConfigError, match="aion-sentiment dependency"):
        _resolve_predict_fn()


def test_aion_analyzer_rejects_empty_text() -> None:
    analyzer = AionAnalyzer(predict_fn=lambda text: {"label": "neutral", "score": 0.6})
    with pytest.raises(ConfigError, match="text cannot be empty"):
        analyzer.analyze("   ")


def test_aion_analyzer_handles_neutral_string_prediction() -> None:
    analyzer = AionAnalyzer(predict_fn=lambda text: "neutral")
    result = analyzer.analyze("Market breadth stays mixed in late session.")
    assert result.score == Decimal("0")
    assert result.label == "NEUTRAL"


def test_aion_resolve_predict_fn_from_module_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    module = SimpleNamespace(predict=lambda text: {"label": "positive", "score": 0.8})
    monkeypatch.setattr(
        "iatb.sentiment.aion_analyzer.importlib.import_module",
        lambda _: module,
    )
    predict_fn = _resolve_predict_fn()
    assert predict_fn("Rupee remains stable.") == {"label": "positive", "score": 0.8}


def test_aion_resolve_predict_fn_from_model_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Model:
        def analyze(self, text: str) -> dict[str, object]:
            _ = text
            return {"label": "bearish", "score": 0.7}

    module = SimpleNamespace(AionSentiment=lambda: _Model())
    monkeypatch.setattr(
        "iatb.sentiment.aion_analyzer.importlib.import_module",
        lambda _: module,
    )
    predict_fn = _resolve_predict_fn()
    assert predict_fn("IT index weakens intraday.") == {"label": "bearish", "score": 0.7}


def test_aion_resolve_predict_fn_without_interface_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "iatb.sentiment.aion_analyzer.importlib.import_module",
        lambda _: SimpleNamespace(),
    )
    with pytest.raises(ConfigError, match="usable prediction interface"):
        _resolve_predict_fn()
