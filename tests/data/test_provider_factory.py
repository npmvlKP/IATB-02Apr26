"""
Tests for DataProviderFactory and ProviderChain.

These tests verify the factory creates properly configured data provider
chains with failover, token management, and symbol resolution.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from iatb.broker.token_manager import ZerodhaTokenManager
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.data.base import OHLCVBar
from iatb.data.failover_provider import FailoverProvider
from iatb.data.instrument_master import InstrumentMaster
from iatb.data.jugaad_provider import JugaadProvider
from iatb.data.kite_provider import KiteProvider
from iatb.data.provider_factory import DataProviderFactory, ProviderChain
from iatb.data.token_resolver import SymbolTokenResolver


@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> Path:
    """Create a temporary cache directory for tests."""
    cache_dir = tmp_path / "cache" / "instruments"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


@pytest.fixture
def mock_token_manager() -> ZerodhaTokenManager:
    """Create a mock ZerodhaTokenManager."""
    tm = MagicMock(spec=ZerodhaTokenManager)
    tm.get_access_token.return_value = "test_access_token"
    return tm


@pytest.fixture
def mock_kite_provider() -> KiteProvider:
    """Create a mock KiteProvider."""
    provider = MagicMock(spec=KiteProvider)

    # Mock get_ohlcv to return valid data
    async def mock_get_ohlcv(*args: Any, **kwargs: Any) -> list[OHLCVBar]:
        return [
            OHLCVBar(
                exchange=Exchange.NSE,
                symbol="RELIANCE",
                timeframe="1d",
                open=Decimal("1000"),
                high=Decimal("1100"),
                low=Decimal("950"),
                close=Decimal("1050"),
                volume=Decimal("1000000"),
                source="test",
            )
        ]

    provider.get_ohlcv = mock_get_ohlcv
    return provider


@pytest.fixture
def mock_jugaad_provider() -> JugaadProvider:
    """Create a mock JugaadProvider."""
    provider = MagicMock(spec=JugaadProvider)

    # Mock get_ohlcv to return valid data
    async def mock_get_ohlcv(*args: Any, **kwargs: Any) -> list[OHLCVBar]:
        return [
            OHLCVBar(
                exchange=Exchange.NSE,
                symbol="RELIANCE",
                timeframe="1d",
                open=Decimal("1000"),
                high=Decimal("1100"),
                low=Decimal("950"),
                close=Decimal("1050"),
                volume=Decimal("1000000"),
                source="test",
            )
        ]

    provider.get_ohlcv = mock_get_ohlcv
    return provider


class TestDataProviderFactory:
    """Test DataProviderFactory initialization and configuration."""

    def test_factory_initialization_with_valid_params(self, temp_cache_dir: Path) -> None:
        """Test factory initializes with valid parameters."""
        factory = DataProviderFactory(
            api_key="test_api_key",
            api_secret="test_api_secret",
            cache_dir=temp_cache_dir,
        )
        assert factory._api_key == "test_api_key"
        assert factory._api_secret == "test_api_secret"
        assert factory._cache_dir == temp_cache_dir

    def test_factory_initialization_with_empty_api_key(self, temp_cache_dir: Path) -> None:
        """Test factory rejects empty API key."""
        with pytest.raises(ConfigError, match="api_key cannot be empty"):
            DataProviderFactory(
                api_key="",
                api_secret="test_api_secret",
                cache_dir=temp_cache_dir,
            )

    def test_factory_initialization_with_empty_api_secret(self, temp_cache_dir: Path) -> None:
        """Test factory rejects empty API secret."""
        with pytest.raises(ConfigError, match="api_secret cannot be empty"):
            DataProviderFactory(
                api_key="test_api_key",
                api_secret="",
                cache_dir=temp_cache_dir,
            )

    def test_factory_initialization_with_invalid_cache_dir(self) -> None:
        """Test factory rejects invalid cache directory."""
        invalid_path = Path("/nonexistent/path/to/cache")
        with pytest.raises(ConfigError, match="Cache directory parent does not exist"):
            DataProviderFactory(
                api_key="test_api_key",
                api_secret="test_api_secret",
                cache_dir=invalid_path,
            )

    @patch.dict("os.environ", {"ZERODHA_API_KEY": "env_key", "ZERODHA_API_SECRET": "env_secret"})
    def test_factory_from_env(self) -> None:
        """Test factory creation from environment variables."""
        factory = DataProviderFactory.from_env()
        assert factory._api_key == "env_key"
        assert factory._api_secret == "env_secret"

    @patch.dict("os.environ", {}, clear=True)
    def test_factory_from_env_missing_api_key(self) -> None:
        """Test factory from_env fails without API key."""
        with pytest.raises(ConfigError, match="ZERODHA_API_KEY environment variable is required"):
            DataProviderFactory.from_env()

    @patch.dict("os.environ", {"ZERODHA_API_KEY": "env_key"}, clear=True)
    def test_factory_from_env_missing_api_secret(self) -> None:
        """Test factory from_env fails without API secret."""
        expected_msg = "ZERODHA_API_SECRET environment variable is required"
        with pytest.raises(ConfigError, match=expected_msg):
            DataProviderFactory.from_env()


class TestTokenManagerCreation:
    """Test ZerodhaTokenManager creation through factory."""

    def test_create_token_manager(self, temp_cache_dir: Path) -> None:
        """Test token manager creation."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
        )
        tm = factory.create_token_manager()
        assert isinstance(tm, ZerodhaTokenManager)


