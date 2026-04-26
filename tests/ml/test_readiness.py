"""Tests for ml.readiness module."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from iatb.ml.model_registry import ModelStatus, RegistryStatus
from iatb.ml.readiness import (
    _determine_overall_status,
    _log_model_health,
    check_ml_readiness,
)


def test_determine_overall_status_all_available() -> None:
    health = MagicMock()
    health.status = ModelStatus.AVAILABLE
    status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=3,
        available_models=3,
        degraded_models=0,
        unavailable_models=0,
        model_health={"a": health, "b": health, "c": health},
    )
    errors: list[str] = []
    result = _determine_overall_status(status, errors)
    assert result == ModelStatus.AVAILABLE


def test_determine_overall_status_none_available() -> None:
    health = MagicMock()
    health.status = ModelStatus.UNAVAILABLE
    status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=2,
        available_models=0,
        degraded_models=0,
        unavailable_models=2,
        model_health={"a": health, "b": health},
    )
    errors: list[str] = []
    result = _determine_overall_status(status, errors)
    assert result == ModelStatus.ERROR
    assert len(errors) == 1


def test_determine_overall_status_degraded() -> None:
    h_avail = MagicMock()
    h_avail.status = ModelStatus.AVAILABLE
    h_unavail = MagicMock()
    h_unavail.status = ModelStatus.UNAVAILABLE
    status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=2,
        available_models=1,
        degraded_models=0,
        unavailable_models=1,
        model_health={"a": h_avail, "b": h_unavail},
    )
    errors: list[str] = []
    result = _determine_overall_status(status, errors)
    assert result == ModelStatus.DEGRADED


def test_log_model_health(caplog: object) -> None:
    health = MagicMock()
    health.status = ModelStatus.AVAILABLE
    health.fallback_available = False
    health.error_message = None
    status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=1,
        available_models=1,
        degraded_models=0,
        unavailable_models=0,
        model_health={"test": health},
    )
    _log_model_health(status)


def test_check_ml_readiness_exception() -> None:
    errors: list[str] = []
    with patch("iatb.ml.readiness.get_registry", side_effect=RuntimeError("test")):
        result = check_ml_readiness(errors)
        assert result == ModelStatus.ERROR
        assert len(errors) == 1
