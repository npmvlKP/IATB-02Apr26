"""Coverage tests for api."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from iatb.api import IATBApi, create_api


class TestIATBApi:
    def test_init_no_token_manager(self) -> None:
        api = IATBApi()
        assert api is not None

    def test_init_with_token_manager(self) -> None:
        tm = MagicMock()
        api = IATBApi(token_manager=tm)
        assert api is not None


class TestCreateApi:
    @patch("iatb.api.ZerodhaTokenManager", create=True)
    def test_create_api_basic(self, mock_tm_cls: MagicMock) -> None:
        mock_tm_instance = MagicMock()
        mock_tm_cls.return_value = mock_tm_instance
        api = create_api(api_key="test_key", api_secret="test_secret")
        assert isinstance(api, IATBApi)

    @patch("iatb.api.ZerodhaTokenManager", create=True)
    def test_create_api_with_totp(self, mock_tm_cls: MagicMock) -> None:
        mock_tm_instance = MagicMock()
        mock_tm_cls.return_value = mock_tm_instance
        api = create_api(api_key="k", api_secret="s", totp_secret="totp")
        assert isinstance(api, IATBApi)
