"""
QuantStats report generation wrappers.
"""

import importlib
from collections.abc import Callable
from decimal import Decimal

from iatb.core.exceptions import ConfigError

ReportRenderer = Callable[[list[Decimal], list[Decimal], str], None]


class QuantStatsReporter:
    """Generate benchmark-comparative HTML reports."""

    def __init__(self, renderer: ReportRenderer | None = None) -> None:
        self._renderer = renderer or _default_renderer

    def build_report(
        self,
        strategy_returns: list[Decimal],
        benchmark_returns: list[Decimal],
        output_path: str,
    ) -> str:
        if not strategy_returns or not benchmark_returns:
            msg = "strategy_returns and benchmark_returns cannot be empty"
            raise ConfigError(msg)
        if len(strategy_returns) != len(benchmark_returns):
            msg = "strategy_returns and benchmark_returns length mismatch"
            raise ConfigError(msg)
        self._renderer(strategy_returns, benchmark_returns, output_path)
        return output_path


def _default_renderer(
    strategy_returns: list[Decimal],
    benchmark_returns: list[Decimal],
    output_path: str,
) -> None:
    module = _load_quantstats_module()
    reports = getattr(module, "reports", None)
    html_fn = getattr(reports, "html", None)
    if not callable(html_fn):
        msg = "quantstats.reports.html is unavailable"
        raise ConfigError(msg)
    html_fn(
        strategy_returns,
        benchmark=benchmark_returns,
        output=output_path,
        title="IATB Backtest",
    )


def _load_quantstats_module() -> object:
    try:
        return importlib.import_module("quantstats")
    except ModuleNotFoundError as exc:
        msg = "quantstats dependency is required for backtest reporting"
        raise ConfigError(msg) from exc