class TestInstrumentMasterCreation:
    """Test InstrumentMaster creation through factory."""

    def test_create_instrument_master(self, temp_cache_dir: Path) -> None:
        """Test instrument master creation."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
        )
        im = factory.create_instrument_master()
        assert isinstance(im, InstrumentMaster)
        assert im._db_path == temp_cache_dir / "instruments.sqlite"


class TestKiteProviderCreation:
    """Test KiteProvider creation through factory."""

    def test_create_kite_provider_with_token_manager(
        self,
        temp_cache_dir: Path,
        mock_token_manager: ZerodhaTokenManager,
    ) -> None:
        """Test KiteProvider creation with token manager."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
        )
        factory.create_kite_provider(token_manager=mock_token_manager)
        # With mock, we can't verify the actual KiteProvider instance
        # but we can verify it was called
        mock_token_manager.get_access_token.assert_called_once_with(
            use_env_fallback=True,
        )

    def test_create_kite_provider_without_access_token(
        self,
        temp_cache_dir: Path,
    ) -> None:
        """Test KiteProvider creation fails without access token."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
        )
        # Create a mock token manager that returns None
        tm = MagicMock(spec=ZerodhaTokenManager)
        tm.get_access_token.return_value = None

        with pytest.raises(ConfigError, match="No access token available"):
            factory.create_kite_provider(token_manager=tm)


class TestJugaadProviderCreation:
    """Test JugaadProvider creation through factory."""

    def test_create_jugaad_provider(self, temp_cache_dir: Path) -> None:
        """Test JugaadProvider creation."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
        )
        provider = factory.create_jugaad_provider()
        assert isinstance(provider, JugaadProvider)


class TestFailoverProviderCreation:
    """Test FailoverProvider creation through factory."""

    def test_create_failover_provider(
        self,
        temp_cache_dir: Path,
        mock_token_manager: ZerodhaTokenManager,
        mock_kite_provider: KiteProvider,
        mock_jugaad_provider: JugaadProvider,
    ) -> None:
        """Test failover provider creation."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
            kite_provider_factory=lambda api_key, token: mock_kite_provider,
            jugaad_provider_factory=lambda: mock_jugaad_provider,
        )

        failover = factory.create_failover_provider(cooldown_seconds=45.0)
        assert isinstance(failover, FailoverProvider)


class TestTokenResolverCreation:
    """Test SymbolTokenResolver creation through factory."""

    def test_create_token_resolver(self, temp_cache_dir: Path) -> None:
        """Test token resolver creation."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
        )
        resolver = factory.create_token_resolver()
        assert isinstance(resolver, SymbolTokenResolver)


class TestProviderChainCreation:
    """Test complete provider chain creation."""

    @pytest.mark.asyncio
    async def test_create_provider_chain(
        self,
        temp_cache_dir: Path,
        mock_token_manager: ZerodhaTokenManager,
        mock_kite_provider: KiteProvider,
        mock_jugaad_provider: JugaadProvider,
    ) -> None:
        """Test complete provider chain creation."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
            kite_provider_factory=lambda api_key, token: mock_kite_provider,
            jugaad_provider_factory=lambda: mock_jugaad_provider,
        )

        chain = factory.create_provider_chain(cooldown_seconds=60.0)

        assert isinstance(chain, ProviderChain)
        assert chain.primary_provider is not None
        assert chain.fallback_provider is not None
        assert chain.failover_provider is not None
        assert chain.token_manager is not None
        assert chain.token_resolver is not None
        assert chain.instrument_master is not None

    @pytest.mark.asyncio
    async def test_get_data_provider(
        self,
        temp_cache_dir: Path,
        mock_token_manager: ZerodhaTokenManager,
        mock_kite_provider: KiteProvider,
        mock_jugaad_provider: JugaadProvider,
    ) -> None:
        """Test get_data_provider convenience method."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
            kite_provider_factory=lambda api_key, token: mock_kite_provider,
            jugaad_provider_factory=lambda: mock_jugaad_provider,
        )

        provider = factory.get_data_provider()
        assert isinstance(provider, FailoverProvider)


