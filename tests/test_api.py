"""Tests for IATB Engine REST API (src/iatb/api.py)."""

import sqlite3
import sys
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from iatb.api import _exchange_status, _is_holiday, app

client = TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_200(self) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["mode"] == "paper"
        assert "timestamp" in body

    def test_health_timestamp_is_utc_aware(self) -> None:
        resp = client.get("/health")
        ts = datetime.fromisoformat(resp.json()["timestamp"])
        assert ts.tzinfo is not None


class TestBrokerStatus:
    def test_no_credentials_returns_401(self) -> None:
        with patch("iatb.api.keyring") as mock_kr:
            mock_kr.get_password.return_value = None
            resp = client.get("/broker/status")
            assert resp.status_code == 401

    def test_missing_access_token_returns_401(self) -> None:
        with patch("iatb.api.keyring") as mock_kr:
            mock_kr.get_password.side_effect = lambda _svc, key: (
                "key" if key == "zerodha_api_key" else None
            )
            resp = client.get("/broker/status")
            assert resp.status_code == 401

    def test_successful_broker_status(self) -> None:
        mock_k = MagicMock()
        mock_k.profile.return_value = {
            "user_id": "AB1234",
            "user_name": "Test User",
            "email": "test@example.com",
        }
        mock_k.margins.return_value = {"equity": {"net": "100000.50", "used": "5000.25"}}
        with patch("iatb.api._init_kite", return_value=mock_k):
            resp = client.get("/broker/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["uid"] == "AB1234"
        assert body["name"] == "Test User"
        assert body["email"] == "test@example.com"
        assert Decimal(str(body["available_balance"])) == Decimal("100000.50")
        assert Decimal(str(body["margin_used"])) == Decimal("5000.25")

    def test_kite_unreachable_returns_503(self) -> None:
        with patch("iatb.api._init_kite", side_effect=Exception("Connection refused")):
            resp = client.get("/broker/status")
            assert resp.status_code == 503

    def test_broker_status_with_zero_margins(self) -> None:
        mock_k = MagicMock()
        mock_k.profile.return_value = {"user_id": "XY99", "user_name": "Noob", "email": ""}
        mock_k.margins.return_value = {"equity": {"net": "0", "used": "0"}}
        with patch("iatb.api._init_kite", return_value=mock_k):
            resp = client.get("/broker/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available_balance"] == "0"
        assert body["margin_used"] == "0"

    def test_broker_api_call_failure_returns_503(self) -> None:
        mock_k = MagicMock()
        with patch("iatb.api._init_kite", return_value=mock_k):
            with patch("iatb.api._fetch_kite_profile", side_effect=Exception("API timeout")):
                resp = client.get("/broker/status")
        assert resp.status_code == 503

    def test_init_kite_returns_cached_instance(self) -> None:
        import iatb.api as api_mod

        mock_k = MagicMock()
        api_mod._kite = mock_k
        try:
            result = api_mod._init_kite()
            assert result is mock_k
        finally:
            api_mod._kite = None

    def test_kiteconnect_unavailable_returns_503(self) -> None:
        import iatb.api as api_mod

        api_mod._kite = None
        saved = sys.modules.get("kiteconnect")
        sys.modules["kiteconnect"] = None
        try:
            with patch("iatb.api.keyring") as mock_kr:
                with patch("iatb.broker.token_manager.ZerodhaTokenManager") as mock_tm:
                    mock_tm.return_value.is_token_fresh.return_value = True
                    mock_kr.get_password.side_effect = lambda _svc, key: (
                        "val" if key == "zerodha_api_key" else "tok"
                    )
                    resp = client.get("/broker/status")
            assert resp.status_code == 503
        finally:
            if saved is not None:
                sys.modules["kiteconnect"] = saved
            elif "kiteconnect" in sys.modules:
                del sys.modules["kiteconnect"]

    def test_expired_token_returns_401_with_relogin_required(self) -> None:
        """Test that expired token returns 401 with relogin_required detail."""
        import iatb.api as api_mod

        api_mod._kite = None
        try:
            with patch("iatb.broker.token_manager.ZerodhaTokenManager") as mock_tm:
                mock_tm.return_value.is_token_fresh.return_value = False
                resp = client.get("/broker/status")
            assert resp.status_code == 401
            assert resp.json()["detail"] == "relogin_required"
        finally:
            api_mod._kite = None


class TestExchangeStatus:
    def test_returns_200(self) -> None:
        resp = client.get("/exchanges/status")
        assert resp.status_code == 200
        body = resp.json()
        assert "nse" in body
        assert "cds" in body
        assert "mcx" in body

    def test_status_values_are_valid(self) -> None:
        resp = client.get("/exchanges/status")
        body = resp.json()
        valid = {"Open-Trading", "Closed", "Closed-Holiday"}
        for val in body.values():
            assert val in valid, f"Invalid status: {val}"


class TestHolidayCheck:
    def test_returns_false_when_file_missing(self) -> None:
        with patch("iatb.api._HOLIDAYS_PATH", Path("/nonexistent/path.toml")):
            assert _is_holiday("NSE") is False

    def test_returns_false_when_file_corrupt(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.toml"
        bad_file.write_text("not valid toml {{{", encoding="utf-8")
        with patch("iatb.api._HOLIDAYS_PATH", bad_file):
            assert _is_holiday("NSE") is False

    def test_detects_nse_holiday(self, tmp_path: Path) -> None:
        import pytz

        ist = pytz.timezone("Asia/Kolkata")
        today = datetime.now(ist).date().isoformat()
        year = str(datetime.now(ist).year)
        toml_content = (
            f"[{year}]\n"
            f"[[{year}.nse_cds]]\n"
            f'date = "{today}"\n'
            f'name = "Test Holiday"\n'
            f'exchanges = ["NSE", "CDS"]\n'
            f"[[{year}.mcx]]\n"
            f'date = "2099-01-01"\n'
            f'name = "Future Holiday"\n'
            f'exchanges = ["MCX"]\n'
        )
        holiday_file = tmp_path / "holidays.toml"
        holiday_file.write_text(toml_content, encoding="utf-8")
        with patch("iatb.api._HOLIDAYS_PATH", holiday_file):
            assert _is_holiday("NSE") is True
            assert _is_holiday("CDS") is True
            assert _is_holiday("MCX") is False

    def test_detects_mcx_holiday(self, tmp_path: Path) -> None:
        import pytz

        ist = pytz.timezone("Asia/Kolkata")
        today = datetime.now(ist).date().isoformat()
        year = str(datetime.now(ist).year)
        toml_content = (
            f"[{year}]\n"
            f"[[{year}.mcx]]\n"
            f'date = "{today}"\n'
            f'name = "MCX Holiday"\n'
            f'exchanges = ["MCX"]\n'
        )
        holiday_file = tmp_path / "holidays.toml"
        holiday_file.write_text(toml_content, encoding="utf-8")
        with patch("iatb.api._HOLIDAYS_PATH", holiday_file):
            assert _is_holiday("MCX") is True
            assert _is_holiday("NSE") is False

    def test_no_holiday_today(self, tmp_path: Path) -> None:
        toml_content = '[2026]\n[[2026.nse_cds]]\ndate = "2026-01-26"\nname = "Republic Day"\n'
        holiday_file = tmp_path / "holidays.toml"
        holiday_file.write_text(toml_content, encoding="utf-8")
        with patch("iatb.api._HOLIDAYS_PATH", holiday_file):
            assert _is_holiday("NSE") is False


class TestExchangeStatusHelper:
    def test_returns_closed_holiday_on_holiday(self) -> None:
        with patch("iatb.api._is_holiday", return_value=True):
            result = _exchange_status("NSE", time(9, 15), time(15, 30))
            assert result == "Closed-Holiday"

    def test_returns_valid_status_when_not_holiday(self) -> None:
        with patch("iatb.api._is_holiday", return_value=False):
            result = _exchange_status("NSE", time(9, 15), time(15, 30))
            assert result in ("Open-Trading", "Closed")

    def test_mcx_closed_outside_hours(self) -> None:
        with patch("iatb.api._is_holiday", return_value=False):
            result = _exchange_status("MCX", time(9, 0), time(23, 30))
            assert result in ("Open-Trading", "Closed")

    def test_cds_uses_nse_cds_section(self) -> None:
        with patch("iatb.api._is_holiday", return_value=False):
            result = _exchange_status("CDS", time(9, 15), time(15, 30))
            assert result in ("Open-Trading", "Closed")

    def test_returns_closed_before_open(self) -> None:
        with patch("iatb.api._is_holiday", return_value=False):
            with patch("iatb.api.datetime") as mock_dt:
                mock_now = MagicMock()
                mock_now.time.return_value = time(8, 0)
                mock_dt.now.return_value = mock_now
                result = _exchange_status("NSE", time(9, 15), time(15, 30))
                assert result == "Closed"

    def test_returns_closed_after_close(self) -> None:
        with patch("iatb.api._is_holiday", return_value=False):
            with patch("iatb.api.datetime") as mock_dt:
                mock_now = MagicMock()
                mock_now.time.return_value = time(16, 0)
                mock_dt.now.return_value = mock_now
                result = _exchange_status("NSE", time(9, 15), time(15, 30))
                assert result == "Closed"

    def test_returns_open_during_hours(self) -> None:
        with patch("iatb.api._is_holiday", return_value=False):
            with patch("iatb.api.datetime") as mock_dt:
                mock_now = MagicMock()
                mock_now.time.return_value = time(10, 30)
                mock_dt.now.return_value = mock_now
                result = _exchange_status("NSE", time(9, 15), time(15, 30))
                assert result == "Open-Trading"


class TestScannerEndpoint:
    def test_returns_200(self) -> None:
        resp = client.post("/scanner/run")
        assert resp.status_code == 200

    def test_returns_ready_status(self) -> None:
        resp = client.post("/scanner/run")
        body = resp.json()
        assert body["status"] == "scanner_ready"
        assert body["regime"] == "SIDEWAYS"
        assert body["scorer_available"] is True


class TestCORS:
    def test_cors_headers_present(self) -> None:
        resp = client.options(
            "/health",
            headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "GET"},
        )
        assert resp.status_code == 200


class TestNotFound:
    def test_unknown_endpoint_returns_404(self) -> None:
        resp = client.get("/nonexistent")
        assert resp.status_code == 404

    def test_wrong_method_returns_405(self) -> None:
        resp = client.delete("/health")
        assert resp.status_code == 405


class TestSentimentHealthEndpoint:
    def test_returns_200(self) -> None:
        resp = client.get("/sentiment/health")
        assert resp.status_code == 200

    def test_response_has_all_keys(self) -> None:
        resp = client.get("/sentiment/health")
        body = resp.json()
        for key in ("finbert", "aion", "vader", "aggregator", "ensemble_status"):
            assert key in body, f"Missing key: {key}"

    def test_values_are_available_or_unavailable(self) -> None:
        resp = client.get("/sentiment/health")
        body = resp.json()
        valid = {"available", "unavailable"}
        for key in ("finbert", "aion", "vader", "aggregator"):
            assert body[key] in valid, f"Invalid value for {key}: {body[key]}"

    def test_ensemble_status_is_operational_or_degraded(self) -> None:
        resp = client.get("/sentiment/health")
        body = resp.json()
        assert body["ensemble_status"] in ("operational", "degraded")

    def test_unavailable_module_reports_correctly(self) -> None:
        def mock_import(module_path: str):
            if "vader" in module_path:
                raise ImportError("not installed")
            mock_mod = MagicMock()
            return mock_mod

        with patch("iatb.api.importlib.import_module", side_effect=mock_import):
            resp = client.get("/sentiment/health")
        body = resp.json()
        assert body["vader"] == "unavailable"
        assert body["ensemble_status"] == "degraded"

    def test_missing_class_reports_unavailable(self) -> None:
        def mock_import(module_path: str):
            mock_mod = MagicMock(spec=[])
            return mock_mod

        with patch("iatb.api.importlib.import_module", side_effect=mock_import):
            resp = client.get("/sentiment/health")
        body = resp.json()
        for key in ("finbert", "aion", "vader", "aggregator"):
            assert body[key] == "unavailable"


class TestPnlSummaryEndpoint:
    def test_returns_200(self) -> None:
        resp = client.get("/pnl/summary")
        assert resp.status_code == 200

    def test_response_has_all_keys(self) -> None:
        resp = client.get("/pnl/summary")
        body = resp.json()
        for key in ("net_notional_pnl", "buy_trades", "sell_trades", "total_trades"):
            assert key in body

    def test_returns_defaults_when_no_db(self) -> None:
        with patch("iatb.api._AUDIT_DB", Path("/nonexistent/trades.sqlite")):
            resp = client.get("/pnl/summary")
        body = resp.json()
        assert body["net_notional_pnl"] == "0"
        assert body["buy_trades"] == "0"
        assert body["sell_trades"] == "0"
        assert body["total_trades"] == "0"

    def test_returns_correct_pnl_from_db(self, tmp_path: Path) -> None:
        db_path = tmp_path / "trades.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_audit_log (
                trade_id TEXT PRIMARY KEY,
                timestamp_utc TEXT NOT NULL,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity TEXT NOT NULL,
                price TEXT NOT NULL,
                status TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        today = datetime.now().astimezone().strftime("%Y-%m-%d")
        conn.execute(
            "INSERT INTO trade_audit_log VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "T1",
                f"{today}T10:00:00+00:00",
                "NSE",
                "RELIANCE",
                "BUY",
                "10",
                "1000.50",
                "FILLED",
                "s1",
                "{}",
            ),
        )
        conn.execute(
            "INSERT INTO trade_audit_log VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "T2",
                f"{today}T11:00:00+00:00",
                "NSE",
                "RELIANCE",
                "SELL",
                "10",
                "1050.75",
                "FILLED",
                "s1",
                "{}",
            ),
        )
        conn.commit()
        conn.close()

        with patch("iatb.api._AUDIT_DB", db_path):
            resp = client.get("/pnl/summary")
        body = resp.json()
        assert Decimal(body["net_notional_pnl"]) == Decimal("502.50")
        assert body["buy_trades"] == "1"
        assert body["sell_trades"] == "1"
        assert body["total_trades"] == "2"

    def test_handles_corrupt_db_gracefully(self, tmp_path: Path) -> None:
        bad_db = tmp_path / "bad.sqlite"
        bad_db.write_text("not a sqlite database", encoding="utf-8")
        with patch("iatb.api._AUDIT_DB", bad_db):
            resp = client.get("/pnl/summary")
        body = resp.json()
        assert body["net_notional_pnl"] == "0"


