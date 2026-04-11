"""
Tests for health endpoint server.
"""

import random
import time
from urllib.error import HTTPError
from urllib.request import urlopen

import numpy as np
import pytest
import torch
from iatb.core.health import HealthServer

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_health_endpoint_returns_ok_payload() -> None:
    """Health endpoint should return HTTP 200 and status payload."""
    server = HealthServer(host="127.0.0.1", port=0)
    server.start()
    try:
        time.sleep(0.05)
        with urlopen(f"http://127.0.0.1:{server.port}/health", timeout=2) as response:  # noqa: S310
            body = response.read().decode("utf-8")
            status = response.status
        assert status == 200
        assert body == '{"status":"ok"}'
    finally:
        server.stop()


def test_non_health_endpoint_returns_not_found() -> None:
    """Unknown endpoint should return 404."""
    server = HealthServer(host="127.0.0.1", port=0)
    server.start()
    try:
        time.sleep(0.05)
        with pytest.raises(HTTPError, match="HTTP Error 404"):
            urlopen(f"http://127.0.0.1:{server.port}/not-found", timeout=2)  # noqa: S310
    finally:
        server.stop()