class TestProviderChainIntegration:
    """Integration tests for ProviderChain."""

    @pytest.mark.asyncio
    async def test_provider_chain_end_to_end(
        self,
        temp_cache_dir: Path,
        mock_token_manager: ZerodhaTokenManager,
        mock_kite_provider: KiteProvider,
        mock_jugaad_provider: JugaadProvider,
    ) -> None:
        """Test end-to-end data flow through provider chain."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
            kite_provider_factory=lambda api_key, token: mock_kite_provider,
            jugaad_provider_factory=lambda: mock_jugaad_provider,
        )

        chain = factory.create_provider_chain()

        # Test failover provider works
        bars = await chain.failover_provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=10,
        )

        assert len(bars) > 0
        assert bars[0].symbol == "RELIANCE"
        assert bars[0].exchange == Exchange.NSE


class TestCreateCoreComponents:
    """Test _create_core_components method."""

    def test_create_core_components(
        self,
        temp_cache_dir: Path,
        mock_token_manager: ZerodhaTokenManager,
        mock_kite_provider: KiteProvider,
        mock_jugaad_provider: JugaadProvider,
    ) -> None:
        """Test core components creation."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
            kite_provider_factory=lambda api_key, token: mock_kite_provider,
            jugaad_provider_factory=lambda: mock_jugaad_provider,
        )

        token_manager, instrument_master, primary, fallback = factory._create_core_components()

        assert isinstance(token_manager, ZerodhaTokenManager)
        assert isinstance(instrument_master, InstrumentMaster)
        assert primary is not None
        assert fallback is not None


class TestCreateFailoverWithResolver:
    """Test _create_failover_with_resolver method."""

    def test_create_failover_with_resolver(
        self,
        temp_cache_dir: Path,
        mock_token_manager: ZerodhaTokenManager,
        mock_kite_provider: KiteProvider,
        mock_jugaad_provider: JugaadProvider,
    ) -> None:
        """Test failover and resolver creation."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
            kite_provider_factory=lambda api_key, token: mock_kite_provider,
            jugaad_provider_factory=lambda: mock_jugaad_provider,
        )

        failover, resolver = factory._create_failover_with_resolver(
            primary=mock_kite_provider,
            fallback=mock_jugaad_provider,
            instrument_master=factory.create_instrument_master(),
            cooldown_seconds=45.0,
        )

        assert isinstance(failover, FailoverProvider)
        assert isinstance(resolver, SymbolTokenResolver)


class TestProviderChainDataclass:
    """Test ProviderChain dataclass."""

    def test_provider_chain_immutability(
        self,
        temp_cache_dir: Path,
        mock_token_manager: ZerodhaTokenManager,
        mock_kite_provider: KiteProvider,
        mock_jugaad_provider: JugaadProvider,
    ) -> None:
        """Test ProviderChain is frozen/immutable."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
            kite_provider_factory=lambda api_key, token: mock_kite_provider,
            jugaad_provider_factory=lambda: mock_jugaad_provider,
        )

        chain = factory.create_provider_chain()

        # Verify all components are present
        assert chain.primary_provider is not None
        assert chain.fallback_provider is not None
        assert chain.failover_provider is not None
        assert chain.token_manager is not None
        assert chain.token_resolver is not None
        assert chain.instrument_master is not None

        # Verify ProviderChain is frozen
        with pytest.raises(FrozenInstanceError):
            chain.primary_provider = mock_kite_provider


