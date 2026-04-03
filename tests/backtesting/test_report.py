from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from iatb.backtesting.report import QuantStatsReporter
from iatb.core.exceptions import ConfigError


def test_quantstats_reporter_uses_custom_renderer(tmp_path: Path) -> None:
    output = tmp_path / "report.html"

    def _renderer(strategy: list[Decimal], benchmark: list[Decimal], path: str) -> None:
        _ = (strategy, benchmark)
        Path(path).write_text("<html>ok</html>", encoding="utf-8")

    reporter = QuantStatsReporter(renderer=_renderer)
    path = reporter.build_report(
        strategy_returns=[Decimal("0.01"), Decimal("0.02")],
        benchmark_returns=[Decimal("0.005"), Decimal("0.01")],
        output_path=str(output),
    )
    assert Path(path).exists()


def test_quantstats_reporter_rejects_invalid_inputs() -> None:
    reporter = QuantStatsReporter(renderer=lambda strategy, benchmark, path: None)
    with pytest.raises(ConfigError, match="cannot be empty"):
        reporter.build_report([], [], "x.html")
    with pytest.raises(ConfigError, match="length mismatch"):
        reporter.build_report([Decimal("0.01")], [Decimal("0.01"), Decimal("0.02")], "x.html")


def test_quantstats_reporter_requires_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "iatb.backtesting.report.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    reporter = QuantStatsReporter()
    with pytest.raises(ConfigError, match="quantstats dependency"):
        reporter.build_report([Decimal("0.01")], [Decimal("0.01")], "x.html")


def test_quantstats_reporter_requires_html_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "iatb.backtesting.report.importlib.import_module",
        lambda _: SimpleNamespace(reports=SimpleNamespace()),
    )
    reporter = QuantStatsReporter()
    with pytest.raises(ConfigError, match="reports.html is unavailable"):
        reporter.build_report([Decimal("0.01")], [Decimal("0.01")], "x.html")
