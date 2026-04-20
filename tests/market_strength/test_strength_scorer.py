import random
from decimal import Decimal

import iatb.market_strength.strength_scorer as strength_module
import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs, StrengthScorer

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def _base_inputs() -> StrengthInputs:
    return StrengthInputs(
        breadth_ratio=Decimal("1.8"),
        regime=MarketRegime.BULL,
        adx=Decimal("30"),
        volume_ratio=Decimal("1.7"),
        volatility_atr_pct=Decimal("0.025"),
    )


def test_strength_scorer_marks_bullish_setup_as_tradable() -> None:
    scorer = StrengthScorer()
    inputs = _base_inputs()
    assert scorer.is_tradable(Exchange.NSE, inputs)
    assert scorer.score(Exchange.NSE, inputs) >= Decimal("0.60")


def test_strength_scorer_blocks_bearish_regime() -> None:
    scorer = StrengthScorer()
    inputs = _base_inputs()
    inputs = StrengthInputs(**{**inputs.__dict__, "regime": MarketRegime.BEAR})
    assert not scorer.is_tradable(Exchange.NSE, inputs)


def test_strength_scorer_blocks_high_volatility() -> None:
    scorer = StrengthScorer()
    inputs = _base_inputs()
    inputs = StrengthInputs(**{**inputs.__dict__, "volatility_atr_pct": Decimal("0.081")})
    assert not scorer.is_tradable(Exchange.NSE, inputs)


@pytest.mark.parametrize(
    "field_name",
    ["breadth_ratio", "adx", "volume_ratio", "volatility_atr_pct"],
)
def test_strength_scorer_rejects_negative_inputs(field_name: str) -> None:
    scorer = StrengthScorer()
    payload = _base_inputs().__dict__.copy()
    payload[field_name] = Decimal("-1")
    with pytest.raises(ConfigError, match="cannot be negative"):
        scorer.score(Exchange.NSE, StrengthInputs(**payload))


def test_strength_scorer_rejects_unsupported_exchange_type() -> None:
    scorer = StrengthScorer()
    with pytest.raises(ConfigError, match="Unsupported exchange"):
        scorer.score("FAKE", _base_inputs())  # type: ignore[arg-type]


def test_strength_scorer_rejects_exchange_not_in_threshold_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scorer = StrengthScorer()
    monkeypatch.delitem(strength_module._EXCHANGE_MIN_SCORE, Exchange.NSE, raising=False)
    with pytest.raises(ConfigError, match="Unsupported exchange"):
        scorer.score(Exchange.NSE, _base_inputs())


def test_strength_scorer_helper_branches() -> None:
    scorer = StrengthScorer(cache_enabled=True)
    assert scorer._normalize(Decimal("2"), cap=Decimal("0")) == Decimal("0")
    assert scorer._regime_score(MarketRegime.SIDEWAYS) == Decimal("0.55")
    assert scorer._regime_score(MarketRegime.BEAR) == Decimal("0.15")
    assert StrengthScorer._volatility_penalty(Decimal("0.02")) == Decimal("0")
    assert StrengthScorer._volatility_penalty(Decimal("0.04")) == Decimal("0.05")
    assert StrengthScorer._volatility_penalty(Decimal("0.07")) == Decimal("0.12")
    assert StrengthScorer._volatility_penalty(Decimal("0.10")) == Decimal("0.20")
