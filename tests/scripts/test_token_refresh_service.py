"""
Tests for token_refresh_service.py script.
"""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestTokenRefreshService:
    """Tests for TokenRefreshService class."""

    @pytest.fixture
    def mock_env_credentials(self) -> None:
        """Set up mock environment credentials."""
        os.environ["KITE_API_KEY"] = "test_api_key"
        os.environ["KITE_API_SECRET"] = "test_api_secret"  # noqa: S105 - test secret
        os.environ["KITE_TOTP_SECRET"] = "JBSWY3DPEHPK3PXP"  # noqa: S105 - test secret

    @pytest.fixture
    def clear_env_credentials(self) -> None:
        """Clear environment credentials."""
        for key in ["KITE_API_KEY", "KITE_API_SECRET", "KITE_TOTP_SECRET"]:
            os.environ.pop(key, None)

    def test_token_refresh_service_import(self, mock_env_credentials: None) -> None:
        """Test that token_refresh_service module can be imported."""
        import scripts.token_refresh_service as trs

        assert hasattr(trs, "TokenRefreshService")

    @patch("iatb.broker.token_manager.ZerodhaTokenManager")
    def test_token_refresh_service_init_with_env(
        self, mock_token_manager: MagicMock, mock_env_credentials: None
    ) -> None:
        """Test TokenRefreshService initialization with env credentials."""
        # Import after credentials are set
        from scripts.token_refresh_service import TokenRefreshService

        service = TokenRefreshService()
        assert service is not None
        mock_token_manager.assert_called_once()

    def test_token_refresh_service_init_missing_credentials(
        self, clear_env_credentials: None
    ) -> None:
        """Test TokenRefreshService initialization with missing credentials."""
        from scripts.token_refresh_service import TokenRefreshService

        with pytest.raises(ValueError, match="Missing API credentials"):
            TokenRefreshService()

    @patch("iatb.broker.token_manager.ZerodhaTokenManager")
    def test_is_token_fresh(  # noqa: D103
        self, mock_token_manager: MagicMock, mock_env_credentials: None
    ) -> None:
        """Test is_token_fresh method."""
        from scripts.token_refresh_service import TokenRefreshService

        mock_tm_instance = MagicMock()
        mock_tm_instance.is_token_fresh.return_value = True
        mock_token_manager.return_value = mock_tm_instance

        service = TokenRefreshService()
        result = service.is_token_fresh()
        assert result is True
        mock_tm_instance.is_token_fresh.assert_called_once()

    @patch("iatb.broker.token_manager.ZerodhaTokenManager")
    def test_get_totp(self, mock_token_manager: MagicMock, mock_env_credentials: None) -> None:
        """Test get_totp method."""
        from scripts.token_refresh_service import TokenRefreshService

        mock_tm_instance = MagicMock()
        mock_tm_instance.get_totp.return_value = "123456"
        mock_token_manager.return_value = mock_tm_instance

        service = TokenRefreshService()
        result = service.get_totp()
        assert result == "123456"
        mock_tm_instance.get_totp.assert_called_once()

    @patch("iatb.broker.token_manager.ZerodhaTokenManager")
    def test_get_login_url(self, mock_token_manager: MagicMock, mock_env_credentials: None) -> None:
        """Test get_login_url method."""
        from scripts.token_refresh_service import TokenRefreshService

        mock_tm_instance = MagicMock()
        mock_tm_instance.get_login_url.return_value = "https://kite.zerodha.com/connect/login"
        mock_token_manager.return_value = mock_tm_instance

        service = TokenRefreshService()
        result = service.get_login_url()
        assert "kite.zerodha.com" in result
        mock_tm_instance.get_login_url.assert_called_once()

    @patch("iatb.broker.token_manager.ZerodhaTokenManager")
    def test_store_token(self, mock_token_manager: MagicMock, mock_env_credentials: None) -> None:
        """Test store_token method."""
        from scripts.token_refresh_service import TokenRefreshService

        mock_tm_instance = MagicMock()
        mock_token_manager.return_value = mock_tm_instance

        service = TokenRefreshService()
        service.store_token("test_access_token")
        mock_tm_instance.store_access_token.assert_called_once_with("test_access_token")

    @patch("iatb.broker.token_manager.ZerodhaTokenManager")
    async def test_run_once(  # noqa: D103
        self, mock_token_manager: MagicMock, mock_env_credentials: None
    ) -> None:
        """Test run_once method."""
        from scripts.token_refresh_service import TokenRefreshService

        mock_tm_instance = MagicMock()
        mock_tm_instance.is_token_fresh.return_value = True
        mock_token_manager.return_value = mock_tm_instance

        service = TokenRefreshService()
        result = await service.run_once()
        assert isinstance(result, dict)
        assert "token_fresh" in result
        assert "needs_refresh" in result
        assert "totp_available" in result
        assert result["token_fresh"] is True
        assert result["needs_refresh"] is False

    @patch("iatb.broker.token_manager.ZerodhaTokenManager")
    def test_stop(self, mock_token_manager: MagicMock, mock_env_credentials: None) -> None:
        """Test stop method."""
        from scripts.token_refresh_service import TokenRefreshService

        service = TokenRefreshService()
        service.stop()
        assert service._running is False  # noqa: SLF001

    @patch("iatb.broker.token_manager.ZerodhaTokenManager")
    def test_custom_check_interval(
        self, mock_token_manager: MagicMock, mock_env_credentials: None
    ) -> None:
        """Test TokenRefreshService with custom check interval."""
        from scripts.token_refresh_service import TokenRefreshService

        service = TokenRefreshService(check_interval_seconds=600)
        assert service._check_interval == 600  # noqa: SLF001
