"""
Tests for start_master.py script.
"""

import asyncio
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest


class MockHTTPResponse:
    """Mock HTTP response object for testing."""

    def __init__(self, status: int, body: str = "OK"):
        self.status = status
        self.body = body.encode() if isinstance(body, str) else body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return self.body


class TestStartMaster:
    """Tests for start_master script functions."""

    @pytest.mark.skip(reason="Requires actual engine startup")
    def test_start_engine(self) -> None:
        """Test start_engine function."""
        # This test requires actual engine startup, skip for now
        pass

    @pytest.mark.asyncio
    async def test_wait_for_health_endpoint_success(self) -> None:
        """Test wait_for_health_endpoint when endpoint is available immediately."""
        from scripts.start_master import wait_for_health_endpoint

        mock_response = MockHTTPResponse(status=200, body='{"status": "healthy"}')

        with patch("scripts.start_master.urllib.request.urlopen", return_value=mock_response):
            result = await wait_for_health_endpoint(timeout_seconds=30)
            assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_health_endpoint_retries_then_success(self) -> None:
        """Test wait_for_health_endpoint with retries before success."""
        from scripts.start_master import wait_for_health_endpoint

        mock_response = MockHTTPResponse(status=200, body='{"status": "healthy"}')
        call_count = [0]

        def urlopen_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise URLError("Connection refused")
            return mock_response

        with patch("scripts.start_master.urllib.request.urlopen", side_effect=urlopen_side_effect):
            result = await wait_for_health_endpoint(timeout_seconds=10)
            assert result is True
            assert call_count[0] >= 3

    @pytest.mark.asyncio
    async def test_wait_for_health_endpoint_timeout(self) -> None:
        """Test wait_for_health_endpoint when endpoint never becomes available."""
        from scripts.start_master import wait_for_health_endpoint

        with patch(
            "scripts.start_master.urllib.request.urlopen",
            side_effect=URLError("Connection refused"),
        ):
            result = await wait_for_health_endpoint(timeout_seconds=2)
            assert result is False

    @pytest.mark.asyncio
    async def test_wait_for_health_endpoint_non_200_status(self) -> None:
        """Test wait_for_health_endpoint when endpoint returns non-200 status."""
        from scripts.start_master import wait_for_health_endpoint

        mock_response = MockHTTPResponse(status=500, body='{"status": "error"}')

        with patch("scripts.start_master.urllib.request.urlopen", return_value=mock_response):
            result = await wait_for_health_endpoint(timeout_seconds=2)
            assert result is False

    @pytest.mark.asyncio
    async def test_wait_for_health_endpoint_custom_timeout(self) -> None:
        """Test wait_for_health_endpoint with custom timeout."""
        from scripts.start_master import wait_for_health_endpoint

        with patch(
            "scripts.start_master.urllib.request.urlopen",
            side_effect=URLError("Connection refused"),
        ):
            # Use very short timeout to test quickly
            result = await wait_for_health_endpoint(timeout_seconds=1)
            assert result is False

    @pytest.mark.asyncio
    async def test_wait_for_health_endpoint_non_blocking(self) -> None:
        """Test that wait_for_health_endpoint doesn't block the event loop."""
        from scripts.start_master import wait_for_health_endpoint

        mock_response = MockHTTPResponse(status=200, body='{"status": "healthy"}')
        call_count = [0]

        def urlopen_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 2:
                raise URLError("Connection refused")
            return mock_response

        with patch("scripts.start_master.urllib.request.urlopen", side_effect=urlopen_side_effect):
            # Create a task that should complete without blocking
            task = asyncio.create_task(wait_for_health_endpoint(timeout_seconds=5))

            # Create another task to verify event loop isn't blocked
            async def dummy_task():
                await asyncio.sleep(0.1)
                return "dummy"

            dummy = asyncio.create_task(dummy_task())

            # Wait for both to complete
            result, dummy_result = await asyncio.gather(task, dummy)

            assert result is True
            assert dummy_result == "dummy"

    def test_start_master_import(self) -> None:
        """Test that start_master module can be imported."""
        import asyncio

        import scripts.start_master as sm

        assert hasattr(sm, "start_engine")
        assert hasattr(sm, "wait_for_health_endpoint")
        # Verify it's an async function
        assert asyncio.iscoroutinefunction(sm.wait_for_health_endpoint)
        assert hasattr(sm, "start_dashboard")
        assert hasattr(sm, "main")

    @patch("scripts.start_master.subprocess.Popen")
    def test_start_dashboard_creates_subprocess(self, mock_popen: MagicMock) -> None:
        """Test that start_dashboard creates a subprocess with stdout=None."""
        from scripts.start_master import start_dashboard

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        result = start_dashboard()
        assert result is not None
        assert result.pid == 12345
        mock_popen.assert_called_once()

        # Verify stdout=None is used to avoid pipe buffer blocking
        call_args = mock_popen.call_args
        assert (
            call_args.kwargs.get("stdout") is None
        ), "stdout should be None to avoid pipe buffer blocking"

    @patch("scripts.start_master.subprocess.Popen")
    def test_start_dashboard_handles_errors(self, mock_popen: MagicMock) -> None:
        """Test that start_dashboard handles errors gracefully."""
        from scripts.start_master import start_dashboard

        mock_popen.side_effect = Exception("Dashboard start failed")

        result = start_dashboard()
        assert result is None
