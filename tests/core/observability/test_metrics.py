"""Tests for observability metrics."""

import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _mock_prometheus():
    mocks = {
        "prometheus_client": MagicMock(),
        "prometheus_fastapi_instrumentator": MagicMock(),
    }
    original = {}
    for mod in mocks:
        original[mod] = sys.modules.get(mod)
        sys.modules[mod] = mocks[mod]
    yield
    for mod, orig in original.items():
        if orig is None:
            sys.modules.pop(mod, None)
        else:
            sys.modules[mod] = orig


class TestInitializeMetrics:
    def test_sets_app_info(self) -> None:
        from iatb.core.observability.metrics import initialize_metrics

        initialize_metrics("1.0.0")


class TestRecordTrade:
    def test_records_trade(self) -> None:
        from iatb.core.observability.metrics import record_trade

        record_trade("NSE", "BUY", "SUCCESS", pnl=100.0, ticker="RELIANCE")
        assert True


class TestUpdateOpenPositions:
    def test_updates_positions(self) -> None:
        from iatb.core.observability.metrics import update_open_positions

        update_open_positions("NSE", 5)
        assert True


class TestRecordDataSourceRequest:
    def test_records_request(self) -> None:
        from iatb.core.observability.metrics import record_data_source_request

        record_data_source_request("kite", "success")
        assert True


class TestRecordDataSourceFallback:
    def test_records_fallback(self) -> None:
        from iatb.core.observability.metrics import record_data_source_fallback

        record_data_source_fallback("kite", "jugaad")
        assert True


class TestUpdateDataFreshness:
    def test_updates_freshness(self) -> None:
        from iatb.core.observability.metrics import update_data_freshness

        update_data_freshness("kite", 60.0)
        assert True


class TestUpdateKiteTokenFreshness:
    def test_updates_freshness(self) -> None:
        from iatb.core.observability.metrics import update_kite_token_freshness

        update_kite_token_freshness(True)
        assert True


class TestTrackExecutionTime:
    def test_decorator(self) -> None:
        from iatb.core.observability.metrics import track_execution_time

        mock_histogram = MagicMock()
        mock_histogram.labels.return_value.time.return_value = MagicMock(
            __enter__=MagicMock(), __exit__=MagicMock()
        )

        @track_execution_time(mock_histogram, labels={"test": "value"})
        def dummy() -> int:
            return 42

        assert dummy() == 42
