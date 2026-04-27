"""Tests for Risk Disclosure Document Generator."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from iatb.core.exceptions import ConfigError
from iatb.risk.risk_disclosure import (
    RiskDisclosureConfig,
    RiskDisclosureGenerator,
)


def _utc_now() -> datetime:
    return datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


class TestRiskDisclosureConfig:
    def test_valid_config(self) -> None:
        config = RiskDisclosureConfig(
            system_name="IATB",
            algo_id="ALGO-001",
        )
        assert config.system_name == "IATB"
        assert config.algo_id == "ALGO-001"

    def test_empty_system_name_rejected(self) -> None:
        with pytest.raises(ConfigError, match="system_name"):
            RiskDisclosureConfig(system_name="   ", algo_id="ALGO-001")

    def test_invalid_retention_years(self) -> None:
        with pytest.raises(ConfigError, match="retention_years"):
            RiskDisclosureConfig(
                system_name="IATB",
                algo_id="ALGO-001",
                retention_years=0,
            )


class TestRiskDisclosureGenerator:
    def _make_generator(self) -> RiskDisclosureGenerator:
        config = RiskDisclosureConfig(
            system_name="IATB",
            system_version="0.1.0",
            algo_id="ALGO-001",
            output_dir=Path("test_disclosures"),
        )
        return RiskDisclosureGenerator(config)

    def test_empty_algo_id_rejected(self) -> None:
        config = RiskDisclosureConfig(
            system_name="IATB",
            algo_id="",
        )
        with pytest.raises(ConfigError, match="algo_id"):
            RiskDisclosureGenerator(config)

    def test_generate_text(self) -> None:
        gen = self._make_generator()
        text = gen.generate_text(_utc_now())
        assert "ALGORITHMIC TRADING RISK DISCLOSURE" in text
        assert "IATB" in text
        assert "ALGO-001" in text
        assert "SEBI" in text
        assert "HMAC-SHA256" in text

    def test_generate_html(self) -> None:
        gen = self._make_generator()
        html = gen.generate_html(_utc_now())
        assert "<!DOCTYPE html>" in html
        assert "IATB" in html
        assert "ALGO-001" in html
        assert "<table" not in html

    def test_generate_text_with_position_limits(self) -> None:
        gen = self._make_generator()
        gen.add_position_limit("NSE", Decimal("10000"), Decimal("50000000"))
        text = gen.generate_text(_utc_now())
        assert "NSE" in text
        assert "10000" in text

    def test_generate_html_with_position_limits(self) -> None:
        gen = self._make_generator()
        gen.add_position_limit("NSE", Decimal("10000"), Decimal("50000000"))
        html = gen.generate_html(_utc_now())
        assert "<table" in html
        assert "NSE" in html

    def test_add_risk_control(self) -> None:
        gen = self._make_generator()
        gen.add_risk_control("Custom risk control A")
        text = gen.generate_text(_utc_now())
        assert "Custom risk control A" in text

    def test_add_risk_control_empty_rejected(self) -> None:
        gen = self._make_generator()
        with pytest.raises(ConfigError, match="empty"):
            gen.add_risk_control("")

    def test_add_position_limit_empty_exchange_rejected(self) -> None:
        gen = self._make_generator()
        with pytest.raises(ConfigError, match="exchange"):
            gen.add_position_limit("", Decimal("10"), Decimal("1000"))

    def test_add_position_limit_zero_quantity_rejected(self) -> None:
        gen = self._make_generator()
        with pytest.raises(ConfigError, match="max_quantity"):
            gen.add_position_limit("NSE", Decimal("0"), Decimal("1000"))

    def test_add_position_limit_zero_notional_rejected(self) -> None:
        gen = self._make_generator()
        with pytest.raises(ConfigError, match="max_notional"):
            gen.add_position_limit("NSE", Decimal("10"), Decimal("0"))

    def test_save_disclosure_text(self, tmp_path: Path) -> None:
        config = RiskDisclosureConfig(
            system_name="IATB",
            algo_id="ALGO-001",
            output_dir=tmp_path / "disclosures",
        )
        gen = RiskDisclosureGenerator(config)
        filepath = gen.save_disclosure(_utc_now(), fmt="text")
        assert filepath.exists()
        content = filepath.read_text(encoding="utf-8")
        assert "ALGORITHMIC TRADING RISK DISCLOSURE" in content

    def test_save_disclosure_html(self, tmp_path: Path) -> None:
        config = RiskDisclosureConfig(
            system_name="IATB",
            algo_id="ALGO-001",
            output_dir=tmp_path / "disclosures",
        )
        gen = RiskDisclosureGenerator(config)
        filepath = gen.save_disclosure(_utc_now(), fmt="html")
        assert filepath.exists()
        content = filepath.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content

    def test_naive_datetime_rejected(self) -> None:
        gen = self._make_generator()
        with pytest.raises(ConfigError, match="UTC"):
            gen.generate_text(datetime(2026, 4, 27, 12, 0, 0))  # noqa: DTZ001

    def test_naive_datetime_rejected_html(self) -> None:
        gen = self._make_generator()
        with pytest.raises(ConfigError, match="UTC"):
            gen.generate_html(datetime(2026, 4, 27, 12, 0, 0))  # noqa: DTZ001

    def test_default_risk_controls_present(self) -> None:
        gen = self._make_generator()
        text = gen.generate_text(_utc_now())
        assert "Circuit breaker" in text
        assert "Kill switch" in text
        assert "Position limit guard" in text

    def test_no_position_limits_shows_default(self) -> None:
        gen = self._make_generator()
        text = gen.generate_text(_utc_now())
        assert "No custom position limits" in text or "SEBI defaults" in text