class TestCustomFactories:
    """Test custom provider factories."""

    def test_factory_with_custom_kite_provider_factory(
        self,
        temp_cache_dir: Path,
        mock_kite_provider: KiteProvider,
    ) -> None:
        """Test factory with custom KiteProvider factory."""
        custom_factory_called = False

        def custom_kite_factory(api_key: str, token: str) -> KiteProvider:
            nonlocal custom_factory_called
            custom_factory_called = True
            assert api_key == "test_key"
            assert token == "test_token"
            return mock_kite_provider

        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
            kite_provider_factory=custom_kite_factory,
        )

        # Mock token manager to return token
        mock_tm = MagicMock(spec=ZerodhaTokenManager)
        mock_tm.get_access_token.return_value = "test_token"

        provider = factory.create_kite_provider(token_manager=mock_tm)
        assert custom_factory_called
        assert provider is mock_kite_provider

    def test_factory_with_custom_jugaad_provider_factory(
        self,
        temp_cache_dir: Path,
        mock_jugaad_provider: JugaadProvider,
    ) -> None:
        """Test factory with custom JugaadProvider factory."""
        custom_factory_called = False

        def custom_jugaad_factory() -> JugaadProvider:
            nonlocal custom_factory_called
            custom_factory_called = True
            return mock_jugaad_provider

        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
            jugaad_provider_factory=custom_jugaad_factory,
        )

        provider = factory.create_jugaad_provider()
        assert custom_factory_called
        assert provider is mock_jugaad_provider


class TestFailoverProviderWithCustomCooldown:
    """Test FailoverProvider with custom cooldown."""

    def test_create_failover_provider_custom_cooldown(
        self,
        temp_cache_dir: Path,
        mock_token_manager: ZerodhaTokenManager,
        mock_kite_provider: KiteProvider,
        mock_jugaad_provider: JugaadProvider,
    ) -> None:
        """Test failover provider creation with custom cooldown."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
            kite_provider_factory=lambda api_key, token: mock_kite_provider,
            jugaad_provider_factory=lambda: mock_jugaad_provider,
        )

        failover = factory.create_failover_provider(cooldown_seconds=120.0)
        assert isinstance(failover, FailoverProvider)
        # Cooldown is passed to FailoverProvider constructor


class TestTokenResolverWithKiteProvider:
    """Test token resolver creation with KiteProvider."""

    def test_create_token_resolver_with_kite_provider(
        self,
        temp_cache_dir: Path,
        mock_kite_provider: KiteProvider,
    ) -> None:
        """Test token resolver creation with KiteProvider."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
        )

        resolver = factory.create_token_resolver(
            kite_provider=mock_kite_provider,
        )
        assert isinstance(resolver, SymbolTokenResolver)


class TestFromEnvCustomVars:
    """Test from_env with custom environment variable names."""

    @patch.dict(
        "os.environ",
        {
            "CUSTOM_API_KEY": "custom_key",
            "CUSTOM_API_SECRET": "custom_secret",
            "CUSTOM_TOTP_SECRET": "custom_totp",
        },
    )
    def test_factory_from_env_custom_vars(
        self,
        temp_cache_dir: Path,
    ) -> None:
        """Test factory from_env with custom variable names."""
        factory = DataProviderFactory.from_env(
            api_key_env_var="CUSTOM_API_KEY",
            api_secret_env_var="CUSTOM_API_SECRET",
            totp_secret_env_var="CUSTOM_TOTP_SECRET",
            cache_dir=temp_cache_dir,
        )

        assert factory._api_key == "custom_key"
        assert factory._api_secret == "custom_secret"
        assert factory._totp_secret == "custom_totp"

    @patch.dict(
        "os.environ",
        {"ZERODHA_API_KEY": "env_key", "ZERODHA_API_SECRET": "env_secret"},
    )
    def test_factory_from_env_without_totp(
        self,
        temp_cache_dir: Path,
    ) -> None:
        """Test factory from_env without TOTP secret."""
        factory = DataProviderFactory.from_env(cache_dir=temp_cache_dir)

        assert factory._api_key == "env_key"
        assert factory._api_secret == "env_secret"
        assert factory._totp_secret is None

    @patch.dict("os.environ", {"ZERODHA_API_KEY": "   ", "ZERODHA_API_SECRET": "secret"})
    def test_factory_from_env_whitespace_only_key(
        self,
        temp_cache_dir: Path,
    ) -> None:
        """Test factory from_env with whitespace-only API key."""
        with pytest.raises(ConfigError, match="ZERODHA_API_KEY environment variable is required"):
            DataProviderFactory.from_env(cache_dir=temp_cache_dir)

    @patch.dict("os.environ", {"ZERODHA_API_KEY": "key", "ZERODHA_API_SECRET": "   "})
    def test_factory_from_env_whitespace_only_secret(
        self,
        temp_cache_dir: Path,
    ) -> None:
        """Test factory from_env with whitespace-only API secret."""
        with pytest.raises(
            ConfigError,
            match="ZERODHA_API_SECRET environment variable is required",
        ):
            DataProviderFactory.from_env(cache_dir=temp_cache_dir)


