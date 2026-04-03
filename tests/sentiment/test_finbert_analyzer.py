from decimal import Decimal
from types import SimpleNamespace

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.finbert_analyzer import FinbertAnalyzer, _default_predictor


def test_finbert_analyzer_parses_positive_prediction() -> None:
    predictor = lambda text: [{"label": "positive", "score": 0.92}]  # noqa: E731
    analyzer = FinbertAnalyzer(predictor=predictor)
    result = analyzer.analyze("Reliance beats estimates in Q4 results.")
    assert result.score == Decimal("0.92")
    assert result.label == "POSITIVE"


def test_finbert_analyzer_parses_negative_prediction() -> None:
    predictor = lambda text: [{"label": "negative", "score": 0.81}]  # noqa: E731
    analyzer = FinbertAnalyzer(predictor=predictor)
    result = analyzer.analyze("Nifty falls after weak global cues.")
    assert result.score == Decimal("-0.81")
    assert result.label == "NEGATIVE"


def test_finbert_analyzer_rejects_empty_prediction() -> None:
    analyzer = FinbertAnalyzer(predictor=lambda text: [])
    with pytest.raises(ConfigError, match="at least one mapping prediction"):
        analyzer.analyze("ICICI posts steady margin growth.")


def test_finbert_default_predictor_missing_dependency_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "iatb.sentiment.finbert_analyzer.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    with pytest.raises(ConfigError, match="transformers dependency"):
        _default_predictor("ProsusAI/finbert")


def test_finbert_analyzer_rejects_empty_text() -> None:
    analyzer = FinbertAnalyzer(predictor=lambda text: [{"label": "positive", "score": 0.8}])
    with pytest.raises(ConfigError, match="text cannot be empty"):
        analyzer.analyze("  ")


def test_finbert_analyzer_maps_neutral_prediction_to_zero_score() -> None:
    analyzer = FinbertAnalyzer(predictor=lambda text: [{"label": "neutral", "score": 0.6}])
    result = analyzer.analyze("Nifty closes flat in low-volume trade.")
    assert result.score == Decimal("0")
    assert result.label == "NEUTRAL"


def test_finbert_default_predictor_pipeline_unavailable_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "iatb.sentiment.finbert_analyzer.importlib.import_module",
        lambda _: SimpleNamespace(),
    )
    with pytest.raises(ConfigError, match="pipeline is unavailable"):
        _default_predictor("ProsusAI/finbert")


def test_finbert_default_predictor_returns_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    def _pipeline(task: str, model: str, tokenizer: str):  # type: ignore[no-untyped-def]
        _ = (task, model, tokenizer)
        return lambda text, truncation: [{"label": "positive", "score": 0.9}]

    monkeypatch.setattr(
        "iatb.sentiment.finbert_analyzer.importlib.import_module",
        lambda _: SimpleNamespace(pipeline=_pipeline),
    )
    predictor = _default_predictor("ProsusAI/finbert")
    assert predictor("RBI hints at growth support.") == [{"label": "positive", "score": 0.9}]
