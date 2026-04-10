"""Tests for IATB Deployment Dashboard (src/iatb/deployment_dashboard.py)."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient
from iatb.deployment_dashboard import (
    _DASHBOARD_HTML,
    _build_offline_status,
    _build_sentiment_health,
    _check_sentiment_module,
    _fetch_engine,
    app,
)

client = TestClient(app)


class TestCheckSentimentModule:
    def test_returns_available_when_import_succeeds(self) -> None:
        mock_mod = MagicMock()
        mock_mod.FinbertAnalyzer = MagicMock()
        with patch("iatb.deployment_dashboard.importlib.import_module", return_value=mock_mod):
            result = _check_sentiment_module("iatb.sentiment.finbert_analyzer", "FinbertAnalyzer")
        assert result == "available"

    def test_returns_unavailable_when_import_fails(self) -> None:
        with patch(
            "iatb.deployment_dashboard.importlib.import_module",
            side_effect=ImportError("no module"),
        ):
            result = _check_sentiment_module("iatb.sentiment.nonexistent", "NoClass")
        assert result == "unavailable"

    def test_returns_unavailable_when_class_missing(self) -> None:
        mock_mod = MagicMock(spec=[])
        with patch("iatb.deployment_dashboard.importlib.import_module", return_value=mock_mod):
            result = _check_sentiment_module("iatb.sentiment.base", "MissingClass")
        assert result == "unavailable"

    def test_returns_unavailable_on_attribute_error(self) -> None:
        mock_mod = MagicMock()
        mock_mod.SomeClass = MagicMock()
        del mock_mod.SomeClass
        with patch("iatb.deployment_dashboard.importlib.import_module", return_value=mock_mod):
            result = _check_sentiment_module("iatb.sentiment.base", "SomeClass")
        assert result == "unavailable"


class TestBuildSentimentHealth:
    def test_returns_all_keys(self) -> None:
        health = _build_sentiment_health()
        for key in ("finbert", "aion", "vader", "aggregator", "ensemble_status"):
            assert key in health

    def test_ensemble_operational_when_all_available(self) -> None:
        with patch("iatb.deployment_dashboard._check_sentiment_module", return_value="available"):
            health = _build_sentiment_health()
        assert health["ensemble_status"] == "operational"

    def test_ensemble_degraded_when_any_unavailable(self) -> None:
        call_count = 0

        def side_effect(mod: str, cls: str) -> str:
            nonlocal call_count
            call_count += 1
            return "unavailable" if call_count == 2 else "available"

        with patch("iatb.deployment_dashboard._check_sentiment_module", side_effect=side_effect):
            health = _build_sentiment_health()
        assert health["ensemble_status"] == "degraded"

    def test_ensemble_degraded_when_all_unavailable(self) -> None:
        with patch("iatb.deployment_dashboard._check_sentiment_module", return_value="unavailable"):
            health = _build_sentiment_health()
        assert health["ensemble_status"] == "degraded"


class TestFetchEngine:
    async def test_returns_empty_dict_on_connection_error(self) -> None:
        with patch("iatb.deployment_dashboard.httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = False
            mock_instance.get.side_effect = httpx.ConnectError("Connection refused")
            mock_cls.return_value = mock_instance
            result = await _fetch_engine("/health")
        assert result == {}

    async def test_returns_json_on_success(self) -> None:
        with patch("iatb.deployment_dashboard.httpx.AsyncClient") as mock_cls:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"status": "healthy"}
            mock_resp.raise_for_status = MagicMock()
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = False
            mock_instance.get.return_value = mock_resp
            mock_cls.return_value = mock_instance
            result = await _fetch_engine("/health")
        assert result == {"status": "healthy"}

    async def test_returns_empty_on_timeout(self) -> None:
        with patch("iatb.deployment_dashboard.httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = False
            mock_instance.get.side_effect = httpx.TimeoutException("timeout")
            mock_cls.return_value = mock_instance
            result = await _fetch_engine("/health", timeout=0.1)
        assert result == {}

    async def test_returns_empty_on_http_error(self) -> None:
        with patch("iatb.deployment_dashboard.httpx.AsyncClient") as mock_cls:
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500",
                request=MagicMock(),
                response=mock_resp,
            )
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = False
            mock_instance.get.return_value = mock_resp
            mock_cls.return_value = mock_instance
            result = await _fetch_engine("/health")
        assert result == {}

    async def test_passes_correct_url_and_timeout(self) -> None:
        with patch("iatb.deployment_dashboard.httpx.AsyncClient") as mock_cls:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {}
            mock_resp.raise_for_status = MagicMock()
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = False
            mock_instance.get.return_value = mock_resp
            mock_cls.return_value = mock_instance
            await _fetch_engine("/broker/status", timeout=5.0)
            mock_instance.get.assert_called_once_with(
                "http://127.0.0.1:8000/broker/status",
                timeout=5.0,
            )


class TestBuildOfflineStatus:
    def test_returns_valid_structure(self) -> None:
        status = _build_offline_status()
        assert status["engine_health"]["status"] == "offline"
        assert status["broker_info"]["status"] == "unreachable"
        assert status["trades_today"] == 0
        assert status["recent_trades"] == []
        assert len(status["log_tail"]) > 0

    def test_timestamp_is_utc(self) -> None:
        status = _build_offline_status()
        ts = datetime.fromisoformat(status["timestamp_utc"])
        assert ts.tzinfo is not None

    def test_exchange_info_has_all_keys(self) -> None:
        status = _build_offline_status()
        for key in ("nse", "cds", "mcx"):
            assert key in status["exchange_info"]

    def test_pnl_summary_has_all_keys(self) -> None:
        status = _build_offline_status()
        for key in ("net_notional_pnl", "buy_trades", "sell_trades", "total_trades"):
            assert key in status["pnl_summary"]

    def test_sentiment_health_has_all_keys(self) -> None:
        status = _build_offline_status()
        for key in ("finbert", "aion", "vader", "aggregator", "ensemble_status"):
            assert key in status["sentiment_health"]

    def test_sentiment_health_uses_real_checks(self) -> None:
        with patch("iatb.deployment_dashboard._build_sentiment_health") as mock:
            mock.return_value = {
                "finbert": "available",
                "aion": "unavailable",
                "vader": "available",
                "aggregator": "available",
                "ensemble_status": "degraded",
            }
            status = _build_offline_status()
        mock.assert_called_once()
        assert status["sentiment_health"]["ensemble_status"] == "degraded"


class TestApiStatusEndpoint:
    def test_returns_200(self) -> None:
        resp = client.get("/api/status")
        assert resp.status_code == 200

    def test_response_structure(self) -> None:
        resp = client.get("/api/status")
        body = resp.json()
        required_keys = [
            "timestamp_utc",
            "engine_health",
            "sentiment_health",
            "broker_info",
            "exchange_info",
            "trades_today",
            "pnl_summary",
            "recent_trades",
            "log_tail",
        ]
        for key in required_keys:
            assert key in body, f"Missing key: {key}"

    def test_timestamp_is_utc_aware(self) -> None:
        resp = client.get("/api/status")
        ts = datetime.fromisoformat(resp.json()["timestamp_utc"])
        assert ts.tzinfo is not None

    def test_engine_offline_returns_offline_status(self) -> None:
        with patch("iatb.deployment_dashboard._fetch_engine", return_value={}):
            resp = client.get("/api/status")
        body = resp.json()
        assert body["engine_health"]["status"] == "offline"
        assert body["broker_info"]["status"] == "unreachable"

    def test_engine_online_returns_real_data(self) -> None:
        mock_health: dict[str, object] = {
            "status": "healthy",
            "mode": "paper",
            "timestamp": "2026-04-10T00:00:00+00:00",
        }
        mock_broker: dict[str, object] = {
            "uid": "AB1234",
            "name": "Test",
            "email": "t@t.com",
            "available_balance": "100000",
            "margin_used": "5000",
        }
        mock_exchanges: dict[str, object] = {
            "nse": "Open-Trading",
            "cds": "Open-Trading",
            "mcx": "Closed",
        }
        mock_sentiment: dict[str, object] = {
            "finbert": "available",
            "aion": "available",
            "vader": "available",
            "aggregator": "available",
            "ensemble_status": "operational",
        }
        mock_pnl: dict[str, object] = {
            "net_notional_pnl": "500",
            "buy_trades": "3",
            "sell_trades": "2",
            "total_trades": "5",
        }
        mock_logs: dict[str, object] = {
            "lines": ["log line 1", "log line 2"],
            "count": 2,
        }

        async def mock_fetch(path: str, timeout: float = 2.0) -> dict[str, object]:
            if path == "/health":
                return mock_health
            if path == "/broker/status":
                return mock_broker
            if path == "/exchanges/status":
                return mock_exchanges
            if path == "/sentiment/health":
                return mock_sentiment
            if path == "/pnl/summary":
                return mock_pnl
            if path == "/logs/tail":
                return mock_logs
            return {}

        with patch("iatb.deployment_dashboard._fetch_engine", side_effect=mock_fetch):
            resp = client.get("/api/status")
        body = resp.json()
        assert body["engine_health"]["status"] == "healthy"
        assert body["broker_info"]["uid"] == "AB1234"
        assert body["exchange_info"]["nse"] == "Open-Trading"
        assert body["sentiment_health"]["finbert"] == "available"
        assert body["pnl_summary"]["net_notional_pnl"] == "500"
        assert body["log_tail"] == ["log line 1", "log line 2"]

    def test_partial_broker_response(self) -> None:
        async def mock_fetch(path: str, timeout: float = 2.0) -> dict[str, object]:
            if path == "/health":
                return {
                    "status": "healthy",
                    "mode": "paper",
                    "timestamp": "2026-04-10T00:00:00+00:00",
                }
            return {}

        with patch("iatb.deployment_dashboard._fetch_engine", side_effect=mock_fetch):
            resp = client.get("/api/status")
        body = resp.json()
        assert body["engine_health"]["status"] == "healthy"
        assert body["broker_info"]["status"] == "unreachable"

    def test_partial_exchange_response(self) -> None:
        async def mock_fetch(path: str, timeout: float = 2.0) -> dict[str, object]:
            if path == "/health":
                return {
                    "status": "healthy",
                    "mode": "paper",
                    "timestamp": "2026-04-10T00:00:00+00:00",
                }
            if path == "/broker/status":
                return {
                    "uid": "XY99",
                    "name": "T",
                    "email": "",
                    "available_balance": "0",
                    "margin_used": "0",
                }
            return {}

        with patch("iatb.deployment_dashboard._fetch_engine", side_effect=mock_fetch):
            resp = client.get("/api/status")
        body = resp.json()
        assert body["exchange_info"]["nse"] == "Closed"

    def test_sentiment_health_structure(self) -> None:
        resp = client.get("/api/status")
        sh = resp.json()["sentiment_health"]
        for key in ("finbert", "aion", "vader", "aggregator", "ensemble_status"):
            assert key in sh

    def test_pnl_summary_defaults(self) -> None:
        resp = client.get("/api/status")
        pnl = resp.json()["pnl_summary"]
        assert pnl["net_notional_pnl"] == "0"
        assert pnl["buy_trades"] == "0"
        assert pnl["sell_trades"] == "0"
        assert pnl["total_trades"] == "0"

    def test_recent_trades_empty(self) -> None:
        resp = client.get("/api/status")
        assert resp.json()["recent_trades"] == []

    def test_log_tail_non_empty(self) -> None:
        resp = client.get("/api/status")
        assert len(resp.json()["log_tail"]) > 0

    def test_falls_back_to_local_sentiment_when_engine_unavailable(self) -> None:
        async def mock_fetch(path: str, timeout: float = 2.0) -> dict[str, object]:
            if path == "/health":
                return {
                    "status": "healthy",
                    "mode": "paper",
                    "timestamp": "2026-04-10T00:00:00+00:00",
                }
            return {}

        with patch("iatb.deployment_dashboard._fetch_engine", side_effect=mock_fetch):
            resp = client.get("/api/status")
        sh = resp.json()["sentiment_health"]
        assert "ensemble_status" in sh


class TestRootEndpoint:
    def test_returns_200(self) -> None:
        resp = client.get("/")
        assert resp.status_code == 200

    def test_returns_html_content_type(self) -> None:
        resp = client.get("/")
        assert "text/html" in resp.headers["content-type"]

    def test_html_contains_title(self) -> None:
        resp = client.get("/")
        assert "iATB Deployment Dashboard" in resp.text

    def test_html_contains_api_endpoint_reference(self) -> None:
        resp = client.get("/")
        assert "/api/status" in resp.text

    def test_html_contains_auto_refresh(self) -> None:
        resp = client.get("/")
        assert "setInterval" in resp.text

    def test_html_contains_exchange_labels(self) -> None:
        resp = client.get("/")
        assert "nse" in resp.text
        assert "cds" in resp.text
        assert "mcx" in resp.text

    def test_html_contains_broker_section(self) -> None:
        resp = client.get("/")
        assert "Broker" in resp.text

    def test_html_contains_sentiment_section(self) -> None:
        resp = client.get("/")
        assert "Sentiment" in resp.text

    def test_html_contains_pnl_section(self) -> None:
        resp = client.get("/")
        assert "PnL" in resp.text

    def test_html_contains_log_section(self) -> None:
        resp = client.get("/")
        assert "Log" in resp.text

    def test_dashboard_html_constant_is_non_empty(self) -> None:
        assert len(_DASHBOARD_HTML) > 0

    def test_dashboard_html_contains_doctype(self) -> None:
        assert "<!DOCTYPE html>" in _DASHBOARD_HTML

    def test_catch_block_updates_all_cards(self) -> None:
        assert "Engine Unreachable" in _DASHBOARD_HTML
        assert 'document.getElementById("brk").innerHTML=_err' in _DASHBOARD_HTML
        assert 'document.getElementById("exch").innerHTML=_err' in _DASHBOARD_HTML
        assert 'document.getElementById("sent").innerHTML=_err' in _DASHBOARD_HTML
        assert 'document.getElementById("pnl").innerHTML=_err' in _DASHBOARD_HTML
        assert 'document.getElementById("log").innerHTML' in _DASHBOARD_HTML

    def test_html_contains_vader_sentiment(self) -> None:
        resp = client.get("/")
        assert "vader" in resp.text
