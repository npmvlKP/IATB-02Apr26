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


def test_health_module_deprecation_warning() -> None:
    """Test that importing health module raises deprecation warning."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        import iatb.core.health as health_module

        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "deprecated and removed" in str(w[0].message).lower()
        assert health_module is not None
