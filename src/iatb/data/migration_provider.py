"""
Risk 4 Migration Provider: Incremental migration with dual-path support and A/B testing.

This provider implements the mitigation strategy for Risk 4: Migration Regression.
It allows gradual migration from jugaad to other DataProvider implementations with:
- Feature flag for default provider selection
- Dual-path parallel execution for A/B testing
- Result comparison and anomaly detection
- Safe fallback mechanisms
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import Timestamp
from iatb.data.base import DataProvider, OHLCVBar, TickerSnapshot

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ABTestResult:
    """Result of A/B testing comparison between two providers."""

    symbol: str
    exchange: Exchange
    default_source: str
    fallback_source: str
    timestamp_utc: datetime
    bars_count_match: bool
    price_diff_pct: Decimal
    volume_diff_pct: Decimal
    max_diff_pct: Decimal
    exceeds_threshold: bool
    warning_message: str | None = None


class MigrationProvider(DataProvider):
    """
    DataProvider wrapper for incremental migration with A/B testing.

    Supports:
    - Feature flag: data_provider_default ("jugaad" | "kite" | "openalgo" | "yfinance")
    - Dual-path execution when enable_ab_testing is true
    - Result comparison with configurable threshold
    - Safe fallback on errors
    """

    def __init__(
        self,
        default_provider: DataProvider,
        fallback_provider: DataProvider,
        enable_ab_testing: bool = False,
        max_diff_pct: Decimal = Decimal("5.0"),
    ) -> None:
        self._default_provider = default_provider
        self._fallback_provider = fallback_provider
        self._enable_ab_testing = enable_ab_testing
        self._max_diff_pct = max_diff_pct
        self._ab_test_results: list[ABTestResult] = []

    @classmethod
    def from_config(
        cls,
        config_path: Path,
        providers: dict[str, DataProvider],
    ) -> "MigrationProvider":
        """
        Create MigrationProvider from configuration file.

        Args:
            config_path: Path to settings.toml configuration file
            providers: Dictionary of provider_name -> DataProvider instance

        Returns:
            Configured MigrationProvider instance

        Raises:
            ConfigError: If required providers are not configured
        """
        config_dict = cls._load_config_file(config_path)
        settings = cls._extract_config_settings(config_dict)
        cls._validate_providers(settings, providers)
        return cls(
            default_provider=providers[cast(str, settings["default_name"])],
            fallback_provider=providers[cast(str, settings["fallback_name"])],
            enable_ab_testing=bool(settings["enable_ab"]),
            max_diff_pct=Decimal(str(settings["max_diff"])),
        )

    @staticmethod
    def _load_config_file(config_path: Path) -> dict[str, object]:
        """Load and parse configuration file."""
        import tomli

        try:
            with config_path.open("rb") as f:
                return tomli.load(f)
        except FileNotFoundError as exc:
            msg = f"Config file not found: {config_path}"
            raise ConfigError(msg) from exc
        except Exception as exc:
            msg = f"Failed to load config from {config_path}: {exc}"
            raise ConfigError(msg) from exc

    @staticmethod
    def _extract_config_settings(config_dict: dict[str, object]) -> dict[str, str | bool | Decimal]:
        """Extract migration settings from config dict."""
        data_config = config_dict.get("data", {})
        if not isinstance(data_config, dict):
            data_config = {}
        return {
            "default_name": str(data_config.get("data_provider_default", "jugaad")),
            "fallback_name": str(data_config.get("data_provider_fallback", "kite")),
            "enable_ab": bool(data_config.get("enable_ab_testing", False)),
            "max_diff": Decimal(str(data_config.get("ab_testing_max_diff_pct", "5.0"))),
        }

    @staticmethod
    def _validate_providers(
        settings: dict[str, str | bool | Decimal], providers: dict[str, DataProvider]
    ) -> None:
        """Validate that required providers exist."""
        provider_keys = list(providers.keys())
        default_name = settings["default_name"]
        fallback_name = settings["fallback_name"]

        if default_name not in providers:
            msg = f"Default provider '{default_name}' not found in providers: {provider_keys}"
            raise ConfigError(msg)
        if fallback_name not in providers:
            msg = f"Fallback provider '{fallback_name}' not found in providers: {provider_keys}"
            raise ConfigError(msg)

    async def get_ohlcv(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: Timestamp | None = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        """
        Fetch OHLCV bars with optional A/B testing.

        If A/B testing is enabled, fetches from both providers in parallel,
        compares results, logs warnings on significant differences, and returns
        default provider results.

        Args:
            symbol: Trading symbol
            exchange: Exchange
            timeframe: Timeframe (e.g., "1d")
            since: Start timestamp
            limit: Maximum number of bars

        Returns:
            List of OHLCVBar from default provider (or fallback if default fails)

        Raises:
            ConfigError: If both providers fail
        """
        if self._enable_ab_testing:
            return await self._get_ohlcv_with_ab_testing(
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
                since=since,
                limit=limit,
            )

        # Single-path execution
        try:
            return await self._default_provider.get_ohlcv(
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
                since=since,
                limit=limit,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "Default provider failed for %s, trying fallback: %s",
                symbol,
                exc,
            )
            try:
                return await self._fallback_provider.get_ohlcv(
                    symbol=symbol,
                    exchange=exchange,
                    timeframe=timeframe,
                    since=since,
                    limit=limit,
                )
            except Exception as fallback_exc:  # noqa: BLE001
                msg = f"Both providers failed for {symbol}: {exc}, {fallback_exc}"
                raise ConfigError(msg) from fallback_exc

    async def _get_ohlcv_with_ab_testing(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: Timestamp | None,
        limit: int,
    ) -> list[OHLCVBar]:
        """
        Fetch from both providers in parallel and compare results.

        Returns default provider results, logs warnings on significant differences.
        """
        default_source = self._get_provider_name(self._default_provider)
        fallback_source = self._get_provider_name(self._fallback_provider)

        try:
            default_bars, fallback_bars = await self._fetch_from_both_providers(
                symbol, exchange, timeframe, since, limit
            )
            return self._handle_ab_testing_results(
                symbol,
                default_bars,
                fallback_bars,
                default_source,
                fallback_source,
                exchange,
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"A/B testing failed for {symbol}: {exc}"
            raise ConfigError(msg) from exc

    async def _fetch_from_both_providers(
        self,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: Timestamp | None,
        limit: int,
    ) -> tuple[list[OHLCVBar] | BaseException, list[OHLCVBar] | BaseException]:
        """Fetch OHLCV data from both providers in parallel."""
        return await asyncio.gather(
            self._default_provider.get_ohlcv(
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
                since=since,
                limit=limit,
            ),
            self._fallback_provider.get_ohlcv(
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
                since=since,
                limit=limit,
            ),
            return_exceptions=True,
        )

    def _handle_ab_testing_results(
        self,
        symbol: str,
        default_bars: list[OHLCVBar] | BaseException,
        fallback_bars: list[OHLCVBar] | BaseException,
        default_source: str,
        fallback_source: str,
        exchange: Exchange,
    ) -> list[OHLCVBar]:
        """Handle and compare A/B testing results from both providers."""
        # Handle exceptions
        if isinstance(default_bars, BaseException):
            _LOGGER.error("Default provider failed for %s: %s", symbol, default_bars)
            if isinstance(fallback_bars, BaseException):
                msg = f"Both providers failed for {symbol}: {default_bars}, {fallback_bars}"
                raise ConfigError(msg) from default_bars
            return fallback_bars

        if isinstance(fallback_bars, BaseException):
            _LOGGER.warning("Fallback provider failed for %s: %s", symbol, fallback_bars)
            return default_bars

        # Compare results
        comparison = self._compare_ohlcv_results(
            symbol=symbol,
            exchange=exchange,
            default_bars=default_bars,
            fallback_bars=fallback_bars,
            default_source=default_source,
            fallback_source=fallback_source,
        )

        self._ab_test_results.append(comparison)

        if comparison.exceeds_threshold:
            _LOGGER.warning(
                "A/B test anomaly for %s: %s",
                symbol,
                comparison.warning_message,
            )

        return default_bars

    def _compare_ohlcv_results(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        default_bars: list[OHLCVBar],
        fallback_bars: list[OHLCVBar],
        default_source: str,
        fallback_source: str,
    ) -> ABTestResult:
        """Compare OHLCV results from two providers."""
        bars_match = len(default_bars) == len(fallback_bars)

        if not bars_match:
            return self._create_mismatch_result(
                symbol, exchange, default_source, fallback_source, default_bars, fallback_bars
            )

        if not default_bars or not fallback_bars:
            return self._create_empty_result(symbol, exchange, default_source, fallback_source)

        return self._compare_bars_content(
            symbol, exchange, default_bars, fallback_bars, default_source, fallback_source
        )

    def _create_mismatch_result(
        self,
        symbol: str,
        exchange: Exchange,
        default_source: str,
        fallback_source: str,
        default_bars: list[OHLCVBar],
        fallback_bars: list[OHLCVBar],
    ) -> ABTestResult:
        """Create result for bar count mismatch."""
        return ABTestResult(
            symbol=symbol,
            exchange=exchange,
            default_source=default_source,
            fallback_source=fallback_source,
            timestamp_utc=datetime.now(UTC),
            bars_count_match=False,
            price_diff_pct=Decimal("0"),
            volume_diff_pct=Decimal("0"),
            max_diff_pct=Decimal("0"),
            exceeds_threshold=True,
            warning_message=(
                f"Bar count mismatch: default={len(default_bars)}, "
                f"fallback={len(fallback_bars)}"
            ),
        )

    def _create_empty_result(
        self, symbol: str, exchange: Exchange, default_source: str, fallback_source: str
    ) -> ABTestResult:
        """Create result for empty bars."""
        return ABTestResult(
            symbol=symbol,
            exchange=exchange,
            default_source=default_source,
            fallback_source=fallback_source,
            timestamp_utc=datetime.now(UTC),
            bars_count_match=True,
            price_diff_pct=Decimal("0"),
            volume_diff_pct=Decimal("0"),
            max_diff_pct=Decimal("0"),
            exceeds_threshold=False,
        )

    def _compare_bars_content(
        self,
        symbol: str,
        exchange: Exchange,
        default_bars: list[OHLCVBar],
        fallback_bars: list[OHLCVBar],
        default_source: str,
        fallback_source: str,
    ) -> ABTestResult:
        """Compare actual bar content between two providers."""
        latest_default = default_bars[-1]
        latest_fallback = fallback_bars[-1]

        price_diff_pct = self._calculate_diff_pct(latest_default.close, latest_fallback.close)
        volume_diff_pct = self._calculate_diff_pct(latest_default.volume, latest_fallback.volume)
        max_diff_pct = max(abs(price_diff_pct), abs(volume_diff_pct))

        exceeds = max_diff_pct > self._max_diff_pct
        warning = self._generate_warning(exceeds, price_diff_pct, volume_diff_pct, max_diff_pct)

        return ABTestResult(
            symbol=symbol,
            exchange=exchange,
            default_source=default_source,
            fallback_source=fallback_source,
            timestamp_utc=datetime.now(UTC),
            bars_count_match=True,
            price_diff_pct=price_diff_pct,
            volume_diff_pct=volume_diff_pct,
            max_diff_pct=max_diff_pct,
            exceeds_threshold=exceeds,
            warning_message=warning,
        )

    def _generate_warning(
        self, exceeds: bool, price_diff: Decimal, volume_diff: Decimal, max_diff: Decimal
    ) -> str | None:
        """Generate warning message if threshold exceeded."""
        if not exceeds:
            return None
        return (
            f"Price diff: {price_diff:.2f}%, "
            f"Volume diff: {volume_diff:.2f}%, "
            f"Max diff: {max_diff:.2f}% (threshold: {self._max_diff_pct}%)"
        )

    @staticmethod
    def _calculate_diff_pct(value1: Decimal, value2: Decimal) -> Decimal:
        """Calculate percentage difference between two decimal values."""
        if value1 == Decimal("0") and value2 == Decimal("0"):
            return Decimal("0")
        if value1 == Decimal("0"):
            return Decimal("100")
        return ((value1 - value2) / abs(value1)) * Decimal("100")

    async def get_ticker(self, *, symbol: str, exchange: Exchange) -> TickerSnapshot:
        """Fetch ticker snapshot with optional fallback."""
        try:
            return await self._default_provider.get_ticker(symbol=symbol, exchange=exchange)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "Default provider ticker failed for %s, trying fallback: %s",
                symbol,
                exc,
            )
            try:
                return await self._fallback_provider.get_ticker(symbol=symbol, exchange=exchange)
            except Exception as fallback_exc:  # noqa: BLE001
                msg = f"Both providers failed ticker for {symbol}: {exc}, {fallback_exc}"
                raise ConfigError(msg) from fallback_exc

    async def get_ohlcv_batch(
        self,
        *,
        symbols: list[str],
        exchange: Exchange,
        timeframe: str,
        since: Timestamp | None = None,
        limit: int = 500,
    ) -> dict[str, list[OHLCVBar]]:
        """
        Fetch OHLCV bars for multiple symbols.

        Delegates to default provider if batch is supported,
        otherwise falls back to parallel individual requests.
        """
        # Try default provider batch first
        try:
            if hasattr(self._default_provider, "get_ohlcv_batch"):
                return await self._default_provider.get_ohlcv_batch(
                    symbols=symbols,
                    exchange=exchange,
                    timeframe=timeframe,
                    since=since,
                    limit=limit,
                )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Default provider batch failed, using parallel: %s", exc)

        # Fallback to parallel individual requests
        tasks = [
            self.get_ohlcv(
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
                since=since,
                limit=limit,
            )
            for symbol in symbols
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output: dict[str, list[OHLCVBar]] = {}
        for symbol, result in zip(symbols, results, strict=False):
            if isinstance(result, Exception):
                _LOGGER.warning("Failed to fetch %s: %s", symbol, result)
                output[symbol] = []
            else:
                output[symbol] = cast(list[OHLCVBar], result)

        return output

    def get_ab_test_results(self) -> list[ABTestResult]:
        """Get all A/B test results for analysis."""
        return self._ab_test_results.copy()

    def clear_ab_test_results(self) -> None:
        """Clear stored A/B test results."""
        self._ab_test_results.clear()

    def get_ab_test_summary(self) -> dict[str, int | Decimal]:
        """Get summary statistics of A/B test results."""
        if not self._ab_test_results:
            return {
                "total_tests": 0,
                "anomalies": 0,
                "max_diff_pct": Decimal("0"),
                "avg_diff_pct": Decimal("0"),
            }

        total = len(self._ab_test_results)
        anomalies = sum(1 for r in self._ab_test_results if r.exceeds_threshold)
        max_diff = max((r.max_diff_pct for r in self._ab_test_results), default=Decimal("0"))
        avg_diff = sum(r.max_diff_pct for r in self._ab_test_results) / Decimal(str(total))

        return {
            "total_tests": total,
            "anomalies": anomalies,
            "max_diff_pct": max_diff,
            "avg_diff_pct": avg_diff,
        }

    @staticmethod
    def _get_provider_name(provider: DataProvider) -> str:
        """Extract provider name from class name."""
        class_name = provider.__class__.__name__
        return class_name.replace("Provider", "").lower()
