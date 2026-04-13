"""
Tests for deployment dashboard functions.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from iatb.visualization.deployment_dashboard import (
    build_dashboard_cards,
    get_broker_status,
    get_dashboard_summary,
    get_database_status,
    get_engine_status,
    get_system_status,
)


def test_get_engine_status_not_running() -> None:
    """Test engine status when engine is not running."""
    result = get_engine_status(engine_up=False)

    assert result["status"] == "Engine Unreachable"
    assert result["uptime_seconds"] == 0
    assert result["last_heartbeat"] is None
    assert result["healthy"] is False


def test_get_engine_status_running_no_heartbeat() -> None:
    """Test engine status when running but no heartbeat."""
    result = get_engine_status(engine_up=True, last_heartbeat=None)

    assert result["status"] == "Running"
    assert result["uptime_seconds"] == 0
    assert result["last_heartbeat"] is None
    assert result["healthy"] is True


def test_get_engine_status_running_with_heartbeat() -> None:
    """Test engine status when running with heartbeat."""
    heartbeat_time = datetime.now(UTC) - timedelta(seconds=120)
    result = get_engine_status(engine_up=True, last_heartbeat=heartbeat_time)

    assert result["status"] == "Running"
    assert result["uptime_seconds"] >= 120
    assert result["last_heartbeat"] == heartbeat_time.isoformat()
    assert result["healthy"] is True


def test_get_engine_status_uptime_calculation() -> None:
    """Test engine uptime calculation is accurate."""
    import time

    heartbeat_time = datetime.now(UTC)
    time.sleep(0.1)  # Small delay
    result = get_engine_status(engine_up=True, last_heartbeat=heartbeat_time)

    assert result["uptime_seconds"] >= 0.1
    assert result["uptime_seconds"] < 1.0  # Should be less than 1 second


def test_get_broker_status_token_invalid() -> None:
    """Test broker status when token is invalid."""
    result = get_broker_status(uid="ABC123", balance=Decimal("100000.0"), token_valid=False)

    assert result["status"] == "relogin_required"
    assert result["uid"] is None
    assert result["balance"] is None
    assert "Access token expired" in result["message"]


def test_get_broker_status_token_valid() -> None:
    """Test broker status when token is valid."""
    result = get_broker_status(uid="ABC123", balance=Decimal("100000.0"), token_valid=True)

    assert result["status"] == "connected"
    assert result["uid"] == "ABC123"
    assert result["balance"] == Decimal("100000.0")
    assert "Broker connection active" in result["message"]


def test_get_broker_status_no_uid_balance() -> None:
    """Test broker status with valid token but no uid/balance."""
    result = get_broker_status(uid=None, balance=None, token_valid=True)

    assert result["status"] == "connected"
    assert result["uid"] is None
    assert result["balance"] is None
    assert "Broker connection active" in result["message"]


def test_get_broker_status_negative_balance() -> None:
    """Test broker status handles negative balance."""
    result = get_broker_status(uid="ABC123", balance=Decimal("-5000.0"), token_valid=True)

    assert result["status"] == "connected"
    assert result["uid"] == "ABC123"
    assert result["balance"] == Decimal("-5000.0")


def test_get_system_status_default() -> None:
    """Test system status with default values."""
    result = get_system_status()

    assert result["cpu_percent"] == 0.0
    assert result["memory_percent"] == 0.0
    assert result["disk_percent"] == 0.0
    assert result["healthy"] is True


def test_get_system_status_healthy() -> None:
    """Test system status with healthy values."""
    result = get_system_status(cpu_percent=50.0, memory_percent=60.0, disk_percent=70.0)

    assert result["cpu_percent"] == 50.0
    assert result["memory_percent"] == 60.0
    assert result["disk_percent"] == 70.0
    assert result["healthy"] is True


def test_get_system_status_unhealthy_cpu() -> None:
    """Test system status with unhealthy CPU."""
    result = get_system_status(cpu_percent=95.0, memory_percent=50.0, disk_percent=50.0)

    assert result["cpu_percent"] == 95.0
    assert result["healthy"] is False


def test_get_system_status_unhealthy_memory() -> None:
    """Test system status with unhealthy memory."""
    result = get_system_status(cpu_percent=50.0, memory_percent=95.0, disk_percent=50.0)

    assert result["memory_percent"] == 95.0
    assert result["healthy"] is False


def test_get_system_status_unhealthy_disk() -> None:
    """Test system status with unhealthy disk."""
    result = get_system_status(cpu_percent=50.0, memory_percent=50.0, disk_percent=95.0)

    assert result["disk_percent"] == 95.0
    assert result["healthy"] is False


def test_get_system_status_all_unhealthy() -> None:
    """Test system status with all metrics unhealthy."""
    result = get_system_status(cpu_percent=95.0, memory_percent=95.0, disk_percent=95.0)

    assert result["cpu_percent"] == 95.0
    assert result["memory_percent"] == 95.0
    assert result["disk_percent"] == 95.0
    assert result["healthy"] is False


def test_get_system_status_boundary_healthy() -> None:
    """Test system status at boundary (89.9% is healthy)."""
    result = get_system_status(cpu_percent=89.9, memory_percent=89.9, disk_percent=89.9)

    assert result["healthy"] is True


def test_get_system_status_boundary_unhealthy() -> None:
    """Test system status at boundary (90% is unhealthy)."""
    result = get_system_status(cpu_percent=90.0, memory_percent=90.0, disk_percent=90.0)

    assert result["healthy"] is False


def test_get_database_status_disconnected() -> None:
    """Test database status when disconnected."""
    result = get_database_status(connected=False)

    assert result["connected"] is False
    assert result["query_time_ms"] == 0.0
    assert result["healthy"] is False


def test_get_database_status_connected_slow() -> None:
    """Test database status when connected but slow queries."""
    result = get_database_status(connected=True, query_time_ms=1500.0)

    assert result["connected"] is True
    assert result["query_time_ms"] == 1500.0
    assert result["healthy"] is False


def test_get_database_status_connected_fast() -> None:
    """Test database status when connected with fast queries."""
    result = get_database_status(connected=True, query_time_ms=500.0)

    assert result["connected"] is True
    assert result["query_time_ms"] == 500.0
    assert result["healthy"] is True


def test_get_database_status_boundary_slow() -> None:
    """Test database status at boundary (1000ms is unhealthy)."""
    result = get_database_status(connected=True, query_time_ms=1000.0)

    assert result["connected"] is True
    assert result["query_time_ms"] == 1000.0
    assert result["healthy"] is False


def test_get_database_status_boundary_fast() -> None:
    """Test database status at boundary (999.9ms is healthy)."""
    result = get_database_status(connected=True, query_time_ms=999.9)

    assert result["connected"] is True
    assert result["query_time_ms"] == 999.9
    assert result["healthy"] is True


def test_build_dashboard_cards_all_none() -> None:
    """Test building dashboard cards with all None values."""
    result = build_dashboard_cards(
        engine_status=None,
        broker_status=None,
        system_status=None,
        database_status=None,
    )

    assert "engine" in result
    assert "broker" in result
    assert "system" in result
    assert "database" in result

    # All should have default values
    assert result["engine"]["status"] == "Engine Unreachable"
    assert result["broker"]["status"] == "relogin_required"
    assert result["system"]["healthy"] is True
    assert result["database"]["connected"] is False


def test_build_dashboard_cards_with_status() -> None:
    """Test building dashboard cards with provided status."""
    engine = {"status": "Running", "healthy": True}
    broker = {"status": "connected", "uid": "ABC123"}
    system = {"cpu_percent": 50.0, "healthy": True}
    database = {"connected": True, "healthy": True}

    result = build_dashboard_cards(
        engine_status=engine,
        broker_status=broker,
        system_status=system,
        database_status=database,
    )

    assert result["engine"] == engine
    assert result["broker"] == broker
    assert result["system"] == system
    assert result["database"] == database


def test_build_dashboard_cards_partial_status() -> None:
    """Test building dashboard cards with partial status."""
    engine = {"status": "Running", "healthy": True}

    result = build_dashboard_cards(engine_status=engine)

    assert result["engine"] == engine
    # Others should have defaults
    assert result["broker"]["status"] == "relogin_required"
    assert result["system"]["healthy"] is True
    assert result["database"]["connected"] is False


def test_get_dashboard_summary_all_healthy() -> None:
    """Test dashboard summary when all components are healthy."""
    cards = {
        "engine": {"healthy": True},
        "broker": {"status": "connected"},
        "system": {"healthy": True},
        "database": {"healthy": True},
    }

    result = get_dashboard_summary(cards)

    assert result["overall_status"] == "healthy"
    assert result["components"]["engine"] == "ok"
    assert result["components"]["broker"] == "ok"
    assert result["components"]["system"] == "ok"
    assert result["components"]["database"] == "ok"
    assert "timestamp_utc" in result


def test_get_dashboard_summary_engine_unhealthy() -> None:
    """Test dashboard summary when engine is unhealthy."""
    cards = {
        "engine": {"healthy": False},
        "broker": {"status": "connected"},
        "system": {"healthy": True},
        "database": {"healthy": True},
    }

    result = get_dashboard_summary(cards)

    assert result["overall_status"] == "degraded"
    assert result["components"]["engine"] == "error"
    assert result["components"]["broker"] == "ok"
    assert result["components"]["system"] == "ok"
    assert result["components"]["database"] == "ok"


def test_get_dashboard_summary_broker_unhealthy() -> None:
    """Test dashboard summary when broker is unhealthy."""
    cards = {
        "engine": {"healthy": True},
        "broker": {"status": "relogin_required"},
        "system": {"healthy": True},
        "database": {"healthy": True},
    }

    result = get_dashboard_summary(cards)

    assert result["overall_status"] == "degraded"
    assert result["components"]["engine"] == "ok"
    assert result["components"]["broker"] == "error"
    assert result["components"]["system"] == "ok"
    assert result["components"]["database"] == "ok"


def test_get_dashboard_summary_system_unhealthy() -> None:
    """Test dashboard summary when system is unhealthy."""
    cards = {
        "engine": {"healthy": True},
        "broker": {"status": "connected"},
        "system": {"healthy": False},
        "database": {"healthy": True},
    }

    result = get_dashboard_summary(cards)

    assert result["overall_status"] == "degraded"
    assert result["components"]["engine"] == "ok"
    assert result["components"]["broker"] == "ok"
    assert result["components"]["system"] == "warning"
    assert result["components"]["database"] == "ok"


def test_get_dashboard_summary_database_unhealthy() -> None:
    """Test dashboard summary when database is unhealthy."""
    cards = {
        "engine": {"healthy": True},
        "broker": {"status": "connected"},
        "system": {"healthy": True},
        "database": {"healthy": False},
    }

    result = get_dashboard_summary(cards)

    assert result["overall_status"] == "degraded"
    assert result["components"]["engine"] == "ok"
    assert result["components"]["broker"] == "ok"
    assert result["components"]["system"] == "ok"
    assert result["components"]["database"] == "error"


def test_get_dashboard_summary_all_unhealthy() -> None:
    """Test dashboard summary when all components are unhealthy."""
    cards = {
        "engine": {"healthy": False},
        "broker": {"status": "relogin_required"},
        "system": {"healthy": False},
        "database": {"healthy": False},
    }

    result = get_dashboard_summary(cards)

    assert result["overall_status"] == "degraded"
    assert result["components"]["engine"] == "error"
    assert result["components"]["broker"] == "error"
    assert result["components"]["system"] == "warning"
    assert result["components"]["database"] == "error"


def test_get_dashboard_summary_missing_components() -> None:
    """Test dashboard summary with missing components."""
    cards = {
        "engine": {"healthy": True},
        "broker": {"status": "connected"},
        # Missing system and database
    }

    result = get_dashboard_summary(cards)

    # Missing components should default to unhealthy/error
    assert result["overall_status"] == "degraded"
    assert result["components"]["engine"] == "ok"
    assert result["components"]["broker"] == "ok"
    assert result["components"]["system"] == "warning"  # Missing system defaults to "warning"
    assert result["components"]["database"] == "error"


def test_get_dashboard_summary_timestamp_is_utc() -> None:
    """Test that dashboard summary timestamp is UTC."""
    cards = {
        "engine": {"healthy": True},
        "broker": {"status": "connected"},
        "system": {"healthy": True},
        "database": {"healthy": True},
    }

    result = get_dashboard_summary(cards)

    assert "timestamp_utc" in result
    # Should be a valid ISO format string
    timestamp_str = result["timestamp_utc"]
    assert "Z" in timestamp_str or "+" in timestamp_str


def test_integration_build_and_summarize_dashboard() -> None:
    """Test integration of building and summarizing dashboard."""
    # Build dashboard cards
    cards = build_dashboard_cards(
        engine_status=get_engine_status(engine_up=True),
        broker_status=get_broker_status(
            uid="ABC123",
            balance=Decimal("100000.0"),
            token_valid=True,
        ),
        system_status=get_system_status(
            cpu_percent=50.0,
            memory_percent=60.0,
            disk_percent=70.0,
        ),
        database_status=get_database_status(connected=True, query_time_ms=500.0),
    )

    # Summarize
    summary = get_dashboard_summary(cards)

    # Verify all healthy
    assert summary["overall_status"] == "healthy"
    assert all(status == "ok" for status in summary["components"].values())


def test_integration_unhealthy_dashboard_scenario() -> None:
    """Test integration with unhealthy components."""
    # Build dashboard with unhealthy components
    cards = build_dashboard_cards(
        engine_status=get_engine_status(engine_up=False),
        broker_status=get_broker_status(token_valid=False),
        system_status=get_system_status(cpu_percent=95.0),
        database_status=get_database_status(connected=False),
    )

    # Summarize
    summary = get_dashboard_summary(cards)

    # Verify degraded
    assert summary["overall_status"] == "degraded"
    assert summary["components"]["engine"] == "error"
    assert summary["components"]["broker"] == "error"
    assert summary["components"]["system"] == "warning"  # System unhealthy is "warning" not "error"
    assert summary["components"]["database"] == "error"


def test_system_status_zero_values() -> None:
    """Test system status with all zero values."""
    result = get_system_status(cpu_percent=0.0, memory_percent=0.0, disk_percent=0.0)

    assert result["cpu_percent"] == 0.0
    assert result["memory_percent"] == 0.0
    assert result["disk_percent"] == 0.0
    assert result["healthy"] is True


def test_system_status_max_values() -> None:
    """Test system status with maximum values."""
    result = get_system_status(cpu_percent=100.0, memory_percent=100.0, disk_percent=100.0)

    assert result["cpu_percent"] == 100.0
    assert result["memory_percent"] == 100.0
    assert result["disk_percent"] == 100.0
    assert result["healthy"] is False


def test_database_status_query_time_zero() -> None:
    """Test database status with zero query time."""
    result = get_database_status(connected=True, query_time_ms=0.0)

    assert result["connected"] is True
    assert result["query_time_ms"] == 0.0
    assert result["healthy"] is True


def test_database_status_query_time_large() -> None:
    """Test database status with very large query time."""
    result = get_database_status(connected=True, query_time_ms=10000.0)

    assert result["connected"] is True
    assert result["query_time_ms"] == 10000.0
    assert result["healthy"] is False


def test_engine_status_future_heartbeat() -> None:
    """Test engine status with heartbeat in future (shouldn't happen but test anyway)."""
    future_time = datetime.now(UTC).replace(year=datetime.now(UTC).year + 1)
    result = get_engine_status(engine_up=True, last_heartbeat=future_time)

    # Should still calculate negative uptime (or handle gracefully)
    assert result["status"] == "Running"
    assert result["healthy"] is True


def test_broker_status_empty_uid() -> None:
    """Test broker status with empty UID string."""
    result = get_broker_status(uid="", balance=Decimal("100000.0"), token_valid=True)

    assert result["status"] == "connected"
    assert result["uid"] == ""


def test_get_dashboard_summary_broker_status_variants() -> None:
    """Test dashboard summary with various broker status values."""
    # Test with different broker status values
    for status in ["connected", "relogin_required", "disconnected", "error"]:
        cards = {
            "engine": {"healthy": True},
            "broker": {"status": status},
            "system": {"healthy": True},
            "database": {"healthy": True},
        }

        result = get_dashboard_summary(cards)

        if status == "connected":
            assert result["components"]["broker"] == "ok"
        else:
            assert result["components"]["broker"] == "error"
