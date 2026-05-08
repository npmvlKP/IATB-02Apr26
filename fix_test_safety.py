#!/usr/bin/env python3
"""Fix the TestPreflightChecks class in tests/safety/test_safety.py."""

from pathlib import Path
import re

file_path = Path("tests/safety/test_safety.py")
text = file_path.read_text(encoding="utf-8")

# The clean version of the TestPreflightChecks class
new_class = '''
class TestPreflightChecks:
    @patch("iatb.core.preflight.ClockDriftDetector")
    def test_all_pass(
        self,
        mock_detector_class: MagicMock,
        tmp_path: Path
    ) -> None:
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
        self,
        mock_detector_class: MagicMock,
        tmp_path: Path
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
        self,
        mock_detector_class: MagicMock,
        tmp_path: Path
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
'''

# Ensure we have the correct imports in the file header
if "from datetime import UTC, datetime, timedelta" not in text:
    text = text.replace(
        "from datetime import UTC, datetime\nfrom decimal import Decimal\nfrom pathlib import Path\n\nimport pytest",
        "from datetime import UTC, datetime, timedelta\nfrom decimal import Decimal\nfrom pathlib import Path\nfrom unittest.mock import MagicMock, patch\n\nimport pytest"
    )
else:
    # Ensure patch and MagicMock imports present
    if "from unittest.mock import MagicMock, patch" not in text:
        text = text.replace(
            "from datetime import UTC, datetime, timedelta\nfrom decimal import Decimal\nfrom pathlib import Path\n\nimport pytest",
            "from datetime import UTC, datetime, timedelta\nfrom decimal import Decimal\nfrom pathlib import Path\nfrom unittest.mock import MagicMock, patch\n\nimport pytest"
        )

# Replace the entire TestPreflightChecks class (from its start to the end of its methods)
# Find "class TestPreflightChecks:" and replace through the end of its methods (i.e., until two newlines before next class or EOF)
pattern = r'(class TestPreflightChecks:.*?)(?=\n\nclass |\Z)'
text = re.sub(pattern, new_class.strip() + "\n\n", text, flags=re.DOTALL)

file_path.write_text(text, encoding="utf-8")
print("Successfully patched TestPreflightChecks class.")
