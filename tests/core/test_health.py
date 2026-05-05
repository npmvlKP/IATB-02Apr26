"""
Tests for health endpoint server.

DEPRECATED: HealthServer is deprecated in favor of FastAPI health endpoints.
Tests for HealthServer have been removed as the class has been deleted.
Comprehensive tests for FastAPI health endpoints are available in test_fastapi_app.py:
- test_liveness_check
- test_readiness_check_all_ready
- test_readiness_check_engine_status
- test_readiness_check_event_bus_status
- test_readiness_check_api_status
"""

import warnings

from iatb.core.health import HealthServer


def test_health_server_deprecation_warning() -> None:
    """Test that instantiating HealthServer raises a deprecation warning."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        HealthServer()
        health_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(health_warnings) >= 1
        assert "deprecated" in str(health_warnings[0].message).lower()
