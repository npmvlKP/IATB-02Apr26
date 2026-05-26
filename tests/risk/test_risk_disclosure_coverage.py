"""Comprehensive coverage tests for iatb.risk.risk_disclosure."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from iatb.core.exceptions import ConfigError
from iatb.risk.risk_disclosure import (
    PositionLimitDisclosure,
    RiskDisclosureConfig,
    RiskDisclosureGenerator,
    _validate_utc,
)


def _make_config(**overrides: object) -> RiskDisclosureConfig:
    defaults = {
        "system_name": "IATB-Test",
        "system_version": "0.1.0",
        "algo_id": "ALGO-001",
        "retention_years": 7,
        "output_dir": Path("docs/disclosures"),
    }
    defaults.update(overrides)
    return RiskDisclosureConfig(**defaults)


def _make_generator(**config_overrides: object) -> RiskDisclosureGenerator:
    return RiskDisclosureGenerator(_make_config(**config_overrides))


_NOW = datetime(2026, 5, 25, 10, 0, tzinfo=UTC)


class TestRiskDisclosureConfig:
    def test_valid_config(self) -> None:
        cfg = _make_config()
        assert cfg.system_name == "IATB-Test"
        assert cfg.retention_years == 7

    def test_empty_system_name_raises(self) -> None:
        with pytest.raises(ConfigError, match="system_name"):
            _make_config(system_name="  ")

    def test_zero_retention_years_raises(self) -> None:
        with pytest.raises(ConfigError, match="retention_years"):
            _make_config(retention_years=0)

    def test_negative_retention_years_raises(self) -> None:
        with pytest.raises(ConfigError, match="retention_years"):
            _make_config(retention_years=-1)

    def test_frozen(self) -> None:
        cfg = _make_config()
        with pytest.raises(AttributeError):
            cfg.system_name = "other"


class TestPositionLimitDisclosure:
    def test_fields(self) -> None:
        pld = PositionLimitDisclosure(
            exchange="NSE", max_quantity=Decimal("100"), max_notional=Decimal("1000000")
        )
        assert pld.exchange == "NSE"
        assert pld.max_quantity == Decimal("100")

    def test_frozen(self) -> None:
        pld = PositionLimitDisclosure(
            exchange="NSE", max_quantity=Decimal("100"), max_notional=Decimal("1000000")
        )
        with pytest.raises(AttributeError):
            pld.exchange = "BSE"


class TestRiskDisclosureGeneratorInit:
    def test_valid_init(self) -> None:
        gen = _make_generator()
        assert gen._config.algo_id == "ALGO-001"

    def test_empty_algo_id_raises(self) -> None:
        with pytest.raises(ConfigError, match="algo_id"):
            _make_generator(algo_id="  ")

    def test_default_risk_controls(self) -> None:
        gen = _make_generator()
        assert len(gen._risk_controls) > 0


class TestAddRiskControl:
    def test_add_valid_control(self) -> None:
        gen = _make_generator()
        initial = len(gen._risk_controls)
        gen.add_risk_control("Custom risk control")
        assert len(gen._risk_controls) == initial + 1

    def test_add_empty_control_raises(self) -> None:
        gen = _make_generator()
        with pytest.raises(ConfigError, match="risk control"):
            gen.add_risk_control("  ")


class TestAddPositionLimit:
    def test_add_valid_limit(self) -> None:
        gen = _make_generator()
        gen.add_position_limit("NSE", Decimal("100"), Decimal("1000000"))
        assert len(gen._position_limits) == 1

    def test_empty_exchange_raises(self) -> None:
        gen = _make_generator()
        with pytest.raises(ConfigError, match="exchange"):
            gen.add_position_limit("  ", Decimal("100"), Decimal("1000000"))

    def test_zero_max_quantity_raises(self) -> None:
        gen = _make_generator()
        with pytest.raises(ConfigError, match="max_quantity"):
            gen.add_position_limit("NSE", Decimal("0"), Decimal("1000000"))

    def test_negative_max_quantity_raises(self) -> None:
        gen = _make_generator()
        with pytest.raises(ConfigError, match="max_quantity"):
            gen.add_position_limit("NSE", Decimal("-1"), Decimal("1000000"))

    def test_zero_max_notional_raises(self) -> None:
        gen = _make_generator()
        with pytest.raises(ConfigError, match="max_notional"):
            gen.add_position_limit("NSE", Decimal("100"), Decimal("0"))

    def test_negative_max_notional_raises(self) -> None:
        gen = _make_generator()
        with pytest.raises(ConfigError, match="max_notional"):
            gen.add_position_limit("NSE", Decimal("100"), Decimal("-1"))


class TestGenerateText:
    def test_generates_text(self) -> None:
        gen = _make_generator()
        result = gen.generate_text(_NOW)
        assert "ALGORITHMIC TRADING RISK DISCLOSURE" in result
        assert "ALGO-001" in result
        assert "IATB-Test" in result

    def test_includes_controls(self) -> None:
        gen = _make_generator()
        result = gen.generate_text(_NOW)
        assert "Circuit breaker" in result

    def test_includes_retention_years(self) -> None:
        gen = _make_generator()
        result = gen.generate_text(_NOW)
        assert "7 years" in result

    def test_includes_position_limits_when_present(self) -> None:
        gen = _make_generator()
        gen.add_position_limit("NSE", Decimal("100"), Decimal("500000"))
        result = gen.generate_text(_NOW)
        assert "NSE" in result
        assert "Max Qty=100" in result

    def test_default_position_limits_text(self) -> None:
        gen = _make_generator()
        result = gen.generate_text(_NOW)
        assert "SEBI defaults" in result

    def test_naive_datetime_raises(self) -> None:
        gen = _make_generator()
        with pytest.raises(ConfigError, match="UTC"):
            gen.generate_text(datetime(2026, 5, 25, 10, 0))


class TestGenerateHtml:
    def test_generates_html(self) -> None:
        gen = _make_generator()
        result = gen.generate_html(_NOW)
        assert "<!DOCTYPE html>" in result
        assert "ALGO-001" in result

    def test_includes_controls_html(self) -> None:
        gen = _make_generator()
        result = gen.generate_html(_NOW)
        assert "<ul>" in result
        assert "<li>" in result

    def test_includes_position_limits_html_when_present(self) -> None:
        gen = _make_generator()
        gen.add_position_limit("NSE", Decimal("100"), Decimal("500000"))
        result = gen.generate_html(_NOW)
        assert "<table" in result
        assert "NSE" in result

    def test_default_position_limits_html(self) -> None:
        gen = _make_generator()
        result = gen.generate_html(_NOW)
        assert "SEBI default" in result

    def test_naive_datetime_raises(self) -> None:
        gen = _make_generator()
        with pytest.raises(ConfigError, match="UTC"):
            gen.generate_html(datetime(2026, 5, 25, 10, 0))


class TestSaveDisclosure:
    def test_save_text(self, tmp_path: Path) -> None:
        gen = _make_generator(output_dir=tmp_path / "disclosures")
        result = gen.save_disclosure(_NOW, fmt="text")
        assert result.suffix == ".txt"
        assert result.exists()

    def test_save_html(self, tmp_path: Path) -> None:
        gen = _make_generator(output_dir=tmp_path / "disclosures")
        result = gen.save_disclosure(_NOW, fmt="html")
        assert result.suffix == ".html"
        assert result.exists()

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        output = tmp_path / "nested" / "dir"
        gen = _make_generator(output_dir=output)
        gen.save_disclosure(_NOW, fmt="text")
        assert output.exists()

    def test_naive_datetime_raises(self, tmp_path: Path) -> None:
        gen = _make_generator(output_dir=tmp_path)
        with pytest.raises(ConfigError, match="UTC"):
            gen.save_disclosure(datetime(2026, 5, 25, 10, 0))


class TestValidateUtc:
    def test_utc_passes(self) -> None:
        _validate_utc(_NOW)

    def test_naive_raises(self) -> None:
        with pytest.raises(ConfigError, match="UTC"):
            _validate_utc(datetime(2026, 5, 25, 10, 0))

    def test_non_utc_tz_raises(self) -> None:
        from datetime import timedelta, timezone

        ist = timezone(timedelta(hours=5, minutes=30))
        with pytest.raises(ConfigError, match="UTC"):
            _validate_utc(datetime(2026, 5, 25, 10, 0, tzinfo=ist))
