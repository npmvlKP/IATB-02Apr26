"""
Tests for start_master.py script.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestStartMaster:
    """Tests for start_master script functions."""

    @pytest.mark.skip(reason="Requires actual engine startup")
    def test_start_engine(self) -> None:
        """Test start_engine function."""

        # This test requires actual engine startup, skip for now
        pass

    @pytest.mark.skip(reason="Requires actual health endpoint")
    def test_wait_for_health_endpoint(self) -> None:
        """Test wait_for_health_endpoint function."""

        # This test requires actual health endpoint, skip for now
        pass

    def test_start_master_import(self) -> None:
        """Test that start_master module can be imported."""
        import scripts.start_master as sm

        assert hasattr(sm, "start_engine")
        assert hasattr(sm, "wait_for_health_endpoint")
        assert hasattr(sm, "start_dashboard")
        assert hasattr(sm, "main")

    @patch("scripts.start_master.subprocess.Popen")
    def test_start_dashboard_creates_subprocess(self, mock_popen: MagicMock) -> None:
        """Test that start_dashboard creates a subprocess."""
        from scripts.start_master import start_dashboard

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        result = start_dashboard()
        assert result is not None
        assert result.pid == 12345
        mock_popen.assert_called_once()

    @patch("scripts.start_master.subprocess.Popen")
    def test_start_dashboard_handles_errors(self, mock_popen: MagicMock) -> None:
        """Test that start_dashboard handles errors gracefully."""
        from scripts.start_master import start_dashboard

        mock_popen.side_effect = Exception("Dashboard start failed")

        result = start_dashboard()
        assert result is None
