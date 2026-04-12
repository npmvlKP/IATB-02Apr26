"""
Deployment dashboard for monitoring engine and system status.
"""

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

_LOGGER = logging.getLogger(__name__)


def get_engine_status(
    engine_up: bool = False,
    last_heartbeat: datetime | None = None,
) -> dict[str, Any]:
    """Get engine status for dashboard.

    Args:
        engine_up: Whether the engine is currently running.
        last_heartbeat: Last heartbeat timestamp from engine.

    Returns:
        Status dict with engine state.
    """
    if not engine_up:
        return {
            "status": "Engine Unreachable",
            "uptime_seconds": 0,
            "last_heartbeat": None,
            "healthy": False,
        }

    if last_heartbeat:
        uptime = (datetime.now(UTC) - last_heartbeat).total_seconds()
    else:
        uptime = 0

    return {
        "status": "Running",
        "uptime_seconds": uptime,
        "last_heartbeat": last_heartbeat.isoformat() if last_heartbeat else None,
        "healthy": True,
    }


def get_broker_status(
    uid: str | None = None,
    balance: float | None = None,
    token_valid: bool = False,
) -> dict[str, Any]:
    """Get broker status for dashboard.

    Args:
        uid: User ID from broker.
        balance: Account balance.
        token_valid: Whether access token is valid.

    Returns:
        Status dict with broker state.
    """
    if not token_valid:
        return {
            "status": "relogin_required",
            "uid": None,
            "balance": None,
            "message": "Access token expired. Please re-authenticate.",
        }

    return {
        "status": "connected",
        "uid": uid,
        "balance": balance,
        "message": "Broker connection active.",
    }


def get_system_status(
    cpu_percent: float = 0.0,
    memory_percent: float = 0.0,
    disk_percent: float = 0.0,
) -> dict[str, Any]:
    """Get system resource status.

    Args:
        cpu_percent: CPU usage percentage.
        memory_percent: Memory usage percentage.
        disk_percent: Disk usage percentage.

    Returns:
        Status dict with system metrics.
    """
    return {
        "cpu_percent": cpu_percent,
        "memory_percent": memory_percent,
        "disk_percent": disk_percent,
        "healthy": (cpu_percent < 90 and memory_percent < 90 and disk_percent < 90),
    }


def get_database_status(
    connected: bool = False,
    query_time_ms: float = 0.0,
) -> dict[str, Any]:
    """Get database status.

    Args:
        connected: Whether database is connected.
        query_time_ms: Average query time in milliseconds.

    Returns:
        Status dict with database health.
    """
    return {
        "connected": connected,
        "query_time_ms": query_time_ms,
        "healthy": connected and query_time_ms < 1000,
    }


def build_dashboard_cards(
    engine_status: dict[str, Any] | None = None,
    broker_status: dict[str, Any] | None = None,
    system_status: dict[str, Any] | None = None,
    database_status: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build all dashboard cards.

    Args:
        engine_status: Engine status dict.
        broker_status: Broker status dict.
        system_status: System status dict.
        database_status: Database status dict.

    Returns:
        Dict with all dashboard cards.
    """
    return {
        "engine": engine_status or get_engine_status(engine_up=False),
        "broker": broker_status or get_broker_status(token_valid=False),
        "system": system_status or get_system_status(),
        "database": database_status or get_database_status(),
    }


def get_dashboard_summary(
    cards: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Get overall dashboard summary.

    Args:
        cards: All dashboard cards.

    Returns:
        Summary dict with overall health.
    """
    engine_healthy = cards.get("engine", {}).get("healthy", False)
    broker_healthy = cards.get("broker", {}).get("status") == "connected"
    system_healthy = cards.get("system", {}).get("healthy", False)
    database_healthy = cards.get("database", {}).get("healthy", False)

    overall_healthy = engine_healthy and broker_healthy and system_healthy and database_healthy

    return {
        "overall_status": "healthy" if overall_healthy else "degraded",
        "components": {
            "engine": "ok" if engine_healthy else "error",
            "broker": "ok" if broker_healthy else "error",
            "system": "ok" if system_healthy else "warning",
            "database": "ok" if database_healthy else "error",
        },
        "timestamp_utc": datetime.now(UTC).isoformat(),
    }