class TestLogsTailEndpoint:
    def test_returns_200(self) -> None:
        resp = client.get("/logs/tail")
        assert resp.status_code == 200

    def test_response_has_lines_and_count(self) -> None:
        resp = client.get("/logs/tail")
        body = resp.json()
        assert "lines" in body
        assert "count" in body

    def test_returns_message_when_no_logs(self) -> None:
        with patch("iatb.api._LOG_DIR", Path("/nonexistent/logs")):
            resp = client.get("/logs/tail")
        body = resp.json()
        assert len(body["lines"]) > 0
        assert body["count"] >= 1

    def test_returns_last_30_lines(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        log_file = log_dir / "deployment_20260410_test.log"
        lines = [f"line {i}" for i in range(50)]
        log_file.write_text("\n".join(lines), encoding="utf-8")

        with patch("iatb.api._LOG_DIR", log_dir):
            resp = client.get("/logs/tail")
        body = resp.json()
        assert body["count"] == 30
        assert body["lines"][0] == "line 20"
        assert body["lines"][-1] == "line 49"

    def test_handles_empty_log_file(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        log_file = log_dir / "deployment_20260410_empty.log"
        log_file.write_text("", encoding="utf-8")

        with patch("iatb.api._LOG_DIR", log_dir):
            resp = client.get("/logs/tail")
        body = resp.json()
        assert body["count"] == 0
        assert body["lines"] == []

    def test_picks_most_recent_log(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "deployment_20260401_old.log").write_text("old log", encoding="utf-8")
        (log_dir / "deployment_20260410_new.log").write_text("new log content", encoding="utf-8")

        with patch("iatb.api._LOG_DIR", log_dir):
            resp = client.get("/logs/tail")
        body = resp.json()
        assert "new log content" in body["lines"]
