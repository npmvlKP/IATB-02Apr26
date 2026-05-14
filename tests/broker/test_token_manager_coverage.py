"""Comprehensive coverage tests for ZerodhaTokenManager.

Augments existing tests in test_token_manager.py with targeted coverage
for token freshness, pre-market validity, refresh logic, persistence,
boundary conditions, and error paths.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import keyring
import pytest
from freezegun import freeze_time
from iatb.broker.token_manager import (
    ZerodhaTokenManager,
    _get_next_expiry_utc,
    _get_pre_market_utc,
    _load_env_file,
    _persist_env_updates,
)

_IST_OFFSET = timedelta(hours=5, minutes=30)
_KEYRING_SERVICE = "iatb_zerodha"


def _make_ist_datetime(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC) - _IST_OFFSET


@pytest.fixture
def mock_http_post() -> MagicMock:
    return MagicMock(return_value={"data": {"access_token": "new_access_token"}})


@pytest.fixture
def tm(mock_http_post: MagicMock) -> ZerodhaTokenManager:
    return ZerodhaTokenManager(
        api_key="test_api_key",
        api_secret="test_api_secret",
        totp_secret="JBSWY3DPEHPK3PXP",
        http_post=mock_http_post,
    )


@pytest.fixture
def tm_no_totp(mock_http_post: MagicMock) -> ZerodhaTokenManager:
    return ZerodhaTokenManager(
        api_key="test_api_key",
        api_secret="test_api_secret",
        totp_secret=None,
        http_post=mock_http_post,
    )


@pytest.fixture
def tm_with_env(mock_http_post: MagicMock, tmp_path: Path) -> ZerodhaTokenManager:
    env_file = tmp_path / ".env"
    env_file.write_text("ZERODHA_ACCESS_TOKEN=stored_tok\n")
    return ZerodhaTokenManager(
        api_key="test_api_key",
        api_secret="test_api_secret",
        totp_secret="JBSWY3DPEHPK3PXP",
        http_post=mock_http_post,
        env_path=env_file,
    )


def _keyring_side_effect(token: str, timestamp: str) -> MagicMock:
    return MagicMock(side_effect=[token, timestamp])


class TestIsTokenFreshBefore6AMIST:
    """Scenario 1: is_token_fresh() with token created before 6 AM IST -> True."""

    @freeze_time("2026-04-12 00:15:00", tz_offset=0)
    def test_token_before_6am_ist_is_fresh(self, tm: ZerodhaTokenManager) -> None:
        token_time = _make_ist_datetime(2026, 4, 12, 5, 30)
        with patch.object(
            keyring,
            "get_password",
            side_effect=["tok", token_time.isoformat()],
        ):
            assert tm.is_token_fresh() is True


class TestIsTokenFreshAfter6AMIST:
    """Scenario 2: is_token_fresh() with token created after 6 AM IST -> expired next day."""

    def test_token_after_6am_ist_expires_next_day(self, tm: ZerodhaTokenManager) -> None:
        token_time = _make_ist_datetime(2026, 4, 12, 7, 0)
        now_utc = _make_ist_datetime(2026, 4, 13, 5, 0)
        with patch.object(
            keyring,
            "get_password",
            side_effect=["tok", token_time.isoformat()],
        ):
            with patch("iatb.broker.token_manager.datetime") as mock_dt:
                mock_dt.now.return_value = now_utc
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.combine = datetime.combine
                assert tm.is_token_fresh() is True

    def test_token_after_6am_expired_past_next_6am(self, tm: ZerodhaTokenManager) -> None:
        token_time = _make_ist_datetime(2026, 4, 12, 7, 0)
        now_utc = _make_ist_datetime(2026, 4, 13, 7, 0)
        with patch.object(
            keyring,
            "get_password",
            side_effect=["tok", token_time.isoformat()],
        ):
            with patch("iatb.broker.token_manager.datetime") as mock_dt:
                mock_dt.now.return_value = now_utc
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.combine = datetime.combine
                assert tm.is_token_fresh() is False


class TestIsTokenValidForPreMarket:
    """Scenario 3: is_token_valid_for_pre_market() at various IST times."""

    def test_pre_market_before_9am_ist_valid(self, tm: ZerodhaTokenManager) -> None:
        token_time = _make_ist_datetime(2026, 4, 12, 6, 30)
        now_utc = _make_ist_datetime(2026, 4, 12, 7, 0)
        with patch.object(
            keyring,
            "get_password",
            side_effect=["tok", token_time.isoformat()],
        ):
            with patch("iatb.broker.token_manager.datetime") as mock_dt:
                mock_dt.now.return_value = now_utc
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.combine = datetime.combine
                assert tm.is_token_valid_for_pre_market() is True

    def test_pre_market_after_9am_ist_invalid(self, tm: ZerodhaTokenManager) -> None:
        token_time = _make_ist_datetime(2026, 4, 12, 6, 30)
        now_utc = _make_ist_datetime(2026, 4, 12, 10, 0)
        with patch.object(
            keyring,
            "get_password",
            side_effect=["tok", token_time.isoformat()],
        ):
            with patch("iatb.broker.token_manager.datetime") as mock_dt:
                mock_dt.now.return_value = now_utc
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.combine = datetime.combine
                assert tm.is_token_valid_for_pre_market() is False

    def test_pre_market_no_token_returns_false(self, tm: ZerodhaTokenManager) -> None:
        with patch.object(keyring, "get_password", return_value=None):
            assert tm.is_token_valid_for_pre_market() is False

    def test_pre_market_invalid_timestamp_returns_false(self, tm: ZerodhaTokenManager) -> None:
        with patch.object(keyring, "get_password", side_effect=["tok", "bad_ts"]):
            assert tm.is_token_valid_for_pre_market() is False


class TestShouldRefreshToken:
    """Scenario 4: should_refresh_token() with buffer_minutes."""

    def test_should_refresh_within_buffer(self, tm: ZerodhaTokenManager) -> None:
        token_time = _make_ist_datetime(2026, 4, 12, 5, 0)
        now_utc = _make_ist_datetime(2026, 4, 12, 5, 45)
        with patch.object(
            keyring,
            "get_password",
            side_effect=["tok", token_time.isoformat()],
        ):
            with patch("iatb.broker.token_manager.datetime") as mock_dt:
                mock_dt.now.return_value = now_utc
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.combine = datetime.combine
                assert tm.should_refresh_token(buffer_minutes=30) is True

    def test_should_not_refresh_outside_buffer(self, tm: ZerodhaTokenManager) -> None:
        token_time = _make_ist_datetime(2026, 4, 12, 5, 0)
        now_utc = _make_ist_datetime(2026, 4, 12, 5, 10)
        with patch.object(
            keyring,
            "get_password",
            side_effect=["tok", token_time.isoformat()],
        ):
            with patch("iatb.broker.token_manager.datetime") as mock_dt:
                mock_dt.now.return_value = now_utc
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.combine = datetime.combine
                assert tm.should_refresh_token(buffer_minutes=30) is False

    def test_should_refresh_no_token(self, tm: ZerodhaTokenManager) -> None:
        with patch.object(keyring, "get_password", return_value=None):
            assert tm.should_refresh_token() is True

    def test_should_refresh_invalid_timestamp(self, tm: ZerodhaTokenManager) -> None:
        with patch.object(keyring, "get_password", side_effect=["tok", "invalid"]):
            assert tm.should_refresh_token() is True


class TestAutoRefreshToken:
    """Scenario 5: auto_refresh_token() with TOTP secret."""

    def test_auto_refresh_no_need(self, tm: ZerodhaTokenManager) -> None:
        token_time = _make_ist_datetime(2026, 4, 12, 5, 0)
        now_utc = _make_ist_datetime(2026, 4, 12, 5, 10)
        with patch.object(
            keyring,
            "get_password",
            side_effect=["tok", token_time.isoformat()],
        ):
            with patch("iatb.broker.token_manager.datetime") as mock_dt:
                mock_dt.now.return_value = now_utc
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.combine = datetime.combine
                assert tm.auto_refresh_token() is None

    def test_auto_refresh_with_totp_succeeds(
        self, tm: ZerodhaTokenManager, mock_http_post: MagicMock
    ) -> None:
        with patch.object(tm, "should_refresh_token", return_value=True):
            with patch.object(tm, "resolve_saved_request_token", return_value="req_tok"):
                with patch.object(tm, "store_access_token"):
                    result = tm.auto_refresh_token()
                    assert result == "new_access_token"
                    mock_http_post.assert_called_once()

    def test_auto_refresh_no_request_token_raises(self, tm: ZerodhaTokenManager) -> None:
        with patch.object(tm, "should_refresh_token", return_value=True):
            with patch.object(tm, "resolve_saved_request_token", return_value=None):
                with pytest.raises(ValueError, match="No saved request token"):
                    tm.auto_refresh_token()


class TestExchangeRequestToken:
    """Scenario 6: exchange_request_token() -> access token."""

    def test_exchange_success_returns_token(
        self, tm: ZerodhaTokenManager, mock_http_post: MagicMock
    ) -> None:
        result = tm.exchange_request_token("req_tok_123")
        assert result == "new_access_token"
        call_args = mock_http_post.call_args
        assert call_args[0][0] == "https://kite.zerodha.com/api/session/token"

    def test_exchange_missing_access_token_raises(
        self,
        tm_no_totp: ZerodhaTokenManager,
    ) -> None:
        bad_post = MagicMock(return_value={"data": {"other_key": "val"}})
        mgr = ZerodhaTokenManager(
            api_key="k",
            api_secret="s",
            http_post=bad_post,
        )
        with pytest.raises(ValueError, match="No access_token in API response"):
            mgr.exchange_request_token("req")


class TestStoreAccessToken:
    """Scenario 7: store_access_token() -> keyring + .env persistence."""

    def test_store_writes_keyring_with_utc_timestamp(self, tm: ZerodhaTokenManager) -> None:
        with patch.object(keyring, "set_password") as mock_set:
            with freeze_time("2026-04-12 10:30:00", tz_offset=0):
                tm.store_access_token("my_token")
        calls = mock_set.call_args_list
        assert calls[0][0][0] == _KEYRING_SERVICE
        assert calls[0][0][2] == "my_token"
        assert "2026-04-12T10:30:00" in calls[1][0][2]


class TestGetAccessTokenFallbackChain:
    """Scenario 8: get_access_token() with keyring -> env -> .env fallback."""

    def test_keyring_fresh_returns_first(self, tm: ZerodhaTokenManager) -> None:
        token_time = _make_ist_datetime(2026, 4, 16, 5, 0)
        with patch.object(
            keyring,
            "get_password",
            side_effect=["kr_tok", token_time.isoformat(), "kr_tok"],
        ):
            with patch("iatb.broker.token_manager.datetime") as mock_dt:
                mock_dt.now.return_value = _make_ist_datetime(2026, 4, 16, 5, 15)
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.combine = datetime.combine
                assert tm.get_access_token() == "kr_tok"

    def test_env_var_zerodha_fallback(self, tm_no_totp: ZerodhaTokenManager) -> None:
        with patch.object(keyring, "get_password", return_value=None):
            with patch.dict(os.environ, {"ZERODHA_ACCESS_TOKEN": "z_env_tok"}):
                assert tm_no_totp.get_access_token() == "z_env_tok"

    def test_env_var_kite_fallback(self, tm_no_totp: ZerodhaTokenManager) -> None:
        with patch.object(keyring, "get_password", return_value=None):
            with patch.dict(os.environ, {"KITE_ACCESS_TOKEN": "k_env_tok"}, clear=False):
                with patch.dict(os.environ, {"ZERODHA_ACCESS_TOKEN": ""}, clear=False):
                    result = tm_no_totp.get_access_token()
                    assert result in ("k_env_tok", "z_env_tok")

    def test_dotenv_file_fallback(self, tm_no_totp: ZerodhaTokenManager, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("ZERODHA_ACCESS_TOKEN=file_tok\n")
        with patch.object(keyring, "get_password", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                with patch("pathlib.Path.cwd", return_value=tmp_path):
                    result = tm_no_totp.get_access_token()
                    assert result == "file_tok"

    def test_all_sources_empty_returns_none(self, tm_no_totp: ZerodhaTokenManager) -> None:
        with patch.object(keyring, "get_password", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                with patch("pathlib.Path.cwd", return_value=Path("no_exist")):
                    assert tm_no_totp.get_access_token() is None


class TestGetKiteClient:
    """Scenario 9: get_kite_client() -> KiteConnect instance."""

    def test_get_kite_client_with_explicit_token(self, tm: ZerodhaTokenManager) -> None:
        mock_kite_instance = MagicMock()
        mock_kc_cls = MagicMock(return_value=mock_kite_instance)
        mock_module = MagicMock()
        mock_module.KiteConnect = mock_kc_cls
        with patch.dict("sys.modules", {"kiteconnect": mock_module}):
            client = tm.get_kite_client(access_token="explicit_tok")
            assert client == mock_kite_instance
            mock_kc_cls.assert_called_once_with(api_key="test_api_key", access_token="explicit_tok")

    def test_get_kite_client_no_token_raises(self, tm_no_totp: ZerodhaTokenManager) -> None:
        with patch.object(keyring, "get_password", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                with pytest.raises(ValueError, match="Access token not available"):
                    tm_no_totp.get_kite_client()

    def test_get_kite_client_import_error(self, tm: ZerodhaTokenManager) -> None:
        with patch(
            "builtins.__import__",
            side_effect=ModuleNotFoundError("kiteconnect"),
        ):
            with pytest.raises(ImportError, match="kiteconnect module is required"):
                tm.get_kite_client(access_token="tok")


class TestPersistSessionTokens:
    """Scenario 10: persist_session_tokens() -> both keyring and .env."""

    def test_persist_with_request_token(
        self, tm_with_env: ZerodhaTokenManager, tmp_path: Path
    ) -> None:
        with patch.object(keyring, "set_password") as mock_set:
            result = tm_with_env.persist_session_tokens(
                access_token="acc_tok", request_token="req_tok"
            )
            assert mock_set.call_count == 5
            assert result == tmp_path / ".env"
        env_content = (tmp_path / ".env").read_text()
        assert "ZERODHA_ACCESS_TOKEN=acc_tok" in env_content
        assert "ZERODHA_REQUEST_TOKEN=req_tok" in env_content

    def test_persist_without_request_token(
        self, tm_with_env: ZerodhaTokenManager, tmp_path: Path
    ) -> None:
        with patch.object(keyring, "set_password") as mock_set:
            tm_with_env.persist_session_tokens(access_token="acc_tok")
            assert mock_set.call_count == 3
        env_content = (tmp_path / ".env").read_text()
        assert "ZERODHA_ACCESS_TOKEN=acc_tok" in env_content
        assert "ZERODHA_REQUEST_TOKEN" not in env_content

    def test_persist_no_env_path_returns_none(self, tm: ZerodhaTokenManager) -> None:
        with patch.object(keyring, "set_password"):
            result = tm.persist_session_tokens(access_token="acc_tok")
            assert result is None


class TestEdge6AMISTBoundary:
    """Scenario 11: Edge - Token at 6 AM IST boundary."""

    def test_token_exactly_at_6am_ist(self) -> None:
        token_6am_ist = _make_ist_datetime(2026, 4, 12, 6, 0)
        expiry = _get_next_expiry_utc(token_6am_ist)
        expected = _make_ist_datetime(2026, 4, 13, 6, 0)
        assert expiry == expected

    def test_token_just_before_6am_ist(self) -> None:
        token_before = _make_ist_datetime(2026, 4, 12, 5, 59)
        expiry = _get_next_expiry_utc(token_before)
        expected = _make_ist_datetime(2026, 4, 12, 6, 0)
        assert expiry == expected

    def test_freshness_at_exact_6am_boundary(self, tm: ZerodhaTokenManager) -> None:
        token_time = _make_ist_datetime(2026, 4, 12, 5, 59)
        now_utc = _make_ist_datetime(2026, 4, 12, 5, 59)
        with patch.object(
            keyring,
            "get_password",
            side_effect=["tok", token_time.isoformat()],
        ):
            with patch("iatb.broker.token_manager.datetime") as mock_dt:
                mock_dt.now.return_value = now_utc
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.combine = datetime.combine
                assert tm.is_token_fresh() is True


class TestEdge9AMISTPreMarketBoundary:
    """Scenario 12: Edge - Token at 9 AM IST pre-market boundary."""

    def test_pre_market_exactly_at_9am(self) -> None:
        token_9am = _make_ist_datetime(2026, 4, 12, 9, 0)
        pre_market = _get_pre_market_utc(token_9am)
        expected = _make_ist_datetime(2026, 4, 13, 9, 0)
        assert pre_market == expected

    def test_pre_market_just_before_9am(self) -> None:
        token_before = _make_ist_datetime(2026, 4, 12, 8, 59)
        pre_market = _get_pre_market_utc(token_before)
        expected = _make_ist_datetime(2026, 4, 12, 9, 0)
        assert pre_market == expected

    def test_pre_market_at_boundary_returns_false(self, tm: ZerodhaTokenManager) -> None:
        token_time = _make_ist_datetime(2026, 4, 12, 8, 0)
        now_utc = _make_ist_datetime(2026, 4, 12, 9, 0)
        with patch.object(
            keyring,
            "get_password",
            side_effect=["tok", token_time.isoformat()],
        ):
            with patch("iatb.broker.token_manager.datetime") as mock_dt:
                mock_dt.now.return_value = now_utc
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.combine = datetime.combine
                assert tm.is_token_valid_for_pre_market() is False


class TestEdgeEmptyEnvFile:
    """Scenario 13: Edge - Empty .env file."""

    def test_load_empty_env_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("")
        result = _load_env_file(env_file)
        assert result == {}

    def test_load_env_file_only_comments(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\n# another\n")
        result = _load_env_file(env_file)
        assert result == {}

    def test_get_access_token_from_empty_env(
        self, tm_no_totp: ZerodhaTokenManager, tmp_path: Path
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("")
        with patch.object(keyring, "get_password", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                with patch("pathlib.Path.cwd", return_value=tmp_path):
                    assert tm_no_totp.get_access_token() is None


class TestEdgeEnvExampleResolves:
    """Scenario 14: Edge - .env.example resolves to .env path."""

    def test_example_resolves_to_env(self, tmp_path: Path) -> None:
        example = tmp_path / ".env.example"
        example.write_text("KEY=val\n")
        mgr = ZerodhaTokenManager(
            api_key="k",
            api_secret="s",
            env_path=example,
        )
        assert mgr.token_store_path == tmp_path / ".env"

    def test_non_example_stays_same(self, tmp_path: Path) -> None:
        env_file = tmp_path / "custom.env"
        env_file.write_text("KEY=val\n")
        mgr = ZerodhaTokenManager(
            api_key="k",
            api_secret="s",
            env_path=env_file,
        )
        assert mgr.token_store_path == env_file


class TestErrorNoTokenInKeyring:
    """Scenario 15: Error - No token in keyring -> is_token_fresh returns False."""

    def test_no_token_returns_false(self, tm: ZerodhaTokenManager) -> None:
        with patch.object(keyring, "get_password", return_value=None):
            assert tm.is_token_fresh() is False

    def test_no_timestamp_returns_false(self, tm: ZerodhaTokenManager) -> None:
        with patch.object(keyring, "get_password", side_effect=["tok", None]):
            assert tm.is_token_fresh() is False


class TestErrorTOTPSecretNotConfigured:
    """Scenario 16: Error - TOTP secret not configured -> auto_refresh fails."""

    def test_auto_refresh_no_totp_raises(self, tm_no_totp: ZerodhaTokenManager) -> None:
        with patch.object(tm_no_totp, "should_refresh_token", return_value=True):
            with pytest.raises(ValueError, match="TOTP secret not configured"):
                tm_no_totp.auto_refresh_token()

    def test_generate_totp_no_secret_raises(self, tm_no_totp: ZerodhaTokenManager) -> None:
        with pytest.raises(ValueError, match="TOTP secret not configured"):
            tm_no_totp._generate_totp()

    def test_get_totp_no_secret_raises(self, tm_no_totp: ZerodhaTokenManager) -> None:
        with pytest.raises(ValueError, match="TOTP secret not configured"):
            tm_no_totp.get_totp()


class TestErrorAPIMissingAccessToken:
    """Scenario 17: Error - API response missing access_token -> ValueError."""

    def test_empty_data_raises(self) -> None:
        bad_post = MagicMock(return_value={"data": {}})
        mgr = ZerodhaTokenManager(
            api_key="k",
            api_secret="s",
            http_post=bad_post,
        )
        with pytest.raises(ValueError, match="No access_token in API response"):
            mgr.exchange_request_token("req")

    def test_no_data_key_raises(self) -> None:
        bad_post = MagicMock(return_value={"status": "error"})
        mgr = ZerodhaTokenManager(
            api_key="k",
            api_secret="s",
            http_post=bad_post,
        )
        with pytest.raises(ValueError, match="No access_token in API response"):
            mgr.exchange_request_token("req")

    def test_access_token_none_raises(self) -> None:
        bad_post = MagicMock(return_value={"data": {"access_token": None}})
        mgr = ZerodhaTokenManager(
            api_key="k",
            api_secret="s",
            http_post=bad_post,
        )
        with pytest.raises(ValueError, match="No access_token in API response"):
            mgr.exchange_request_token("req")


class TestErrorKeyringPasswordDeleteError:
    """Scenario 18: Error - keyring PasswordDeleteError during clear_token()."""

    def test_clear_token_handles_password_delete_error(self, tm: ZerodhaTokenManager) -> None:
        with patch.object(
            keyring,
            "delete_password",
            side_effect=keyring.errors.PasswordDeleteError(),
        ):
            tm.clear_token()

    def test_clear_token_with_env_file_and_keyring_error(
        self, tm_with_env: ZerodhaTokenManager, tmp_path: Path
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("ZERODHA_ACCESS_TOKEN=tok\nOTHER_KEY=val\n")
        with patch.object(
            keyring,
            "delete_password",
            side_effect=keyring.errors.PasswordDeleteError(),
        ):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                tm_with_env.clear_token()
        content = env_file.read_text()
        assert "ZERODHA_ACCESS_TOKEN" not in content
        assert "OTHER_KEY" in content


class TestErrorOSErrorReadingEnv:
    """Scenario 19: Error - OSError reading .env -> handled."""

    def test_load_env_file_os_error(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("KEY=val\n")
        real_path = str(env_file)
        with patch("iatb.broker.token_manager.Path.read_text", side_effect=OSError("read error")):
            result = _load_env_file(Path(real_path))
            assert result == {}

    def test_clear_env_token_os_error(self, tm: ZerodhaTokenManager, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("ZERODHA_ACCESS_TOKEN=tok\n")
        real_path = str(env_file)
        with patch("iatb.broker.token_manager.Path.read_text", side_effect=OSError("read error")):
            tm._clear_env_token(Path(real_path))


class TestAutoRefreshExceptionPropagation:
    """Scenario 20: auto_refresh_token() exception propagation."""

    def test_auto_refresh_exchange_failure_raises(self, tm: ZerodhaTokenManager) -> None:
        with patch.object(tm, "should_refresh_token", return_value=True):
            with patch.object(tm, "resolve_saved_request_token", return_value="req"):
                with patch.object(
                    tm,
                    "exchange_request_token",
                    side_effect=ValueError("API error"),
                ):
                    with pytest.raises(ValueError, match="API error"):
                        tm.auto_refresh_token()


class TestResolveSavedRequestToken:
    """Additional: resolve_saved_request_token env file path."""

    def test_request_token_from_env_file_valid(
        self, mock_http_post: MagicMock, tmp_path: Path
    ) -> None:
        env_file = tmp_path / ".env.example"
        env_file.write_text(
            "ZERODHA_REQUEST_TOKEN=req_tok\n" "ZERODHA_REQUEST_TOKEN_DATE_UTC=2026-04-16\n"
        )
        actual_env = tmp_path / ".env"
        actual_env.write_text(
            "ZERODHA_REQUEST_TOKEN=req_tok\n" "ZERODHA_REQUEST_TOKEN_DATE_UTC=2026-04-16\n"
        )
        mgr = ZerodhaTokenManager(
            api_key="k",
            api_secret="s",
            http_post=mock_http_post,
            env_path=env_file,
            today_utc=date(2026, 4, 16),
        )
        with patch.object(keyring, "get_password", return_value=None):
            assert mgr.resolve_saved_request_token() == "req_tok"

    def test_request_token_no_date_invalid(self, mock_http_post: MagicMock, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("ZERODHA_REQUEST_TOKEN=req_tok\n")
        mgr = ZerodhaTokenManager(
            api_key="k",
            api_secret="s",
            http_post=mock_http_post,
            env_path=env_file,
            today_utc=date(2026, 4, 16),
        )
        with patch.object(keyring, "get_password", return_value=None):
            assert mgr.resolve_saved_request_token() is None


class TestResolveSavedAccessToken:
    """Additional: resolve_saved_access_token env file valid."""

    def test_access_token_from_env_file_valid_today(
        self, mock_http_post: MagicMock, tmp_path: Path
    ) -> None:
        env_example = tmp_path / ".env.example"
        env_example.write_text("placeholder=1\n")
        actual_env = tmp_path / ".env"
        actual_env.write_text(
            "ZERODHA_ACCESS_TOKEN=env_acc_tok\n" "ZERODHA_ACCESS_TOKEN_DATE_UTC=2026-04-16\n"
        )
        mgr = ZerodhaTokenManager(
            api_key="k",
            api_secret="s",
            http_post=mock_http_post,
            env_path=env_example,
            today_utc=date(2026, 4, 16),
        )
        with patch.object(keyring, "get_password", return_value=None):
            assert mgr.resolve_saved_access_token() == "env_acc_tok"

    def test_access_token_kite_alias_from_env(
        self, mock_http_post: MagicMock, tmp_path: Path
    ) -> None:
        env_example = tmp_path / ".env.example"
        env_example.write_text("placeholder=1\n")
        actual_env = tmp_path / ".env"
        actual_env.write_text(
            "KITE_ACCESS_TOKEN=kite_acc\n" "ZERODHA_ACCESS_TOKEN_DATE_UTC=2026-04-16\n"
        )
        mgr = ZerodhaTokenManager(
            api_key="k",
            api_secret="s",
            http_post=mock_http_post,
            env_path=env_example,
            today_utc=date(2026, 4, 16),
        )
        with patch.object(keyring, "get_password", return_value=None):
            assert mgr.resolve_saved_access_token() == "kite_acc"


class TestPersistEnvUpdates:
    """Additional: _persist_env_updates updates existing keys."""

    def test_persist_updates_existing_key(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING_KEY=old_val\nOTHER_KEY=other\n")
        _persist_env_updates(env_file, {"EXISTING_KEY": "new_val"})
        content = env_file.read_text()
        assert "EXISTING_KEY=new_val" in content
        assert "OTHER_KEY=other" in content

    def test_persist_creates_new_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        assert not env_file.exists()
        _persist_env_updates(env_file, {"NEW_KEY": "val"})
        content = env_file.read_text()
        assert "NEW_KEY=val" in content


class TestIsTodayMethod:
    """Additional: _is_today edge cases."""

    def test_is_today_matching_date(self) -> None:
        mgr = ZerodhaTokenManager(
            api_key="k",
            api_secret="s",
            today_utc=date(2026, 4, 16),
        )
        assert mgr._is_today("2026-04-16") is True

    def test_is_today_non_matching_date(self) -> None:
        mgr = ZerodhaTokenManager(
            api_key="k",
            api_secret="s",
            today_utc=date(2026, 4, 16),
        )
        assert mgr._is_today("2026-04-15") is False

    def test_is_today_whitespace_stripped(self) -> None:
        mgr = ZerodhaTokenManager(
            api_key="k",
            api_secret="s",
            today_utc=date(2026, 4, 16),
        )
        assert mgr._is_today("  2026-04-16  ") is True


class TestDefaultHTTPPost:
    """Additional: _default_http_post non-HTTPS rejected."""

    def test_non_https_raises(self) -> None:
        from iatb.broker.token_manager import _default_http_post

        with pytest.raises(ValueError, match="Only HTTPS URLs are allowed"):
            _default_http_post(
                "http://insecure.com",
                {"Content-Type": "application/json"},
                b"body",
            )


class TestGetLoginURL:
    """Additional: get_login_url correctness."""

    def test_login_url_format(self, tm: ZerodhaTokenManager) -> None:
        url = tm.get_login_url()
        assert url.startswith("https://kite.zerodha.com/connect/login")
        assert "api_key=test_api_key" in url


class TestInitWithEnvValues:
    """Additional: Initialization with env_values parameter."""

    def test_init_with_env_values_dict(self, mock_http_post: MagicMock, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING=val\n")
        mgr = ZerodhaTokenManager(
            api_key="k",
            api_secret="s",
            http_post=mock_http_post,
            env_path=env_file,
            env_values={"CUSTOM_KEY": "custom_val"},
        )
        assert mgr._env_values == {"CUSTOM_KEY": "custom_val"}

    def test_init_without_env_path(self, mock_http_post: MagicMock) -> None:
        mgr = ZerodhaTokenManager(
            api_key="k",
            api_secret="s",
            http_post=mock_http_post,
        )
        assert mgr.token_store_path is None

    def test_init_with_today_utc(self, mock_http_post: MagicMock) -> None:
        mgr = ZerodhaTokenManager(
            api_key="k",
            api_secret="s",
            http_post=mock_http_post,
            today_utc=date(2026, 1, 1),
        )
        assert mgr._today_utc == date(2026, 1, 1)


class TestClearEnvTokenPreservesComments:
    """Additional: _clear_env_token preserves comments and other keys."""

    def test_clear_preserves_comments_and_non_token_keys(
        self, tm: ZerodhaTokenManager, tmp_path: Path
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# This is a comment\n"
            "API_KEY=my_key\n"
            "ZERODHA_ACCESS_TOKEN=secret\n"
            "OTHER_SETTING=true\n"
        )
        tm._clear_env_token(env_file)
        content = env_file.read_text()
        assert "# This is a comment" in content
        assert "API_KEY=my_key" in content
        assert "OTHER_SETTING=true" in content
        assert "ZERODHA_ACCESS_TOKEN" not in content


class TestGetAccessTokenNoEnvFallback:
    """Additional: get_access_token with use_env_fallback=False skips env."""

    def test_no_env_fallback_skips_env_vars(self, tm_no_totp: ZerodhaTokenManager) -> None:
        with patch.object(keyring, "get_password", return_value=None):
            with patch.dict(os.environ, {"ZERODHA_ACCESS_TOKEN": "env_tok"}):
                assert tm_no_totp.get_access_token(use_env_fallback=False) is None


class TestPreMarketUTC:
    """Additional: _get_pre_market_utc helper function."""

    def test_before_9am_ist_same_day(self) -> None:
        token_time = _make_ist_datetime(2026, 4, 12, 8, 0)
        result = _get_pre_market_utc(token_time)
        expected = _make_ist_datetime(2026, 4, 12, 9, 0)
        assert result == expected

    def test_after_9am_ist_next_day(self) -> None:
        token_time = _make_ist_datetime(2026, 4, 12, 10, 0)
        result = _get_pre_market_utc(token_time)
        expected = _make_ist_datetime(2026, 4, 13, 9, 0)
        assert result == expected


class TestLoadEnvFileParsing:
    """Additional: _load_env_file parsing edge cases."""

    def test_line_without_equals_skipped(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("NO_EQUALS_HERE\nKEY=val\n")
        result = _load_env_file(env_file)
        assert result == {"KEY": "val"}

    def test_quoted_values_stripped(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=\"double\"\nKEY2='single'\n")
        result = _load_env_file(env_file)
        assert result["KEY1"] == "double"
        assert result["KEY2"] == "single"

    def test_equals_in_value_preserved(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("KEY=val=with=equals\n")
        result = _load_env_file(env_file)
        assert result["KEY"] == "val=with=equals"
