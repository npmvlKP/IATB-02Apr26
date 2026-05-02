"""
Failover data provider with circuit-breaker pattern.

This provider implements automatic failover across multiple data sources
with circuit-breaker pattern to prevent cascading failures. It maintains
ordered fallback providers (Kite → Jugaad → YFinance) and switches
sources on failure with configurable cooldown periods.

Key features:
- Ordered provider fallback: Primary tried first, falls back on failure
- Circuit state management: Open/closed states with configurable cooldown
- Source tagging: Every response tagged with actual source for audit
- Warning-level logging: Logs source switches at WARNING level
- Prometheus metrics: Tracks switches and latency per source
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import Timestamp
from iatb.data.base import DataProvider, OHLCVBar, TickerSnapshot
from iatb.data.rate_limiter import CircuitState

# Re-export CircuitState for backward compatibility
__all__ = ["FailoverProvider", "CircuitState", "CircuitBreaker", "ProviderRecord"]

# Default circuit breaker cooldown period (60 seconds)
_DEFAULT_COOLDOWN_SECONDS = 60.0
# Default failure threshold before opening circuit
_DEFAULT_FAILURE_THRESHOLD = 5


@dataclass(frozen=True)
class ProviderRecord:
    """Record of a provider attempt with timing information."""

    provider_name: str
    success: bool
    latency_seconds: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class CircuitBreaker:
    """Synchronous circuit breaker for FailoverProvider.

    Implements a three-state circuit breaker (CLOSED, OPEN, HALF_OPEN) with
    configurable failure threshold and cooldown period.

    Features:
    - Configurable failure threshold (default: 5 failures)
    - Cooldown period before retry (default: 60 seconds)
    - Three states: CLOSED, OPEN, HALF_OPEN (for recovery probing)
    - Automatic state transitions based on failures and cooldown

    State transitions:
    - CLOSED -> OPEN: When failure count reaches threshold
    - OPEN -> HALF_OPEN: When cooldown period expires
    - HALF_OPEN -> CLOSED: On successful request
    - HALF_OPEN -> OPEN: On failed request
    """

    def __init__(
        self,
        *,
        provider_name: str,
        cooldown_seconds: float = _DEFAULT_COOLDOWN_SECONDS,
        failure_threshold: int = _DEFAULT_FAILURE_THRESHOLD,
    ) -> None:
        """Initialize circuit breaker.

        Args:
            provider_name: Name of the provider this circuit monitors.
            cooldown_seconds: Cooldown period in seconds after circuit opens.
                Default: 60 seconds.
            failure_threshold: Number of consecutive failures before opening.
                Default: 5 failures.

        Raises:
            ValueError: If parameters are invalid.
        """
        if cooldown_seconds <= 0:
            msg = "cooldown_seconds must be positive"
            raise ValueError(msg)
        if failure_threshold <= 0:
            msg = "failure_threshold must be positive"
            raise ValueError(msg)

        self._provider_name = provider_name
        self._cooldown_seconds = cooldown_seconds
        self._failure_threshold = failure_threshold
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: datetime | None = None

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return self._provider_name

    @property
    def cooldown_seconds(self) -> float:
        """Get cooldown seconds."""
        return self._cooldown_seconds

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count

    @property
    def last_failure_time(self) -> datetime | None:
        """Get last failure time."""
        return self._last_failure_time

    def record_failure(self) -> None:
        """Record a provider failure and update circuit state.

        Increments failure count and potentially opens circuit if threshold
        is reached. If in HALF_OPEN state, immediately opens circuit.
        """
        self._failure_count += 1
        self._last_failure_time = datetime.now(UTC)

        if self._state == CircuitState.HALF_OPEN:
            # Failure in HALF_OPEN means recovery failed, open circuit
            self._state = CircuitState.OPEN
        elif self._failure_count >= self._failure_threshold:
            # Threshold reached, open circuit
            self._state = CircuitState.OPEN

    def record_success(self) -> None:
        """Record a provider success and update circuit state.

        Resets failure count. If in HALF_OPEN state, closes circuit
        indicating successful recovery.
        """
        self._failure_count = 0

        if self._state == CircuitState.HALF_OPEN:
            # Successful recovery, close circuit
            self._state = CircuitState.CLOSED
            self._last_failure_time = None
        elif self._state == CircuitState.OPEN:
            # Success while OPEN shouldn't normally happen, but reset anyway
            self._state = CircuitState.CLOSED
            self._last_failure_time = None

    def is_available(self) -> bool:
        """Check if provider is available for requests.

        Returns:
            True if circuit is CLOSED or HALF_OPEN, or if OPEN but cooldown
            has expired (transitions to HALF_OPEN). False if OPEN and in
            cooldown period.
        """
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.HALF_OPEN:
            return True

        # State is OPEN, check if cooldown has expired
        if self._last_failure_time is None:
            return True

        elapsed = (datetime.now(UTC) - self._last_failure_time).total_seconds()
        if elapsed >= self._cooldown_seconds:
            # Cooldown expired, transition to HALF_OPEN for recovery probe
            self._state = CircuitState.HALF_OPEN
            return True

        return False


class FailoverProvider(DataProvider):
    """Failover data provider with circuit-breaker pattern.

    This provider wraps multiple data providers in a failover chain with
    automatic source switching on failure. It maintains circuit-breaker
    state for each provider to prevent cascading failures and provides
    observability through logging and metrics.

    Example:
        providers = [KiteProvider(...), JugaadProvider(), YFinanceProvider()]
        failover = FailoverProvider(providers=providers)

        # First attempt uses Kite, falls back to Jugaad on failure
        bars = await failover.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=100
        )
        # bars[0].source == "kiteconnect" or "jugaad" or "yfinance"
    """

    def __init__(
        self,
        *,
        providers: list[DataProvider],
        cooldown_seconds: float = _DEFAULT_COOLDOWN_SECONDS,
        failure_threshold: int = _DEFAULT_FAILURE_THRESHOLD,
        metrics_switches: Callable[[str, str, str], None] | None = None,
        metrics_latency: Callable[[str, str, float], None] | None = None,
    ) -> None:
        """Initialize failover provider with ordered provider list.

        Args:
            providers: Ordered list of providers (primary first).
                Must not be empty.
            cooldown_seconds: Circuit breaker cooldown period in seconds.
                Default: 60 seconds.
            failure_threshold: Number of consecutive failures before opening circuit.
                Default: 5 failures.
            metrics_switches: Optional callback to record source switches.
                Called with (from_provider, to_provider, method_name).
            metrics_latency: Optional callback to record provider latency.
                Called with (provider_name, method_name, latency_seconds).

        Raises:
            ConfigError: If providers list is empty or parameters invalid.
        """
        if not providers:
            msg = "providers list cannot be empty"
            raise ConfigError(msg)
        if cooldown_seconds <= 0:
            msg = "cooldown_seconds must be positive"
            raise ConfigError(msg)
        if failure_threshold <= 0:
            msg = "failure_threshold must be positive"
            raise ConfigError(msg)

        self._providers = providers
        self._cooldown_seconds = cooldown_seconds
        self._failure_threshold = failure_threshold
        self._metrics_switches = metrics_switches
        self._metrics_latency = metrics_latency

        # Create circuit breakers for each provider
        self._circuits = self._initialize_circuits(providers, cooldown_seconds, failure_threshold)

    def _initialize_circuits(
        self,
        providers: list[DataProvider],
        cooldown_seconds: float,
        failure_threshold: int,
    ) -> dict[str, CircuitBreaker]:
        """Initialize circuit breakers for all providers.

        Args:
            providers: List of providers.
            cooldown_seconds: Circuit breaker cooldown period.
            failure_threshold: Failure threshold for opening circuits.

        Returns:
            Dictionary mapping provider names to circuit breakers.
        """
        circuits: dict[str, CircuitBreaker] = {}
        for idx, provider in enumerate(providers):
            provider_name = self._get_provider_name(provider, idx)
            circuits[provider_name] = CircuitBreaker(
                provider_name=provider_name,
                cooldown_seconds=cooldown_seconds,
                failure_threshold=failure_threshold,
            )
        return circuits

    async def get_ohlcv(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: Timestamp | None = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        """Fetch OHLCV bars with automatic failover.

        Tries providers in order, falling back on failure. Skips providers
        with open circuits (in cooldown period). Updates circuit states
        based on success/failure.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE").
            exchange: Exchange (NSE, BSE, etc.).
            timeframe: Timeframe (1m, 5m, 15m, 30m, 1h, 1d).
            since: Optional timestamp to filter from.
            limit: Maximum number of bars to return.

        Returns:
            List of normalized OHLCVBar objects with source tag.

        Raises:
            ConfigError: If all providers fail or are in cooldown.
        """
        result = await self._execute_with_failover(
            method_name="get_ohlcv",
            method_call=lambda p: p.get_ohlcv(
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
                since=since,
                limit=limit,
            ),
        )
        return cast("list[OHLCVBar]", result)

    async def get_ticker(
        self,
        *,
        symbol: str,
        exchange: Exchange,
    ) -> TickerSnapshot:
        """Fetch ticker snapshot with automatic failover.

        Tries providers in order, falling back on failure. Skips providers
        with open circuits (in cooldown period). Updates circuit states
        based on success/failure.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE").
            exchange: Exchange (NSE, BSE, etc.).

        Returns:
            Normalized TickerSnapshot with source tag.

        Raises:
            ConfigError: If all providers fail or are in cooldown.
        """
        result = await self._execute_with_failover(
            method_name="get_ticker",
            method_call=lambda p: p.get_ticker(symbol=symbol, exchange=exchange),
        )
        return cast("TickerSnapshot", result)

    async def get_ohlcv_batch(
        self,
        *,
        symbols: list[str],
        exchange: Exchange,
        timeframe: str,
        since: Timestamp | None = None,
        limit: int = 500,
    ) -> dict[str, list[OHLCVBar]]:
        """Fetch OHLCV bars for multiple symbols with automatic failover.

        Tries providers in order, falling back on failure. Skips providers
        with open circuits (in cooldown period). Updates circuit states
        based on success/failure.

        Args:
            symbols: List of trading symbols.
            exchange: Exchange (NSE, BSE, etc.).
            timeframe: Timeframe (1m, 5m, 15m, 30m, 1h, 1d).
            since: Optional timestamp to filter from.
            limit: Maximum number of bars to return per symbol.

        Returns:
            Dictionary mapping symbols to OHLCVBar lists with source tags.

        Raises:
            ConfigError: If all providers fail or are in cooldown.
        """
        result = await self._execute_with_failover(
            method_name="get_ohlcv_batch",
            method_call=lambda p: p.get_ohlcv_batch(
                symbols=symbols,
                exchange=exchange,
                timeframe=timeframe,
                since=since,
                limit=limit,
            ),
        )
        return cast("dict[str, list[OHLCVBar]]", result)

    async def _execute_with_failover(
        self,
        *,
        method_name: str,
        method_call: Callable[[DataProvider], Any],
    ) -> Any:
        """Execute method call with automatic failover across providers.

        Args:
            method_name: Name of the method being called (for logging/metrics).
            method_call: Callable that accepts a provider and returns a coroutine.

        Returns:
            Result from first successful provider.

        Raises:
            ConfigError: If all providers fail or are in cooldown.
        """
        last_error: Exception | None = None
        last_provider_name: str | None = None

        for idx, provider in enumerate(self._providers):
            provider_name = self._get_provider_name(provider, idx)
            circuit = self._circuits[provider_name]

            # Skip if circuit is open (in cooldown)
            if not circuit.is_available():
                continue

            # Try this provider
            try:
                result = await self._try_provider(
                    provider=provider,
                    provider_name=provider_name,
                    circuit=circuit,
                    method_name=method_name,
                    method_call=method_call,
                    last_provider_name=last_provider_name,
                )
                return result

            except Exception as exc:
                # Record failure and continue to next provider
                circuit.record_failure()
                last_error = exc
                last_provider_name = provider_name

        # All providers failed
        self._raise_all_providers_failed(method_name, last_error)

    def _raise_all_providers_failed(
        self,
        method_name: str,
        last_error: Exception | None,
    ) -> None:
        """Raise error when all providers fail."""
        msg = f"All data providers failed for {method_name}. Last error: {last_error!s}"
        raise ConfigError(msg) from last_error

    async def _try_provider(
        self,
        *,
        provider: DataProvider,
        provider_name: str,
        circuit: CircuitBreaker,
        method_name: str,
        method_call: Callable[[DataProvider], Any],
        last_provider_name: str | None,
    ) -> Any:
        """Try executing method call on a single provider.

        Args:
            provider: The provider to try.
            provider_name: Name of the provider.
            circuit: Circuit breaker for this provider.
            method_name: Name of the method being called.
            method_call: Callable that accepts a provider and returns a coroutine.
            last_provider_name: Name of the previous provider (if any).

        Returns:
            Result from the provider.

        Raises:
            Exception: If the provider fails.
        """
        start_time = datetime.now(UTC)
        result = await method_call(provider)
        latency = (datetime.now(UTC) - start_time).total_seconds()

        # Record success and update metrics
        circuit.record_success()
        self._record_latency(provider_name, method_name, latency)

        # Log source switch if not the first provider
        if last_provider_name is not None:
            self._log_source_switch(
                from_provider=last_provider_name,
                to_provider=provider_name,
                method_name=method_name,
            )

        return result

    def _get_provider_name(self, provider: DataProvider, idx: int) -> str:
        """Get a descriptive name for the provider.

        Args:
            provider: The provider instance.
            idx: Index of provider in the list.

        Returns:
            Provider name string.
        """
        # Check if provider has a name attribute (e.g., MockProvider.name)
        if hasattr(provider, "name") and provider.name:
            return str(provider.name).lower()

        class_name = provider.__class__.__name__
        # Extract source name from common patterns
        if class_name == "KiteProvider":
            return "kiteconnect"
        if class_name == "JugaadProvider":
            return "jugaad"
        if class_name == "YFinanceProvider":
            return "yfinance"
        # Fallback to class name with index for uniqueness
        return f"{class_name.lower()}_{idx}"

    def _log_source_switch(
        self,
        *,
        from_provider: str,
        to_provider: str,
        method_name: str,
    ) -> None:
        """Log a source switch at WARNING level.

        Args:
            from_provider: Name of the provider that failed.
            to_provider: Name of the provider being switched to.
            method_name: Name of the method being called.
        """
        try:
            import structlog  # type: ignore[import-not-found]

            logger = structlog.get_logger()
            logger.warning(
                "Data provider switched",
                extra={
                    "from_provider": from_provider,
                    "to_provider": to_provider,
                    "method_name": method_name,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        except ImportError:
            # structlog not available, skip logging
            pass

        # Record switch in metrics
        if self._metrics_switches is not None:
            self._metrics_switches(from_provider, to_provider, method_name)

    def _record_latency(
        self,
        provider_name: str,
        method_name: str,
        latency_seconds: float,
    ) -> None:
        """Record provider latency in metrics.

        Args:
            provider_name: Name of the provider.
            method_name: Name of the method called.
            latency_seconds: Latency in seconds.
        """
        if self._metrics_latency is not None:
            self._metrics_latency(provider_name, method_name, latency_seconds)

    def get_circuit_states(self) -> dict[str, dict[str, Any]]:
        """Get current state of all circuit breakers.

        Returns:
            Dictionary mapping provider names to circuit state info.
        """
        return {
            name: {
                "state": circuit.state.name,
                "failure_count": circuit.failure_count,
                "last_failure_time": (
                    circuit.last_failure_time.isoformat() if circuit.last_failure_time else None
                ),
                "available": circuit.is_available(),
            }
            for name, circuit in self._circuits.items()
        }

    def reset_circuit(self, provider_name: str) -> None:
        """Manually reset a circuit breaker for a provider.

        Args:
            provider_name: Name of the provider to reset.

        Raises:
            ConfigError: If provider name not found.
        """
        if provider_name not in self._circuits:
            msg = f"Unknown provider name: {provider_name}"
            raise ConfigError(msg)

        circuit = self._circuits[provider_name]
        # Reset the circuit breaker state
        circuit._state = CircuitState.CLOSED
        circuit._failure_count = 0
        circuit._last_failure_time = None
