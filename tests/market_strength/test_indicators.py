from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.market_strength.indicators import PandasTaIndicators, _last_decimal, _to_decimal


class _FakeTaBackend:
    @staticmethod
    def rsi(**kwargs: object) -> list[float]:
        _ = kwargs
        return [45.0, 55.5]

    @staticmethod
    def adx(**kwargs: object) -> dict[str, list[float]]:
        _ = kwargs
        return {"ADX_14": [18.0, 25.0]}

    @staticmethod
    def atr(**kwargs: object) -> list[float]:
        _ = kwargs
        return [1.2, 1.4]

    @staticmethod
    def macd(**kwargs: object) -> dict[str, list[float]]:
        _ = kwargs
        return {"MACDh_12_26_9": [-0.1, 0.2]}

    @staticmethod
    def bbands(**kwargs: object) -> dict[str, list[float]]:
        _ = kwargs
        return {
            "BBU_20_2.0": [120.0],
            "BBM_20_2.0": [110.0],
            "BBL_20_2.0": [100.0],
        }


def test_indicator_snapshot_uses_backend_outputs() -> None:
    wrapper = PandasTaIndicators(backend_loader=lambda: _FakeTaBackend())
    snapshot = wrapper.snapshot(
        close=[Decimal("100"), Decimal("101"), Decimal("102")],
        high=[Decimal("102"), Decimal("103"), Decimal("104")],
        low=[Decimal("99"), Decimal("100"), Decimal("101")],
    )
    assert snapshot.rsi == Decimal("55.5")
    assert snapshot.adx == Decimal("25.0")
    assert snapshot.macd_histogram == Decimal("0.2")


def test_indicator_snapshot_mismatched_lengths_fails() -> None:
    wrapper = PandasTaIndicators(backend_loader=lambda: _FakeTaBackend())
    with pytest.raises(ConfigError, match="must have equal length"):
        wrapper.snapshot(
            close=[Decimal("100")],
            high=[Decimal("101"), Decimal("102")],
            low=[Decimal("99")],
        )


def test_indicator_snapshot_empty_sequences_fail() -> None:
    wrapper = PandasTaIndicators(backend_loader=lambda: _FakeTaBackend())
    with pytest.raises(ConfigError, match="cannot be empty"):
        wrapper.snapshot(close=[], high=[], low=[])


def test_indicator_snapshot_backend_missing_function_fails() -> None:
    class _BadBackend:
        pass

    wrapper = PandasTaIndicators(backend_loader=lambda: _BadBackend())
    with pytest.raises(ConfigError, match="missing function: rsi"):
        wrapper.snapshot(
            close=[Decimal("1")],
            high=[Decimal("1")],
            low=[Decimal("1")],
        )


def test_indicator_snapshot_missing_named_columns_fail() -> None:
    class _MissingColumnBackend(_FakeTaBackend):
        @staticmethod
        def adx(**kwargs: object) -> dict[str, list[float]]:
            _ = kwargs
            return {"WRONG": [1.0]}

    wrapper = PandasTaIndicators(backend_loader=lambda: _MissingColumnBackend())
    with pytest.raises(ConfigError, match="missing column: ADX_14"):
        wrapper.snapshot(
            close=[Decimal("1"), Decimal("2")],
            high=[Decimal("1"), Decimal("2")],
            low=[Decimal("1"), Decimal("2")],
        )


def test_to_decimal_helper_validation_branches() -> None:
    with pytest.raises(ConfigError, match="cannot be None"):
        _to_decimal(None, "field")
    with pytest.raises(ConfigError, match="decimal-compatible"):
        _to_decimal(object(), "field")


def test_last_decimal_helper_validation_branches() -> None:
    with pytest.raises(ConfigError, match="empty sequence"):
        _last_decimal([], "series")
    with pytest.raises(ConfigError, match="unsupported output type"):
        _last_decimal(123, "series")


def test_default_backend_loader_missing_dependency_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "iatb.market_strength.indicators.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    with pytest.raises(ConfigError, match="pandas-ta dependency"):
        PandasTaIndicators()


def test_extract_named_with_getitem_payload_error_paths() -> None:
    class _IndexingPayload:
        def __getitem__(self, key: str) -> object:
            _ = key
            raise KeyError("missing")

    with pytest.raises(ConfigError, match="missing column"):
        PandasTaIndicators._extract_named(_IndexingPayload(), "COL")
    with pytest.raises(ConfigError, match="must support named column access"):
        PandasTaIndicators._extract_named(object(), "COL")


def test_indicator_snapshot_non_finite_output_fails() -> None:
    class _NonFiniteBackend(_FakeTaBackend):
        @staticmethod
        def rsi(**kwargs: object) -> list[str]:
            _ = kwargs
            return ["NaN"]

    wrapper = PandasTaIndicators(backend_loader=lambda: _NonFiniteBackend())
    with pytest.raises(ConfigError, match="must be finite"):
        wrapper.snapshot(
            close=[Decimal("1"), Decimal("2")],
            high=[Decimal("1"), Decimal("2")],
            low=[Decimal("1"), Decimal("2")],
        )
