#!/usr/bin/env python
"""Patch test_safety.py file to add ClockDriftDetector mocking."""

import re
from pathlib import Path

test_file = Path("tests/safety/test_safety.py")
content = test_file.read_text(encoding="utf-8")

# Ensure needed imports are present
if "from unittest.mock import MagicMock, patch" not in content:
    content = content.replace(
        "from datetime import UTC, datetime\nfrom decimal import Decimal\n"
        "from pathlib import Path\n\nimport pytest",
        "from datetime import UTC, datetime, timedelta\nfrom decimal import "
        "Decimal\nfrom pathlib import Path\nfrom unittest.mock import MagicMock, "
        "patch\nimport pytest",
    )

# Define fixed TestPreflightChecks class
new_class = """class TestPreflightChecks:
    @patch("iatb.core.preflight.ClockDriftDetector")
    def test_all_pass(self, mock_detector_class: MagicMock, tmp_path: Path) -> None:
        from iatb.core.preflight import run_preflight_checks

        # Mock clock drift to be within threshold
        mock_detector = MagicMock()
        mock_detector.check_drift.return_value = timedelta(seconds=0.5)
        mock_detector_class.return_value = mock_detector

        executor = PaperExecutor()
        ks = KillSwitch(executor)
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        audit_path = tmp_path / "audit" / "trades.sqlite"
        assert run_preflight_checks(executor, ks, data_dir, audit_path) is True

    @patch("iatb.core.preflight.ClockDriftDetector")
    def test_engaged_kill_switch_fails(
        self, mock_detector_class: MagicMock, tmp_path: Path
    ) -> None:
        from iatb.core.preflight import run_preflight_checks

        # Mock clock drift to be within threshold
        mock_detector = MagicMock()
        mock_detector.check_drift.return_value = timedelta(seconds=0.5)
        mock_detector_class.return_value = mock_detector

        executor = PaperExecutor()
        ks = KillSwitch(executor)
        ks.engage("test", _NOW)
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        audit_path = tmp_path / "audit" / "trades.sqlite"
        assert run_preflight_checks(executor, ks, data_dir, audit_path) is False

    @patch("iatb.core.preflight.ClockDriftDetector")
    def test_missing_data_dir_fails(
        self, mock_detector_class: MagicMock, tmp_path: Path
    ) -> None:
        from iatb.core.preflight import run_preflight_checks

        # Mock clock drift to be within threshold
        mock_detector = MagicMock()
        mock_detector.check_drift.return_value = timedelta(seconds=0.5)
        mock_detector_class.return_value = mock_detector

        executor = PaperExecutor()
        ks = KillSwitch(executor)
        missing = tmp_path / "nonexistent"
        audit_path = tmp_path / "audit" / "trades.sqlite"
        assert run_preflight_checks(executor, ks, missing, audit_path) is False
"""

# Replace TestPreflightChecks class
pattern = r"class TestPreflightChecks:.*?(?=\n{2,2}class |\Z)"
content = re.sub(pattern, new_class + "\n\n", content, flags=re.DOTALL)

test_file.write_text(content, encoding="utf-8")
