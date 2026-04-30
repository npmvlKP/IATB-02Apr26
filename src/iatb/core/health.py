"""
HTTP health endpoint support for runtime/container probes.

DEPRECATED: This module is deprecated in favor of FastAPI health endpoints.
Use /health/live and /health/ready endpoints from fastapi_app.py instead.

The HealthServer class has been removed as it caused port conflicts with FastAPI.
All health check functionality is now provided by FastAPI endpoints:
- /health/live - Liveness check (always returns 200 if process is running)
- /health/ready - Readiness check (returns 200 only if all components are ready)
"""

import warnings

warnings.warn(
    "HealthServer module is deprecated and removed. "
    "Use FastAPI /health/live and /health/ready endpoints instead.",
    DeprecationWarning,
    stacklevel=2,
)