class TestCreateProviderChainErrorHandling:
    """Test error handling in create_provider_chain."""

    def test_create_provider_chain_no_access_token(
        self,
        temp_cache_dir: Path,
        mock_jugaad_provider: JugaadProvider,
    ) -> None:
        """Test create_provider_chain fails without access token."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
            jugaad_provider_factory=lambda: mock_jugaad_provider,
        )

        # Mock token manager to return None
        with patch.object(factory, "create_token_manager") as mock_tm_factory:
            mock_tm = MagicMock(spec=ZerodhaTokenManager)
            mock_tm.get_access_token.return_value = None
            mock_tm_factory.return_value = mock_tm

            with pytest.raises(ConfigError, match="No access token available"):
                factory.create_provider_chain()


class TestInstrumentMasterCacheDirCreation:
    """Test InstrumentMaster cache directory creation."""

    def test_instrument_master_creates_cache_dir(
        self,
        temp_cache_dir: Path,
    ) -> None:
        """Test that create_instrument_master creates cache directory."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir / "new_cache",
        )

        # Ensure directory doesn't exist
        assert not temp_cache_dir.joinpath("new_cache").exists()

        im = factory.create_instrument_master()

        # Directory should now exist
        assert temp_cache_dir.joinpath("new_cache").exists()
        assert isinstance(im, InstrumentMaster)


class TestValidateParamsEdgeCases:
    """Test parameter validation edge cases."""

    def test_validate_params_with_whitespace_key(self, temp_cache_dir: Path) -> None:
        """Test validation rejects whitespace-only API key."""
        with pytest.raises(ConfigError, match="api_key cannot be empty"):
            DataProviderFactory(
                api_key="   ",
                api_secret="test_secret",
                cache_dir=temp_cache_dir,
            )

    def test_validate_params_with_whitespace_secret(self, temp_cache_dir: Path) -> None:
        """Test validation rejects whitespace-only API secret."""
        with pytest.raises(ConfigError, match="api_secret cannot be empty"):
            DataProviderFactory(
                api_key="test_key",
                api_secret="   ",
                cache_dir=temp_cache_dir,
            )

    def test_validate_params_with_none_cache_dir(self) -> None:
        """Test validation accepts None cache_dir."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=None,
        )
        assert factory is not None
        # Should use default cache directory


class TestGetDataProviderConvenience:
    """Test get_data_provider convenience method."""

    def test_get_data_provider_returns_failover(
        self,
        temp_cache_dir: Path,
        mock_token_manager: ZerodhaTokenManager,
        mock_kite_provider: KiteProvider,
        mock_jugaad_provider: JugaadProvider,
    ) -> None:
        """Test get_data_provider returns FailoverProvider."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=temp_cache_dir,
            kite_provider_factory=lambda api_key, token: mock_kite_provider,
            jugaad_provider_factory=lambda: mock_jugaad_provider,
        )

        provider = factory.get_data_provider()
        assert isinstance(provider, FailoverProvider)


class TestFactoryAttributeInitialization:
    """Test factory attribute initialization."""

    def test_factory_initializes_all_attributes(self, temp_cache_dir: Path) -> None:
        """Test factory initializes all attributes correctly."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            totp_secret="test_totp",
            cache_dir=temp_cache_dir,
            env_path=temp_cache_dir / ".env",
        )

        assert factory._api_key == "test_key"
        assert factory._api_secret == "test_secret"
        assert factory._totp_secret == "test_totp"
        assert factory._cache_dir == temp_cache_dir
        assert factory._env_path == temp_cache_dir / ".env"
        assert factory._kite_provider_factory is None
        assert factory._jugaad_provider_factory is None

    def test_factory_initializes_with_default_cache_dir(self) -> None:
        """Test factory uses default cache directory when None provided."""
        factory = DataProviderFactory(
            api_key="test_key",
            api_secret="test_secret",
            cache_dir=None,
        )

        # Should use current working directory / cache / instruments
        assert factory._cache_dir == Path.cwd() / "cache" / "instruments"
