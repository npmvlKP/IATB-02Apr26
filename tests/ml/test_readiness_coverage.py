"""Comprehensive tests for ml.readiness module with full coverage.

Test Scenarios:
- All models available → AVAILABLE
- Some unavailable → DEGRADED
- Zero available → ERROR
- Registry exception → ERROR
- Mock: get_registry() + RegistryStatus
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from iatb.ml.model_registry import ModelHealth, ModelStatus, RegistryStatus
from iatb.ml.readiness import (
    _determine_overall_status,
    _log_model_health,
    check_ml_readiness,
)

# ---------------------------------------------------------------------------
# Test _log_model_health Function
# ---------------------------------------------------------------------------


def test_log_model_health_all_available(caplog: object) -> None:
    """Test logging model health when all models are available."""
    health = MagicMock()
    health.status = ModelStatus.AVAILABLE
    health.fallback_available = False
    health.error_message = None
    status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=3,
        available_models=3,
        degraded_models=0,
        unavailable_models=0,
        model_health={"model1": health, "model2": health, "model3": health},
    )

    with caplog.at_level("INFO"):
        _log_model_health(status)

    # Verify INFO logs for all models
    assert any("✓ model1:" in record.message for record in caplog.records)
    assert any("✓ model2:" in record.message for record in caplog.records)
    assert any("✓ model3:" in record.message for record in caplog.records)


def test_log_model_health_mixed_status(caplog: object) -> None:
    """Test logging model health with mixed status."""
    health_avail = MagicMock()
    health_avail.status = ModelStatus.AVAILABLE
    health_avail.fallback_available = False
    health_avail.error_message = None

    health_unavail = MagicMock()
    health_unavail.status = ModelStatus.UNAVAILABLE
    health_unavail.fallback_available = True
    health_unavail.error_message = "Test error"

    status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=2,
        available_models=1,
        degraded_models=0,
        unavailable_models=1,
        model_health={"model1": health_avail, "model2": health_unavail},
    )

    with caplog.at_level("INFO"):
        _log_model_health(status)

    # Verify correct symbols and fallback status
    assert any(
        "✓ model1: available (fallback: no)" in record.message
        for record in caplog.records
    )
    assert any(
        "✗ model2: unavailable (fallback: yes)" in record.message
        for record in caplog.records
    )


def test_log_model_health_with_error_message(caplog: object) -> None:
    """Test logging model health with error message."""
    health = MagicMock()
    health.status = ModelStatus.ERROR
    health.fallback_available = False
    health.error_message = "DLL load failed"

    status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=1,
        available_models=0,
        degraded_models=0,
        unavailable_models=1,
        model_health={"model1": health},
    )

    with caplog.at_level("DEBUG"):
        _log_model_health(status)

    # Verify DEBUG log with error message
    assert any("Error: DLL load failed" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# Test _determine_overall_status Function
# ---------------------------------------------------------------------------


def test_determine_overall_status_all_available() -> None:
    """Test overall status when all models are available."""
    health = MagicMock()
    health.status = ModelStatus.AVAILABLE
    status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=3,
        available_models=3,
        degraded_models=0,
        unavailable_models=0,
        model_health={"model1": health, "model2": health, "model3": health},
    )
    errors: list[str] = []

    result = _determine_overall_status(status, errors)

    assert result == ModelStatus.AVAILABLE
    assert len(errors) == 0


def test_determine_overall_status_all_degraded() -> None:
    """Test overall status when all models are degraded."""
    health = MagicMock()
    health.status = ModelStatus.DEGRADED
    status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=2,
        available_models=0,
        degraded_models=2,
        unavailable_models=0,
        model_health={"model1": health, "model2": health},
    )
    errors: list[str] = []

    result = _determine_overall_status(status, errors)

    # Degraded models count as unavailable for overall status
    assert result == ModelStatus.ERROR
    assert len(errors) == 1
    assert "No ML models available" in errors[0]


def test_determine_overall_status_none_available() -> None:
    """Test overall status when no models are available."""
    health_unavail = MagicMock()
    health_unavail.status = ModelStatus.UNAVAILABLE
    health_error = MagicMock()
    health_error.status = ModelStatus.ERROR
    status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=2,
        available_models=0,
        degraded_models=0,
        unavailable_models=2,
        model_health={"model1": health_unavail, "model2": health_error},
    )
    errors: list[str] = []

    result = _determine_overall_status(status, errors)

    assert result == ModelStatus.ERROR
    assert len(errors) == 1
    assert "No ML models available" in errors[0]


def test_determine_overall_status_partial_degraded() -> None:
    """Test overall status when some models are unavailable (degraded mode)."""
    health_avail = MagicMock()
    health_avail.status = ModelStatus.AVAILABLE
    health_unavail = MagicMock()
    health_unavail.status = ModelStatus.UNAVAILABLE
    status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=2,
        available_models=1,
        degraded_models=0,
        unavailable_models=1,
        model_health={"model1": health_avail, "model2": health_unavail},
    )
    errors: list[str] = []

    result = _determine_overall_status(status, errors)

    assert result == ModelStatus.DEGRADED
    assert len(errors) == 0


def test_determine_overall_status_single_unavailable() -> None:
    """Test overall status with single unavailable model."""
    health_avail = MagicMock()
    health_avail.status = ModelStatus.AVAILABLE
    health_unavail = MagicMock()
    health_unavail.status = ModelStatus.ERROR
    status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=3,
        available_models=2,
        degraded_models=0,
        unavailable_models=1,
        model_health={
            "model1": health_avail,
            "model2": health_avail,
            "model3": health_unavail,
        },
    )
    errors: list[str] = []

    result = _determine_overall_status(status, errors)

    assert result == ModelStatus.DEGRADED
    assert len(errors) == 0


def test_determine_overall_status_boundary_zero_available() -> None:
    """Test boundary case: exactly zero available models."""
    health = MagicMock()
    health.status = ModelStatus.ERROR
    status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=1,
        available_models=0,
        degraded_models=0,
        unavailable_models=1,
        model_health={"model1": health},
    )
    errors: list[str] = []

    result = _determine_overall_status(status, errors)

    assert result == ModelStatus.ERROR
    assert len(errors) == 1


def test_determine_overall_status_boundary_one_available() -> None:
    """Test boundary case: exactly one available model."""
    health_avail = MagicMock()
    health_avail.status = ModelStatus.AVAILABLE
    health_unavail = MagicMock()
    health_unavail.status = ModelStatus.UNAVAILABLE
    status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=2,
        available_models=1,
        degraded_models=0,
        unavailable_models=1,
        model_health={"model1": health_avail, "model2": health_unavail},
    )
    errors: list[str] = []

    result = _determine_overall_status(status, errors)

    assert result == ModelStatus.DEGRADED
    assert len(errors) == 0


# ---------------------------------------------------------------------------
# Test check_ml_readiness Function
# ---------------------------------------------------------------------------


def test_check_ml_readiness_all_available(caplog: object) -> None:
    """Test ML readiness check when all models are available."""
    mock_registry = MagicMock()
    mock_status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=3,
        available_models=3,
        degraded_models=0,
        unavailable_models=0,
        model_health={},
    )
    mock_registry.initialize.return_value = mock_status
    errors: list[str] = []

    with patch("iatb.ml.readiness.get_registry", return_value=mock_registry):
        with caplog.at_level("INFO"):
            result = check_ml_readiness(errors)

    assert result == ModelStatus.AVAILABLE
    assert len(errors) == 0
    assert any("All ML models available" in record.message for record in caplog.records)


def test_check_ml_readiness_degraded_mode(caplog: object) -> None:
    """Test ML readiness check in degraded mode."""
    mock_registry = MagicMock()
    mock_status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=3,
        available_models=2,
        degraded_models=0,
        unavailable_models=1,
        model_health={},
    )
    mock_registry.initialize.return_value = mock_status
    errors: list[str] = []

    with patch("iatb.ml.readiness.get_registry", return_value=mock_registry):
        with caplog.at_level("WARNING"):
            result = check_ml_readiness(errors)

    assert result == ModelStatus.DEGRADED
    assert len(errors) == 0
    assert any(
        "Operating in degraded mode with 1 unavailable model(s)" in record.message
        for record in caplog.records
    )


def test_check_ml_readiness_no_models_available(caplog: object) -> None:
    """Test ML readiness check when no models are available."""
    mock_registry = MagicMock()
    mock_status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=2,
        available_models=0,
        degraded_models=0,
        unavailable_models=2,
        model_health={},
    )
    mock_registry.initialize.return_value = mock_status
    errors: list[str] = []

    with patch("iatb.ml.readiness.get_registry", return_value=mock_registry):
        with caplog.at_level("ERROR"):
            result = check_ml_readiness(errors)

    assert result == ModelStatus.ERROR
    assert len(errors) == 1
    assert "No ML models available" in errors[0]
    assert any("No ML models available" in record.message for record in caplog.records)


def test_check_ml_readiness_registry_exception(caplog: object) -> None:
    """Test ML readiness check when registry raises exception."""
    errors: list[str] = []

    with patch(
        "iatb.ml.readiness.get_registry", side_effect=RuntimeError("Registry failed")
    ):
        with caplog.at_level("ERROR"):
            result = check_ml_readiness(errors)

    assert result == ModelStatus.ERROR
    assert len(errors) == 1
    assert "ML readiness check failed: Registry failed" in errors[0]
    assert any(
        "ML readiness check failed: Registry failed" in record.message
        for record in caplog.records
    )


def test_check_ml_readiness_initialize_exception(caplog: object) -> None:
    """Test ML readiness check when initialize() raises exception."""
    mock_registry = MagicMock()
    mock_registry.initialize.side_effect = ValueError("Initialize error")
    errors: list[str] = []

    with patch("iatb.ml.readiness.get_registry", return_value=mock_registry):
        with caplog.at_level("ERROR"):
            result = check_ml_readiness(errors)

    assert result == ModelStatus.ERROR
    assert len(errors) == 1
    assert "ML readiness check failed: Initialize error" in errors[0]


def test_check_ml_readiness_log_status_summary(caplog: object) -> None:
    """Test that status summary is logged correctly."""
    mock_registry = MagicMock()
    mock_status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=3,
        available_models=2,
        degraded_models=1,
        unavailable_models=0,
        model_health={},
    )
    mock_registry.initialize.return_value = mock_status
    errors: list[str] = []

    with patch("iatb.ml.readiness.get_registry", return_value=mock_registry):
        with caplog.at_level("INFO"):
            check_ml_readiness(errors)

    # Check status summary log
    assert any(
        "ML Status: 2 available, 1 degraded, 0 unavailable" in record.message
        for record in caplog.records
    )


def test_check_ml_readiness_with_real_model_health(caplog: object) -> None:
    """Test ML readiness check with real ModelHealth objects."""
    mock_registry = MagicMock()

    # Create real ModelHealth objects
    health1 = ModelHealth(
        model_name="model1",
        status=ModelStatus.AVAILABLE,
        last_check=datetime.now(UTC),
        error_message=None,
        load_time_ms=None,
        dll_loaded=True,
        fallback_available=False,
    )
    health2 = ModelHealth(
        model_name="model2",
        status=ModelStatus.UNAVAILABLE,
        last_check=datetime.now(UTC),
        error_message="Test error",
        load_time_ms=None,
        dll_loaded=False,
        fallback_available=True,
    )

    mock_status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=2,
        available_models=1,
        degraded_models=0,
        unavailable_models=1,
        model_health={"model1": health1, "model2": health2},
    )
    mock_registry.initialize.return_value = mock_status
    errors: list[str] = []

    with patch("iatb.ml.readiness.get_registry", return_value=mock_registry):
        with caplog.at_level("INFO"):
            result = check_ml_readiness(errors)

    assert result == ModelStatus.DEGRADED
    assert len(errors) == 0


def test_check_ml_readiness_multiple_unavailable_models(caplog: object) -> None:
    """Test ML readiness check with multiple unavailable models."""
    mock_registry = MagicMock()
    mock_status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=5,
        available_models=2,
        degraded_models=0,
        unavailable_models=3,
        model_health={},
    )
    mock_registry.initialize.return_value = mock_status
    errors: list[str] = []

    with patch("iatb.ml.readiness.get_registry", return_value=mock_registry):
        with caplog.at_level("WARNING"):
            result = check_ml_readiness(errors)

    assert result == ModelStatus.DEGRADED
    assert len(errors) == 0
    assert any(
        "Operating in degraded mode with 3 unavailable model(s)" in record.message
        for record in caplog.records
    )


def test_check_ml_readiness_exception_with_custom_error(caplog: object) -> None:
    """Test ML readiness check with custom exception type."""

    class CustomError(Exception):
        pass

    errors: list[str] = []

    with patch(
        "iatb.ml.readiness.get_registry", side_effect=CustomError("Custom error")
    ):
        with caplog.at_level("ERROR"):
            result = check_ml_readiness(errors)

    assert result == ModelStatus.ERROR
    assert len(errors) == 1
    assert "ML readiness check failed: Custom error" in errors[0]


def test_check_ml_readiness_empty_registry(caplog: object) -> None:
    """Test ML readiness check with empty registry (0 models)."""
    mock_registry = MagicMock()
    mock_status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=0,
        available_models=0,
        degraded_models=0,
        unavailable_models=0,
        model_health={},
    )
    mock_registry.initialize.return_value = mock_status
    errors: list[str] = []

    with patch("iatb.ml.readiness.get_registry", return_value=mock_registry):
        with caplog.at_level("ERROR"):
            result = check_ml_readiness(errors)

    assert result == ModelStatus.ERROR
    assert len(errors) == 1
    assert "No ML models available" in errors[0]


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


def test_full_readiness_check_happy_path() -> None:
    """Test full readiness check with all models available."""
    mock_registry = MagicMock()

    # Create real ModelHealth objects
    health1 = ModelHealth(
        model_name="finbert",
        status=ModelStatus.AVAILABLE,
        last_check=datetime.now(UTC),
        error_message=None,
        load_time_ms=Decimal("100"),
        dll_loaded=True,
        fallback_available=False,
    )
    health2 = ModelHealth(
        model_name="vader",
        status=ModelStatus.AVAILABLE,
        last_check=datetime.now(UTC),
        error_message=None,
        load_time_ms=Decimal("50"),
        dll_loaded=True,
        fallback_available=False,
    )
    health3 = ModelHealth(
        model_name="aion",
        status=ModelStatus.AVAILABLE,
        last_check=datetime.now(UTC),
        error_message=None,
        load_time_ms=Decimal("75"),
        dll_loaded=True,
        fallback_available=False,
    )

    mock_status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=3,
        available_models=3,
        degraded_models=0,
        unavailable_models=0,
        model_health={"finbert": health1, "vader": health2, "aion": health3},
    )
    mock_registry.initialize.return_value = mock_status
    errors: list[str] = []

    with patch("iatb.ml.readiness.get_registry", return_value=mock_registry):
        result = check_ml_readiness(errors)

    assert result == ModelStatus.AVAILABLE
    assert len(errors) == 0


def test_full_readiness_check_degraded_with_fallback() -> None:
    """Test full readiness check with degraded mode but fallback available."""
    mock_registry = MagicMock()

    # FinBERT unavailable but has fallback
    health1 = ModelHealth(
        model_name="finbert",
        status=ModelStatus.ERROR,
        last_check=datetime.now(UTC),
        error_message="DLL load failed",
        load_time_ms=None,
        dll_loaded=False,
        fallback_available=True,
    )
    # VADER available (fallback)
    health2 = ModelHealth(
        model_name="vader",
        status=ModelStatus.AVAILABLE,
        last_check=datetime.now(UTC),
        error_message=None,
        load_time_ms=Decimal("50"),
        dll_loaded=True,
        fallback_available=False,
    )
    # AION available
    health3 = ModelHealth(
        model_name="aion",
        status=ModelStatus.AVAILABLE,
        last_check=datetime.now(UTC),
        error_message=None,
        load_time_ms=Decimal("75"),
        dll_loaded=True,
        fallback_available=False,
    )

    mock_status = RegistryStatus(
        timestamp=datetime.now(UTC),
        total_models=3,
        available_models=2,
        degraded_models=0,
        unavailable_models=1,
        model_health={"finbert": health1, "vader": health2, "aion": health3},
    )
    mock_registry.initialize.return_value = mock_status
    errors: list[str] = []

    with patch("iatb.ml.readiness.get_registry", return_value=mock_registry):
        result = check_ml_readiness(errors)

    assert result == ModelStatus.DEGRADED
    assert len(errors) == 0
