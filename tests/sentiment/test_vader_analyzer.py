import random
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.sentiment.vader_analyzer import VaderAnalyzer, _default_factory

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class _FakeVader:
    def __init__(self, compound: Decimal) -> None:
        self._compound = compound

    def polarity_scores(self, text: str) -> dict[str, object]:
        _ = text
        return {"compound": str(self._compound)}


def test_vader_analyzer_maps_positive_compound() -> None:
    analyzer = VaderAnalyzer(analyzer_factory=lambda: _FakeVader(Decimal("0.64")))
    result = analyzer.analyze("Indian markets surge after policy reform optimism.")
    assert result.label == "POSITIVE"
    assert result.score == Decimal("0.64")


def test_vader_analyzer_maps_negative_compound() -> None:
    analyzer = VaderAnalyzer(analyzer_factory=lambda: _FakeVader(Decimal("-0.72")))
    result = analyzer.analyze("Midcaps tumble as risk-off sentiment intensifies.")
    assert result.label == "NEGATIVE"
    assert result.score == Decimal("-0.72")


def test_vader_analyzer_rejects_non_mapping_payload() -> None:
    class _BadVader:
        def polarity_scores(self, text: str) -> object:
            _ = text
            return []

    analyzer = VaderAnalyzer(analyzer_factory=lambda: _BadVader())
    with pytest.raises(ConfigError, match="must return mapping"):
        analyzer.analyze("Energy stocks stay flat.")


def test_vader_default_factory_missing_dependency_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "iatb.sentiment.vader_analyzer.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    with pytest.raises(ConfigError, match="vadersentiment dependency"):
        _default_factory()


def test_vader_analyzer_rejects_empty_text() -> None:
    analyzer = VaderAnalyzer(analyzer_factory=lambda: _FakeVader(Decimal("0.1")))
    with pytest.raises(ConfigError, match="text cannot be empty"):
        analyzer.analyze("   ")


def test_vader_default_factory_missing_analyzer_class_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "iatb.sentiment.vader_analyzer.importlib.import_module",
        lambda _: SimpleNamespace(),
    )
    with pytest.raises(ConfigError, match="SentimentIntensityAnalyzer not found"):
        _default_factory()


def test_vader_default_factory_returns_analyzer_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Analyzer:
        def polarity_scores(self, text: str) -> dict[str, object]:
            _ = text
            return {"compound": "0.2"}

    module = SimpleNamespace(SentimentIntensityAnalyzer=lambda: _Analyzer())
    monkeypatch.setattr(
        "iatb.sentiment.vader_analyzer.importlib.import_module",
        lambda _: module,
    )
    analyzer = _default_factory()
    assert analyzer.polarity_scores("NSE volumes improve.") == {"compound": "0.2"}
