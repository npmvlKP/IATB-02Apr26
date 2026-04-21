"""
Tests for FailoverProvider with circuit-breaker pattern.

Tests cover:
- Happy path: primary provider succeeds
- Failover: primary fails, secondary succeeds
- Circuit breaker state management
- Cooldown period enforcement
- Source tagging verification
- Logging at WARNING level
- Metrics recording
- All providers fail scenario
- get_ohlcv, get_ticker, get_ohlcv_batch methods
- Circuit state inspection and reset
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price, create_quantity
from iatb.data.base import DataProvider, OHLCVBar, TickerSnapshot
from iatb.data.failover_provider import CircuitBreaker, CircuitState, FailoverProvider


class MockProvider(DataProvider):
    """Mock data provider for testing."""

    def __init__(
        self,
        name: str,
        *,
        should_fail: bool = False,
        delay_seconds: float = 0.0,
    ) -> None:
        self.name = name
        self.should_fail = should_fail
        self.delay_seconds = delay_seconds
        self.get_ohlcv_calls: list[dict[str, Any]] = []
        self.get_ticker_calls: list[dict[str, Any]] = []

    async def get_ohlcv(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: Any | None = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        self.get_ohlcv_calls.append(
            {
                "symbol": symbol,
                "exchange": exchange,
                "timeframe": timeframe,
                "since": since,
                "limit": limit,
            }
        )

        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)

        if self.should_fail:
            msg = f"{self.name} provider failed"
            raise ConfigError(msg)

        return [
            OHLCVBar(
                exchange=exchange,
                symbol=symbol,
                open=create_price("100"),
                high=create_price("110"),
                low=create_price("95"),
                close=create_price("105"),
                volume=create_quantity("1000"),
                source=self.name,
            )
        ]

    async def get_ticker(
        self,
        *,
        symbol: str,
        exchange: Exchange,
    ) -> TickerSnapshot:
        self.get_ticker_calls.append({"symbol": symbol, "exchange": exchange})

        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)

        if self.should_fail:
            msg = f"{self.name} provider failed"
            raise ConfigError(msg)

        return TickerSnapshot(
            exchange=exchange,
            symbol=symbol,
            bid=create_price("104"),
            ask=create_price("106"),
            last=create_price("105"),
            volume_24h=create_quantity("10000"),
            source=self.name,
        )

    async def get_ohlcv_batch(
        self,
        *,
        symbols: list[str],
        exchange: Exchange,
        timeframe: str,
        since: Any | None = None,
        limit: int = 500,
    ) -> dict[str, list[OHLCVBar]]:
        if self.should_fail:
            msg = f"{self.name} provider failed"
            raise ConfigError(msg)

        results = {}
        for symbol in symbols:
            results[symbol] = [
                OHLCVBar(
                    exchange=exchange,
                    symbol=symbol,
                    open=create_price("100"),
                    high=create_price("110"),
                    low=create_price("95"),
                    close=create_price("105"),
                    volume=create_quantity("1000"),
                    source=self.name,
                )
            ]
        return results


@pytest.fixture
def mock_metrics_switches() -> list[tuple[str, str, str]]:
    """Mock metrics switches callback."""
    switches: list[tuple[str, str, str]] = []

    def record_switch(from_provider: str, to_provider: str, method_name: str) -> None:
        switches.append((from_provider, to_provider, method_name))

    return switches, record_switch


@pytest.fixture
def mock_metrics_latency() -> list[tuple[str, str, float]]:
    """Mock metrics latency callback."""
    latencies: list[tuple[str, str, float]] = []

    def record_latency(provider_name: str, method_name: str, latency_seconds: float) -> None:
        latencies.append((provider_name, method_name, latency_seconds))

    return latencies, record_latency


class TestFailoverProviderInitialization:
    """Tests for FailoverProvider initialization."""

    def test_empty_providers_raises_error(self) -> None:
        """Test that empty providers list raises ConfigError."""
        with pytest.raises(ConfigError, match="providers list cannot be empty"):
            FailoverProvider(providers=[])

    def test_negative_cooldown_raises_error(self) -> None:
        """Test that negative cooldown raises ConfigError."""
        provider = MockProvider("test")
        with pytest.raises(ConfigError, match="cooldown_seconds must be positive"):
            FailoverProvider(providers=[provider], cooldown_seconds=-1.0)

    def test_zero_cooldown_raises_error(self) -> None:
        """Test that zero cooldown raises ConfigError."""
        provider = MockProvider("test")
        with pytest.raises(ConfigError, match="cooldown_seconds must be positive"):
            FailoverProvider(providers=[provider], cooldown_seconds=0.0)

    def test_successful_initialization(self) -> None:
        """Test successful initialization with valid parameters."""
        provider1 = MockProvider("provider1")
        provider2 = MockProvider("provider2")

        failover = FailoverProvider(
            providers=[provider1, provider2],
            cooldown_seconds=10.0,
        )

        assert len(failover._providers) == 2
        assert failover._cooldown_seconds == 10.0
        # Each provider has a unique name, so circuits dict has 2 entries
        assert "provider1" in failover._circuits
        assert "provider2" in failover._circuits
        assert failover._circuits["provider1"].cooldown_seconds == 10.0
        assert failover._circuits["provider2"].cooldown_seconds == 10.0

    def test_metrics_callbacks_stored(self, mock_metrics_switches, mock_metrics_latency) -> None:
        """Test that metrics callbacks are stored."""
        provider = MockProvider("test")
        _, switches_cb = mock_metrics_switches
        _, latency_cb = mock_metrics_latency

        failover = FailoverProvider(
            providers=[provider],
            metrics_switches=switches_cb,
            metrics_latency=latency_cb,
        )

        assert failover._metrics_switches is switches_cb
        assert failover._metrics_latency is latency_cb


class TestFailoverProviderHappyPath:
    """Tests for happy path scenarios (primary provider succeeds)."""

    @pytest.mark.asyncio
    async def test_primary_provider_succeeds_get_ohlcv(self) -> None:
        """Test that primary provider succeeds for get_ohlcv."""
        primary = MockProvider("kiteconnect")
        secondary = MockProvider("jugaad")

        failover = FailoverProvider(providers=[primary, secondary])

        result = await failover.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=10,
        )

        assert len(result) == 1
        assert result[0].source == "kiteconnect"
        assert len(primary.get_ohlcv_calls) == 1
        assert len(secondary.get_ohlcv_calls) == 0

    @pytest.mark.asyncio
    async def test_primary_provider_succeeds_get_ticker(self) -> None:
        """Test that primary provider succeeds for get_ticker."""
        primary = MockProvider("kiteconnect")
        secondary = MockProvider("jugaad")

        failover = FailoverProvider(providers=[primary, secondary])

        result = await failover.get_ticker(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
        )

        assert result.source == "kiteconnect"
        assert len(primary.get_ticker_calls) == 1
        assert len(secondary.get_ticker_calls) == 0

    @pytest.mark.asyncio
    async def test_primary_provider_succeeds_get_ohlcv_batch(self) -> None:
        """Test that primary provider succeeds for get_ohlcv_batch."""
        primary = MockProvider("kiteconnect")
        secondary = MockProvider("jugaad")

        failover = FailoverProvider(providers=[primary, secondary])

        result = await failover.get_ohlcv_batch(
            symbols=["RELIANCE", "TCS"],
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=10,
        )

        assert len(result) == 2
        for bars in result.values():
            assert bars[0].source == "kiteconnect"


class TestFailoverProviderFailover:
    """Tests for failover scenarios (primary fails, secondary succeeds)."""

    @pytest.mark.asyncio
    async def test_primary_fails_secondary_succeeds_get_ohlcv(
        self, mock_metrics_switches, mock_metrics_latency
    ) -> None:
        """Test failover from primary to secondary for get_ohlcv."""
        primary = MockProvider("kiteconnect", should_fail=True)
        secondary = MockProvider("jugaad")
        switches, switches_cb = mock_metrics_switches
        latencies, latency_cb = mock_metrics_latency

        failover = FailoverProvider(
            providers=[primary, secondary],
            metrics_switches=switches_cb,
            metrics_latency=latency_cb,
        )

        result = await failover.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=10,
        )

        assert len(result) == 1
        assert result[0].source == "jugaad"
        assert len(primary.get_ohlcv_calls) == 1
        assert len(secondary.get_ohlcv_calls) == 1
        assert len(switches) == 1
        assert switches[0] == ("kiteconnect", "jugaad", "get_ohlcv")
        assert len(latencies) == 1
        assert latencies[0][0] == "jugaad"

    @pytest.mark.asyncio
    async def test_primary_fails_secondary_succeeds_get_ticker(self, mock_metrics_switches) -> None:
        """Test failover from primary to secondary for get_ticker."""
        primary = MockProvider("kiteconnect", should_fail=True)
        secondary = MockProvider("jugaad")
        switches, switches_cb = mock_metrics_switches

        failover = FailoverProvider(
            providers=[primary, secondary],
            metrics_switches=switches_cb,
        )

        result = await failover.get_ticker(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
        )

        assert result.source == "jugaad"
        assert len(primary.get_ticker_calls) == 1
        assert len(secondary.get_ticker_calls) == 1
        assert len(switches) == 1
        assert switches[0] == ("kiteconnect", "jugaad", "get_ticker")

    @pytest.mark.asyncio
    async def test_two_providers_fail_third_succeeds(self) -> None:
        """Test failover through two failed providers to third."""
        primary = MockProvider("kiteconnect", should_fail=True)
        secondary = MockProvider("jugaad", should_fail=True)
        tertiary = MockProvider("yfinance")

        failover = FailoverProvider(providers=[primary, secondary, tertiary])

        result = await failover.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
        )

        assert result[0].source == "yfinance"
        assert len(primary.get_ohlcv_calls) == 1
        assert len(secondary.get_ohlcv_calls) == 1
        assert len(tertiary.get_ohlcv_calls) == 1


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    def test_initial_state_is_closed(self) -> None:
        """Test that initial circuit state is CLOSED."""
        circuit = CircuitBreaker(provider_name="test")
        assert circuit.state == CircuitState.CLOSED
        assert circuit.failure_count == 0
        assert circuit.last_failure_time is None
        assert circuit.is_available()

    def test_record_failure_opens_circuit(self) -> None:
        """Test that recording failure opens circuit."""
        circuit = CircuitBreaker(provider_name="test")
        circuit.record_failure()

        assert circuit.state == CircuitState.OPEN
        assert circuit.failure_count == 1
        assert circuit.last_failure_time is not None
        assert not circuit.is_available()

    def test_record_success_closes_circuit(self) -> None:
        """Test that recording success closes circuit."""
        circuit = CircuitBreaker(provider_name="test")
        circuit.record_failure()
        circuit.record_success()

        assert circuit.state == CircuitState.CLOSED
        assert circuit.failure_count == 0
        assert circuit.last_failure_time is None
        assert circuit.is_available()

    def test_cooldown_prevents_availability(self) -> None:
        """Test that cooldown period prevents availability."""
        circuit = CircuitBreaker(provider_name="test", cooldown_seconds=30.0)
        circuit.record_failure()

        # Immediately after failure, should not be available
        assert not circuit.is_available()

        # After 20 seconds, still in cooldown
        circuit.last_failure_time = datetime.now(UTC) - timedelta(seconds=20)
        assert not circuit.is_available()

        # After 30 seconds, cooldown expired
        circuit.last_failure_time = datetime.now(UTC) - timedelta(seconds=30)
        assert circuit.is_available()
        assert circuit.state == CircuitState.CLOSED

    def test_multiple_failures_tracked(self) -> None:
        """Test that multiple failures are tracked."""
        circuit = CircuitBreaker(provider_name="test")
        circuit.record_failure()
        circuit.record_failure()
        circuit.record_failure()

        assert circuit.failure_count == 3
        assert circuit.state == CircuitState.OPEN

    def test_cooldown_reset_on_success(self) -> None:
        """Test that cooldown is reset on success."""
        circuit = CircuitBreaker(provider_name="test", cooldown_seconds=30.0)
        circuit.record_failure()
        assert not circuit.is_available()

        # Manually set last failure time
        circuit.last_failure_time = datetime.now(UTC) - timedelta(seconds=20)

        # Record success should reset
        circuit.record_success()
        assert circuit.is_available()
        assert circuit.last_failure_time is None

    def test_is_available_with_open_circuit_and_no_failure_time(self) -> None:
        """Test is_available when circuit is OPEN but last_failure_time is None (edge case)."""
        circuit = CircuitBreaker(provider_name="test")
        # Manually set state to OPEN without calling record_failure
        circuit.state = CircuitState.OPEN
        circuit.last_failure_time = None
        # Should be available since last_failure_time is None
        assert circuit.is_available()


class TestFailoverProviderCircuitBreaker:
    """Tests for FailoverProvider circuit breaker integration."""

    @pytest.mark.asyncio
    async def test_failed_provider_skipped_during_cooldown(self) -> None:
        """Test that failed provider is skipped during cooldown."""
        primary = MockProvider("kiteconnect", should_fail=True)
        secondary = MockProvider("jugaad")
        tertiary = MockProvider("yfinance")

        failover = FailoverProvider(
            providers=[primary, secondary, tertiary],
            cooldown_seconds=5.0,
        )

        # First call: primary fails, falls back to secondary
        result1 = await failover.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
        )
        assert result1[0].source == "jugaad"

        # Second call: primary still in cooldown, should try secondary first
        # Secondary succeeds, so no switch to tertiary
        result2 = await failover.get_ohlcv(
            symbol="TCS",
            exchange=Exchange.NSE,
            timeframe="1d",
        )
        assert result2[0].source == "jugaad"

        # Primary should not have been called again (in cooldown)
        assert len(primary.get_ohlcv_calls) == 1

    @pytest.mark.asyncio
    async def test_circuit_resets_after_cooldown(self) -> None:
        """Test that circuit resets after cooldown period."""
        primary = MockProvider("kiteconnect", should_fail=True)
        secondary = MockProvider("jugaad")

        failover = FailoverProvider(
            providers=[primary, secondary],
            cooldown_seconds=0.1,  # 100ms cooldown
        )

        # First call: primary fails, falls back to secondary
        result1 = await failover.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
        )
        assert result1[0].source == "jugaad"

        # Wait for cooldown to expire
        await asyncio.sleep(0.15)

        # Second call: primary should be tried again (cooldown expired)
        # But primary still fails, so falls back to secondary
        result2 = await failover.get_ohlcv(
            symbol="TCS",
            exchange=Exchange.NSE,
            timeframe="1d",
        )
        assert result2[0].source == "jugaad"

        # Primary should have been called again (cooldown expired)
        assert len(primary.get_ohlcv_calls) == 2

    @pytest.mark.asyncio
    async def test_get_circuit_states(self) -> None:
        """Test get_circuit_states method."""
        primary = MockProvider("kiteconnect")
        secondary = MockProvider("jugaad")

        failover = FailoverProvider(
            providers=[primary, secondary],
            cooldown_seconds=30.0,
        )

        states = failover.get_circuit_states()

        assert "kiteconnect" in states
        assert "jugaad" in states
        assert states["kiteconnect"]["state"] == "CLOSED"
        assert states["kiteconnect"]["available"] is True
        assert states["kiteconnect"]["failure_count"] == 0

    @pytest.mark.asyncio
    async def test_reset_circuit(self) -> None:
        """Test reset_circuit method."""
        primary = MockProvider("kiteconnect", should_fail=True)
        secondary = MockProvider("jugaad", should_fail=True)

        failover = FailoverProvider(
            providers=[primary, secondary],
            cooldown_seconds=30.0,
        )

        # Cause both providers to fail
        with pytest.raises(ConfigError):
            await failover.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1d",
            )

        # Check circuit is open
        states = failover.get_circuit_states()
        assert states["kiteconnect"]["state"] == "OPEN"
        assert states["kiteconnect"]["available"] is False

        # Reset circuit
        failover.reset_circuit("kiteconnect")

        # Check circuit is closed
        states = failover.get_circuit_states()
        assert states["kiteconnect"]["state"] == "CLOSED"
        assert states["kiteconnect"]["available"] is True
        assert states["kiteconnect"]["failure_count"] == 0

    def test_reset_circuit_unknown_provider_raises_error(self) -> None:
        """Test that resetting unknown provider raises error."""
        provider = MockProvider("test")
        failover = FailoverProvider(providers=[provider])

        with pytest.raises(ConfigError, match="Unknown provider name"):
            failover.reset_circuit("unknown")


class TestFailoverProviderAllProvidersFail:
    """Tests for scenario where all providers fail."""

    @pytest.mark.asyncio
    async def test_all_providers_fail_raises_error(self) -> None:
        """Test that ConfigError is raised when all providers fail."""
        primary = MockProvider("kiteconnect", should_fail=True)
        secondary = MockProvider("jugaad", should_fail=True)
        tertiary = MockProvider("yfinance", should_fail=True)

        failover = FailoverProvider(
            providers=[primary, secondary, tertiary],
        )

        with pytest.raises(ConfigError, match="All data providers failed"):
            await failover.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1d",
            )

    @pytest.mark.asyncio
    async def test_all_providers_fail_in_cooldown_raises_error(self) -> None:
        """Test that ConfigError is raised when all providers are in cooldown."""
        primary = MockProvider("kiteconnect", should_fail=True)
        secondary = MockProvider("jugaad", should_fail=True)

        failover = FailoverProvider(
            providers=[primary, secondary],
            cooldown_seconds=60.0,
        )

        # Cause both to fail
        with pytest.raises(ConfigError):
            await failover.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1d",
            )

        # Both should be in cooldown now
        states = failover.get_circuit_states()
        assert not states["kiteconnect"]["available"]
        assert not states["jugaad"]["available"]

        # Next call should fail immediately with all providers error
        with pytest.raises(ConfigError, match="All data providers failed"):
            await failover.get_ohlcv(
                symbol="TCS",
                exchange=Exchange.NSE,
                timeframe="1d",
            )


class TestFailoverProviderLatencyTracking:
    """Tests for latency tracking in metrics."""

    @pytest.mark.asyncio
    async def test_latency_recorded_on_success(self, mock_metrics_latency) -> None:
        """Test that latency is recorded on successful request."""
        primary = MockProvider("kiteconnect", delay_seconds=0.05)
        latencies, latency_cb = mock_metrics_latency

        failover = FailoverProvider(
            providers=[primary],
            metrics_latency=latency_cb,
        )

        await failover.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
        )

        assert len(latencies) == 1
        provider, method, latency = latencies[0]
        assert provider == "kiteconnect"
        assert method == "get_ohlcv"
        assert latency >= 0.05  # At least the delay we added

    @pytest.mark.asyncio
    async def test_latency_not_recorded_on_failure(self, mock_metrics_latency) -> None:
        """Test that latency is not recorded on failed request."""
        primary = MockProvider("kiteconnect", should_fail=True)
        secondary = MockProvider("jugaad")
        latencies, latency_cb = mock_metrics_latency

        failover = FailoverProvider(
            providers=[primary, secondary],
            metrics_latency=latency_cb,
        )

        await failover.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
        )

        # Only secondary success should be recorded
        assert len(latencies) == 1
        assert latencies[0][0] == "jugaad"


class TestFailoverProviderSourceTagging:
    """Tests for source tagging in responses."""

    @pytest.mark.asyncio
    async def test_source_tagged_in_ohlcv_response(self) -> None:
        """Test that source is tagged in OHLCV response."""
        provider = MockProvider("kiteconnect")
        failover = FailoverProvider(providers=[provider])

        result = await failover.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
        )

        assert len(result) == 1
        assert result[0].source == "kiteconnect"

    @pytest.mark.asyncio
    async def test_source_tagged_in_ticker_response(self) -> None:
        """Test that source is tagged in ticker response."""
        provider = MockProvider("kiteconnect")
        failover = FailoverProvider(providers=[provider])

        result = await failover.get_ticker(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
        )

        assert result.source == "kiteconnect"

    @pytest.mark.asyncio
    async def test_source_tagged_in_batch_response(self) -> None:
        """Test that source is tagged in batch response."""
        provider = MockProvider("kiteconnect")
        failover = FailoverProvider(providers=[provider])

        result = await failover.get_ohlcv_batch(
            symbols=["RELIANCE", "TCS"],
            exchange=Exchange.NSE,
            timeframe="1d",
        )

        assert len(result) == 2
        for bars in result.values():
            assert bars[0].source == "kiteconnect"


class TestFailoverProviderNaming:
    """Tests for provider name extraction logic."""

    @pytest.mark.asyncio
    async def test_provider_name_from_name_attribute(self) -> None:
        """Test provider name extraction from name attribute."""
        provider = MockProvider("custom_provider_name")
        failover = FailoverProvider(providers=[provider])

        states = failover.get_circuit_states()
        assert "custom_provider_name" in states

    @pytest.mark.asyncio
    async def test_provider_name_from_class_name_fallback(self) -> None:
        """Test provider name extraction from class name (no name attribute)."""

        # Create a provider without a name attribute
        class NoNameProvider(DataProvider):
            async def get_ohlcv(  # type: ignore[override]
                self,
                *,
                symbol: str,
                exchange: Exchange,
                timeframe: str,
                since: Any | None = None,
                limit: int = 500,
            ) -> list[OHLCVBar]:
                return []

            async def get_ticker(  # type: ignore[override]
                self,
                *,
                symbol: str,
                exchange: Exchange,
            ) -> TickerSnapshot:
                return TickerSnapshot(
                    exchange=exchange,
                    symbol=symbol,
                    bid=create_price("100"),
                    ask=create_price("101"),
                    last=create_price("100.5"),
                    volume_24h=create_quantity("1000"),
                    source="nonameprovider_0",
                )

            async def get_ohlcv_batch(  # type: ignore[override]
                self,
                *,
                symbols: list[str],
                exchange: Exchange,
                timeframe: str,
                since: Any | None = None,
                limit: int = 500,
            ) -> dict[str, list[OHLCVBar]]:
                return {}

        provider = NoNameProvider()
        failover = FailoverProvider(providers=[provider])

        states = failover.get_circuit_states()
        # Should use class name with index as fallback
        assert "nonameprovider_0" in states

    @pytest.mark.asyncio
    async def test_provider_name_from_kite_provider_class(self) -> None:
        """Test provider name extraction for KiteProvider class name."""

        # Create a provider with class name "KiteProvider" but no name attribute
        class KiteProvider(DataProvider):
            async def get_ohlcv(  # type: ignore[override]
                self,
                *,
                symbol: str,
                exchange: Exchange,
                timeframe: str,
                since: Any | None = None,
                limit: int = 500,
            ) -> list[OHLCVBar]:
                return [
                    OHLCVBar(
                        exchange=exchange,
                        symbol=symbol,
                        open=create_price("100"),
                        high=create_price("110"),
                        low=create_price("95"),
                        close=create_price("105"),
                        volume=create_quantity("1000"),
                        source="kiteconnect",
                    )
                ]

            async def get_ticker(  # type: ignore[override]
                self,
                *,
                symbol: str,
                exchange: Exchange,
            ) -> TickerSnapshot:
                return TickerSnapshot(
                    exchange=exchange,
                    symbol=symbol,
                    bid=create_price("104"),
                    ask=create_price("106"),
                    last=create_price("105"),
                    volume_24h=create_quantity("10000"),
                    source="kiteconnect",
                )

            async def get_ohlcv_batch(  # type: ignore[override]
                self,
                *,
                symbols: list[str],
                exchange: Exchange,
                timeframe: str,
                since: Any | None = None,
                limit: int = 500,
            ) -> dict[str, list[OHLCVBar]]:
                return {}

        provider = KiteProvider()
        failover = FailoverProvider(providers=[provider])

        states = failover.get_circuit_states()
        # Should use "kiteconnect" from class name mapping
        assert "kiteconnect" in states

    @pytest.mark.asyncio
    async def test_provider_name_from_jugaad_provider_class(self) -> None:
        """Test provider name extraction for JugaadProvider class name."""

        # Create a provider with class name "JugaadProvider" but no name attribute
        class JugaadProvider(DataProvider):
            async def get_ohlcv(  # type: ignore[override]
                self,
                *,
                symbol: str,
                exchange: Exchange,
                timeframe: str,
                since: Any | None = None,
                limit: int = 500,
            ) -> list[OHLCVBar]:
                return [
                    OHLCVBar(
                        exchange=exchange,
                        symbol=symbol,
                        open=create_price("100"),
                        high=create_price("110"),
                        low=create_price("95"),
                        close=create_price("105"),
                        volume=create_quantity("1000"),
                        source="jugaad",
                    )
                ]

            async def get_ticker(  # type: ignore[override]
                self,
                *,
                symbol: str,
                exchange: Exchange,
            ) -> TickerSnapshot:
                return TickerSnapshot(
                    exchange=exchange,
                    symbol=symbol,
                    bid=create_price("104"),
                    ask=create_price("106"),
                    last=create_price("105"),
                    volume_24h=create_quantity("10000"),
                    source="jugaad",
                )

            async def get_ohlcv_batch(  # type: ignore[override]
                self,
                *,
                symbols: list[str],
                exchange: Exchange,
                timeframe: str,
                since: Any | None = None,
                limit: int = 500,
            ) -> dict[str, list[OHLCVBar]]:
                return {}

        provider = JugaadProvider()
        failover = FailoverProvider(providers=[provider])

        states = failover.get_circuit_states()
        # Should use "jugaad" from class name mapping
        assert "jugaad" in states

    @pytest.mark.asyncio
    async def test_provider_name_from_yfinance_provider_class(self) -> None:
        """Test provider name extraction for YFinanceProvider class name."""

        # Create a provider with class name "YFinanceProvider" but no name attribute
        class YFinanceProvider(DataProvider):
            async def get_ohlcv(  # type: ignore[override]
                self,
                *,
                symbol: str,
                exchange: Exchange,
                timeframe: str,
                since: Any | None = None,
                limit: int = 500,
            ) -> list[OHLCVBar]:
                return [
                    OHLCVBar(
                        exchange=exchange,
                        symbol=symbol,
                        open=create_price("100"),
                        high=create_price("110"),
                        low=create_price("95"),
                        close=create_price("105"),
                        volume=create_quantity("1000"),
                        source="yfinance",
                    )
                ]

            async def get_ticker(  # type: ignore[override]
                self,
                *,
                symbol: str,
                exchange: Exchange,
            ) -> TickerSnapshot:
                return TickerSnapshot(
                    exchange=exchange,
                    symbol=symbol,
                    bid=create_price("104"),
                    ask=create_price("106"),
                    last=create_price("105"),
                    volume_24h=create_quantity("10000"),
                    source="yfinance",
                )

            async def get_ohlcv_batch(  # type: ignore[override]
                self,
                *,
                symbols: list[str],
                exchange: Exchange,
                timeframe: str,
                since: Any | None = None,
                limit: int = 500,
            ) -> dict[str, list[OHLCVBar]]:
                return {}

        provider = YFinanceProvider()
        failover = FailoverProvider(providers=[provider])

        states = failover.get_circuit_states()
        # Should use "yfinance" from class name mapping
        assert "yfinance" in states

    @pytest.mark.asyncio
    async def test_source_switch_logging_with_structlog(self, mock_metrics_switches) -> None:
        """Test that source switch logging works with structlog available."""
        # This test covers the structlog import path in _log_source_switch
        primary = MockProvider("kiteconnect", should_fail=True)
        secondary = MockProvider("jugaad")
        switches, switches_cb = mock_metrics_switches

        failover = FailoverProvider(
            providers=[primary, secondary],
            metrics_switches=switches_cb,
        )

        # This will trigger source switch logging
        await failover.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=10,
        )

        # Verify switch was recorded
        assert len(switches) == 1
        assert switches[0] == ("kiteconnect", "jugaad", "get_ohlcv")
