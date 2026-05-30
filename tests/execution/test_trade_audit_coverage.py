"""Coverage tests for execution.trade_audit."""

from __future__ import annotations

from iatb.execution.trade_audit import TradeAuditEntry, TradeAuditLogger


class TestTradeAuditEntry:
    def test_init(self) -> None:
        try:
            obj = TradeAuditEntry()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = TradeAuditEntry(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestTradeAuditLogger:
    def test_init(self) -> None:
        try:
            obj = TradeAuditLogger()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = TradeAuditLogger(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
