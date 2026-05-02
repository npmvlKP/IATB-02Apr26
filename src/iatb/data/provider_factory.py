"""
Factory for creating configured data provider chains with failover.

This module provides a unified factory for creating production-ready data
provider instances with proper dependency injection:
- KiteProvider (primary) with ZerodhaTokenManager
- JugaadProvider (fallback)
- FailoverProvider wrapping both
- SymbolTokenResolver integration
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from iatb.broker.token_manager import ZerodhaTokenManager
from iatb.core.exceptions import ConfigError
from iatb.data.failover_provider import FailoverProvider
from iatb.data.instrument_master import InstrumentMaster
from iatb.data.jugaad_provider import JugaadProvider
from iatb.data.kite_provider import KiteProvider
from iatb.data.kite_ws_provider import KiteWebSocketProvider
from iatb.data.rate_limiter import CircuitBreaker, RateLimiter, RetryConfig
from iatb.data.token_resolver import SymbolTokenResolver

if TYPE_CHECKING:
    from iatb.data.base import DataProvider


@dataclass(frozen=True)
class ProviderChain:
    """Complete data provider chain with all components."""

    primary_provider: KiteProvider
    fallback_provider: JugaadProvider
    failover_provider: FailoverProvider
    ws_provider: KiteWebSocketProvider
    token_manager: ZerodhaTokenManager
    token_resolver: SymbolTokenResolver
    instrument_master: InstrumentMaster


class DataProviderFactory:
    """Factory for creating configured data provider chains.

    This factory provides a single entry point for creating production-ready
    data provider instances with proper failover configuration and token management.

    Example:
        factory = DataProviderFactory(
            api_key="xxx",
            api_secret="yyy",
            totp_secret="zzz",
            cache_dir=Path("/path/to/cache")
        )
        chain = factory.create_provider_chain()
        scanner = InstrumentScanner(data_provider=chain.failover_provider)
    """

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        totp_secret: str | None = None,
        cache_dir: Path | None = None,
        env_path: Path | None = None,
        kite_provider_factory: Callable[[str, str], KiteProvider] | None = None,
        jugaad_provider_factory: Callable[[], JugaadProvider] | None = None,
    ) -> None:
        """Initialize data provider factory.

        Args:
            api_key: Zerodha API key.
            api_secret: Zerodha API secret.
            totp_secret: TOTP secret for 2FA (optional).
            cache_dir: Directory for instrument master cache (optional).
            env_path: Path to .env file for session persistence (optional).
            kite_provider_factory: Optional factory for creating KiteProvider.
            jugaad_provider_factory: Optional factory for creating JugaadProvider.

        Raises:
            ConfigError: If required parameters are invalid.
        """
        self._validate_params(api_key, api_secret, cache_dir)

        self._api_key = api_key
        self._api_secret = api_secret
        self._totp_secret = totp_secret
        self._cache_dir = cache_dir or Path.cwd() / "cache" / "instruments"
        self._env_path = env_path
        self._kite_provider_factory = kite_provider_factory
        self._jugaad_provider_factory = jugaad_provider_factory

    @staticmethod
    def _validate_params(api_key: str, api_secret: str, cache_dir: Path | None) -> None:
        """Validate factory parameters.

        Raises:
            ConfigError: If parameters are invalid.
        """
        if not api_key.strip():
            msg = "api_key cannot be empty"
            raise ConfigError(msg)
        if not api_secret.strip():
            msg = "api_secret cannot be empty"
            raise ConfigError(msg)
        if cache_dir is not None and not cache_dir.parent.exists():
            msg = f"Cache directory parent does not exist: {cache_dir.parent}"
            raise ConfigError(msg)

    def create_token_manager(self) -> ZerodhaTokenManager:
        """Create ZerodhaTokenManager instance.

        Returns:
            Configured ZerodhaTokenManager.
        """
        return ZerodhaTokenManager(
            api_key=self._api_key,
            api_secret=self._api_secret,
            totp_secret=self._totp_secret,
            env_path=self._env_path,
        )

    def create_instrument_master(self) -> InstrumentMaster:
        """Create InstrumentMaster instance for caching instrument data.

        Returns:
            Configured InstrumentMaster.
        """
        # Ensure cache directory exists
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        return InstrumentMaster(cache_dir=self._cache_dir)

    def _get_access_token(self, token_manager: ZerodhaTokenManager | None) -> str:
        """Get access token from token manager or create one."""
        tm = token_manager or self.create_token_manager()

        # Get access token
        access_token = tm.get_access_token(use_env_fallback=True)
        if not access_token:
            msg = (
                "No access token available. Please authenticate using "
                "ZerodhaTokenManager.get_login_url() and exchange_request_token()"
            )
            raise ConfigError(msg)

        return access_token

    def _create_rate_limiter(self, rate_limiter: RateLimiter | None) -> RateLimiter:
        """Create rate limiter with default values if not provided."""
        return rate_limiter or RateLimiter(
            requests_per_second=3.0,
            burst_capacity=10,
        )

    def _create_circuit_breaker(
        self,
        circuit_breaker: CircuitBreaker | None,
    ) -> CircuitBreaker:
        """Create circuit breaker with default values if not provided."""
        return circuit_breaker or CircuitBreaker(
            failure_threshold=5,
            reset_timeout=60.0,
        )

    def _create_retry_config(self, retry_config: RetryConfig | None) -> RetryConfig:
        """Create retry config with default values if not provided."""
        return retry_config or RetryConfig()

    def create_kite_provider(
        self,
        token_manager: ZerodhaTokenManager | None = None,
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        retry_config: RetryConfig | None = None,
    ) -> KiteProvider:
        """Create KiteProvider instance.

        Args:
            token_manager: Optional ZerodhaTokenManager. If not provided,
                will create a new one.
            rate_limiter: Optional rate limiter instance. If not provided,
                creates default RateLimiter(3, burst_capacity=10).
            circuit_breaker: Optional circuit breaker instance. If not provided,
                creates default CircuitBreaker(5, 60.0).
            retry_config: Optional retry configuration. If not provided,
                creates default RetryConfig().

        Returns:
            Configured KiteProvider.

        Raises:
            ConfigError: If access token cannot be obtained.
        """
        access_token = self._get_access_token(token_manager)

        # Create rate limiter, circuit breaker, and retry config if not provided
        rl = self._create_rate_limiter(rate_limiter)
        cb = self._create_circuit_breaker(circuit_breaker)
        rc = self._create_retry_config(retry_config)

        if self._kite_provider_factory:
            return self._kite_provider_factory(self._api_key, access_token)

        return KiteProvider(
            api_key=self._api_key,
            access_token=access_token,
            rate_limiter=rl,
            circuit_breaker=cb,
            retry_config=rc,
        )  # type: ignore[abstract]

    def create_jugaad_provider(self) -> JugaadProvider:
        """Create JugaadProvider instance.

        Returns:
            Configured JugaadProvider.
        """
        if self._jugaad_provider_factory:
            return self._jugaad_provider_factory()

        return JugaadProvider()  # type: ignore[abstract]

    def create_failover_provider(
        self,
        primary: KiteProvider | None = None,
        fallback: JugaadProvider | None = None,
        cooldown_seconds: float = 30.0,
    ) -> FailoverProvider:
        """Create FailoverProvider with Kite (primary) and Jugaad (fallback).

        Args:
            primary: Optional KiteProvider. If not provided, will create one.
            fallback: Optional JugaadProvider. If not provided, will create one.
            cooldown_seconds: Circuit breaker cooldown period in seconds.

        Returns:
            Configured FailoverProvider.
        """
        kite = primary or self.create_kite_provider()
        jugaad = fallback or self.create_jugaad_provider()

        return FailoverProvider(
            providers=[kite, jugaad],
            cooldown_seconds=cooldown_seconds,
        )

    def create_token_resolver(
        self,
        instrument_master: InstrumentMaster | None = None,
        kite_provider: KiteProvider | None = None,
    ) -> SymbolTokenResolver:
        """Create SymbolTokenResolver for symbol-to-token resolution.

        Args:
            instrument_master: Optional InstrumentMaster. If not provided,
                will create one.
            kite_provider: Optional KiteProvider for API fallback.

        Returns:
            Configured SymbolTokenResolver.
        """
        im = instrument_master or self.create_instrument_master()

        # KiteProvider is optional for token resolver
        # If not provided, cache misses will raise ConfigError
        return SymbolTokenResolver(instrument_master=im, kite_provider=kite_provider)

    def create_ws_provider(
        self,
        token_manager: ZerodhaTokenManager | None = None,
        token_resolver: SymbolTokenResolver | None = None,
        instrument_master: InstrumentMaster | None = None,
    ) -> KiteWebSocketProvider:
        """Create KiteWebSocketProvider for real-time market data.

        Args:
            token_manager: Optional ZerodhaTokenManager. If not provided,
                will create a new one.
            token_resolver: Optional SymbolTokenResolver for exchange resolution.
            instrument_master: Optional InstrumentMaster for token->exchange resolution.

        Returns:
            Configured KiteWebSocketProvider.
        """
        tm = token_manager or self.create_token_manager()
        tr = token_resolver or self.create_token_resolver(
            kite_provider=self.create_kite_provider(tm),
        )
        im = instrument_master or self.create_instrument_master()
        access_token = self._get_access_token(tm)

        return KiteWebSocketProvider(
            api_key=self._api_key,
            access_token=access_token,
            token_resolver=tr,
            instrument_master=im,
        )

    def _create_core_components(
        self,
    ) -> tuple[
        ZerodhaTokenManager,
        InstrumentMaster,
        KiteProvider,
        JugaadProvider,
    ]:
        """Create core provider chain components.

        Returns:
            Tuple of (token_manager, instrument_master, primary, fallback).
        """
        token_manager = self.create_token_manager()
        instrument_master = self.create_instrument_master()
        primary = self.create_kite_provider(token_manager=token_manager)
        fallback = self.create_jugaad_provider()
        return token_manager, instrument_master, primary, fallback

    def _create_failover_with_resolver(
        self,
        primary: KiteProvider,
        fallback: JugaadProvider,
        instrument_master: InstrumentMaster,
        cooldown_seconds: float,
    ) -> tuple[FailoverProvider, SymbolTokenResolver]:
        """Create failover provider and token resolver.

        Args:
            primary: Primary KiteProvider.
            fallback: Fallback JugaadProvider.
            instrument_master: InstrumentMaster instance.
            cooldown_seconds: Circuit breaker cooldown period.

        Returns:
            Tuple of (failover_provider, token_resolver).
        """
        failover = self.create_failover_provider(
            primary=primary,
            fallback=fallback,
            cooldown_seconds=cooldown_seconds,
        )
        token_resolver = self.create_token_resolver(
            instrument_master=instrument_master,
            kite_provider=primary,
        )
        return failover, token_resolver

    def create_provider_chain(
        self,
        cooldown_seconds: float = 30.0,
    ) -> ProviderChain:
        """Create complete provider chain with all components.

        This is the recommended method for getting a fully configured
        data provider stack.

        Args:
            cooldown_seconds: Circuit breaker cooldown period in seconds.

        Returns:
            ProviderChain with all components.

        Raises:
            ConfigError: If any component creation fails.
        """
        # Create core components
        token_manager, instrument_master, primary, fallback = self._create_core_components()

        # Create failover and resolver
        failover, token_resolver = self._create_failover_with_resolver(
            primary,
            fallback,
            instrument_master,
            cooldown_seconds,
        )

        # Create WebSocket provider with token resolver and instrument master
        ws_provider = self.create_ws_provider(
            token_manager=token_manager,
            token_resolver=token_resolver,
            instrument_master=instrument_master,
        )

        return ProviderChain(
            primary_provider=primary,
            fallback_provider=fallback,
            failover_provider=failover,
            ws_provider=ws_provider,
            token_manager=token_manager,
            token_resolver=token_resolver,
            instrument_master=instrument_master,
        )

    @classmethod
    def from_env(
        cls,
        *,
        api_key_env_var: str = "ZERODHA_API_KEY",  # noqa: S107
        api_secret_env_var: str = "ZERODHA_API_SECRET",  # noqa: S107
        totp_secret_env_var: str = "ZERODHA_TOTP_SECRET",  # noqa: S107
        cache_dir: Path | None = None,
        env_path: Path | None = None,
    ) -> DataProviderFactory:
        """Create factory from environment variables.

        Args:
            api_key_env_var: Environment variable name for API key.
            api_secret_env_var: Environment variable name for API secret.
            totp_secret_env_var: Environment variable name for TOTP secret.
            cache_dir: Directory for instrument master cache (optional).
            env_path: Path to .env file for session persistence (optional).

        Returns:
            Configured DataProviderFactory.

        Raises:
            ConfigError: If required environment variables not set.
        """
        import os

        api_key = os.getenv(api_key_env_var, "").strip()
        api_secret = os.getenv(api_secret_env_var, "").strip()
        totp_secret = os.getenv(totp_secret_env_var, "").strip() or None

        if not api_key:
            msg = f"{api_key_env_var} environment variable is required"
            raise ConfigError(msg)
        if not api_secret:
            msg = f"{api_secret_env_var} environment variable is required"
            raise ConfigError(msg)

        return cls(
            api_key=api_key,
            api_secret=api_secret,
            totp_secret=totp_secret,
            cache_dir=cache_dir,
            env_path=env_path,
        )

    def get_data_provider(self) -> DataProvider:
        """Get the failover data provider for direct use.

        This is a convenience method for getting the DataProvider instance
        directly without needing to access the full ProviderChain.

        Returns:
            FailoverProvider instance.
        """
        chain = self.create_provider_chain()
        return chain.failover_provider
