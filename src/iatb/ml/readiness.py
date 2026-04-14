"""
ML readiness checks for scan cycle integration.

This module provides functions to check ML model availability
before running scan cycles, enabling graceful degradation.
"""

import logging

from iatb.ml.model_registry import ModelStatus, RegistryStatus, get_registry

_LOGGER = logging.getLogger(__name__)


def _log_model_health(status: RegistryStatus) -> None:
    """Log individual model health status.

    Args:
        status: RegistryStatus object with health information.
    """
    for model_name, health in status.model_health.items():
        status_str = "✓" if health.status == ModelStatus.AVAILABLE else "✗"
        _LOGGER.info(
            "  %s %s: %s (fallback: %s)",
            status_str,
            model_name,
            health.status.value,
            "yes" if health.fallback_available else "no",
        )
        if health.error_message:
            _LOGGER.debug("    Error: %s", health.error_message)


def _determine_overall_status(status: RegistryStatus, errors: list[str]) -> ModelStatus:
    """Determine overall ML model status.

    Args:
        status: RegistryStatus object with health information.
        errors: List to collect error messages.

    Returns:
        Overall ModelStatus.
    """
    if status.available_models == 0:
        error_msg = "No ML models available"
        _LOGGER.error("  ✗ %s", error_msg)
        errors.append(error_msg)
        return ModelStatus.ERROR
    elif status.unavailable_models > 0:
        _LOGGER.warning(
            "  ⚠ Operating in degraded mode with %d unavailable model(s)",
            status.unavailable_models,
        )
        return ModelStatus.DEGRADED
    else:
        _LOGGER.info("  ✓ All ML models available")
        return ModelStatus.AVAILABLE


def check_ml_readiness(errors: list[str]) -> ModelStatus:
    """Check ML model readiness before scan cycle.

    This performs health checks on all ML models to detect Windows DLL issues
    or other problems early, enabling graceful degradation.

    Args:
        errors: List to collect error messages.

    Returns:
        Overall ModelStatus (AVAILABLE if at least one model works).
    """
    _LOGGER.info("Checking ML model readiness...")

    try:
        registry = get_registry()
        status = registry.initialize()

        _LOGGER.info(
            "ML Status: %d available, %d degraded, %d unavailable",
            status.available_models,
            status.degraded_models,
            status.unavailable_models,
        )

        # Log individual model status
        _log_model_health(status)

        # Determine overall status
        return _determine_overall_status(status, errors)

    except Exception as exc:
        error_msg = f"ML readiness check failed: {exc}"
        _LOGGER.error("  ✗ %s", error_msg)
        errors.append(error_msg)
        return ModelStatus.ERROR
