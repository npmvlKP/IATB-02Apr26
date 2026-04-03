from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.risk.sebi_compliance import SEBIComplianceConfig, SEBIComplianceManager
from iatb.storage.sqlite_store import SQLiteStore, TradeAuditRecord


def test_sebi_compliance_injection_checks_and_logout_logic(tmp_path: Path) -> None:
    config = SEBIComplianceConfig("ALG-101", tmp_path / "audit.db", ("ip-allowed",))
    manager = SEBIComplianceManager(config)
    payload = manager.inject_algo_id({"symbol": "NIFTY"})
    assert payload["algo_id"] == "ALG-101"
    assert manager.is_static_ip_allowed("ip-allowed")
    assert not manager.should_auto_logout(datetime(2026, 1, 5, 20, 0, tzinfo=UTC))  # 01:30 IST
    assert manager.should_auto_logout(datetime(2026, 1, 5, 21, 30, tzinfo=UTC))  # 03:00 IST


def test_sebi_compliance_audit_append_and_live_session_assertions(tmp_path: Path) -> None:
    db_path = tmp_path / "audit.db"
    manager = SEBIComplianceManager(SEBIComplianceConfig("ALG-101", db_path, ("ip-allowed",)))
    record = TradeAuditRecord(
        trade_id="TR-1",
        timestamp=create_timestamp(datetime(2026, 1, 5, 4, 0, tzinfo=UTC)),
        exchange=Exchange.NSE,
        symbol="NIFTY",
        side=OrderSide.BUY,
        quantity=create_quantity(Decimal("1")),
        price=create_price(Decimal("100")),
        status=OrderStatus.FILLED,
        strategy_id="strat",
        metadata={"algo_id": "ALG-101"},
    )
    manager.append_audit_record(record)
    fetched = SQLiteStore(db_path).get_trade("TR-1")
    assert fetched is not None
    with pytest.raises(ConfigError, match="allow-list"):
        manager.assert_live_session_allowed("ip-denied", datetime(2026, 1, 5, 20, 0, tzinfo=UTC))
    with pytest.raises(ConfigError, match="logged out"):
        manager.assert_live_session_allowed("ip-allowed", datetime(2026, 1, 5, 21, 30, tzinfo=UTC))
