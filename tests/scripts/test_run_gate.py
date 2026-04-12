"""
Tests for run_gate.py script (Option B: Individual Quality Gate Execution)
"""

import random
import subprocess
from pathlib import Path

import numpy as np
import pytest
import torch

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def _result(
    args: list[str],
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    """Create a mock subprocess result."""
    return subprocess.CompletedProcess(
        args=args,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class _Runner:
    """Mock subprocess runner that returns predefined responses."""

    def __init__(self, responses: list[subprocess.CompletedProcess[str]]) -> None:
        self._responses = responses
        self.calls: list[list[str]] = []

    def __call__(
        self,
        args: list[str],
        capture_output: bool = False,
        text: bool = False,
        check: bool = False,
        timeout: int = 300,
    ) -> subprocess.CompletedProcess[str]:
        """Mock subprocess.run call."""
        _ = capture_output, text, check, timeout
        self.calls.append(args)
        return self._responses.pop(0)


class TestRunGate:
    """Test individual quality gate execution functionality."""

    def test_run_command_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test successful command execution."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import run_command

        responses = [_result(["echo", "test"], stdout="test\n")]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        success, output = run_command(["echo", "test"], "Test Command")
        assert success is True
        assert "test" in output

    def test_run_command_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test command execution failure."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import run_command

        responses = [_result(["false"], returncode=1, stderr="error\n")]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        success, output = run_command(["false"], "Failed Command")
        assert success is False
        assert "error" in output

    def test_check_gate_g1_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test G1 (lint) pass."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import check_gate_g1

        responses = [_result(["poetry", "run", "ruff"], stdout="")]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        success, output = check_gate_g1()
        assert success is True
        assert "PASS" in output

    def test_check_gate_g1_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test G1 (lint) fail."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import check_gate_g1

        responses = [_result(["poetry", "run", "ruff"], stdout="error1\nerror2\n")]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        success, output = check_gate_g1()
        assert success is False
        assert "FAIL" in output

    def test_check_gate_g2_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test G2 (format) pass."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import check_gate_g2

        responses = [_result(["poetry", "run", "ruff", "format"], stdout="")]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        success, output = check_gate_g2()
        assert success is True
        assert "PASS" in output

    def test_check_gate_g2_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test G2 (format) fail."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import check_gate_g2

        responses = [_result(["poetry", "run", "ruff", "format"], stdout="would reformat\n")]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        success, output = check_gate_g2()
        assert success is False
        assert "would reformat" in output

    def test_check_gate_g3_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test G3 (types) pass."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import check_gate_g3

        responses = [_result(["poetry", "run", "mypy"], stdout="")]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        success, output = check_gate_g3()
        assert success is True
        assert "PASS" in output

    def test_check_gate_g3_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test G3 (types) fail."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import check_gate_g3

        responses = [
            _result(
                ["poetry", "run", "mypy"],
                returncode=1,
                stdout="error: missing type\n",
            )
        ]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        success, output = check_gate_g3()
        assert success is False

    def test_check_gate_g4_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test G4 (security) pass."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import check_gate_g4

        responses = [_result(["poetry", "run", "bandit"], stdout="")]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        success, output = check_gate_g4()
        assert success is True
        assert "PASS" in output

    def test_check_gate_g4_low_severity_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test G4 (security) with only low-severity issues."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import check_gate_g4

        responses = [_result(["poetry", "run", "bandit"], stdout="Low severity issue\n")]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        success, output = check_gate_g4()
        assert success is True  # Low severity is acceptable

    def test_check_gate_g5_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test G5 (secrets) pass."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import check_gate_g5

        responses = [_result(["gitleaks"], stdout="No leaks found\n")]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        success, output = check_gate_g5()
        assert success is True
        assert "PASS" in output

    def test_check_gate_g5_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test G5 (secrets) fail."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import check_gate_g5

        responses = [_result(["gitleaks"], returncode=1, stdout="Leak found: API_KEY\n")]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        success, output = check_gate_g5()
        assert success is False

    def test_check_gate_g6_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test G6 (tests) pass."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import check_gate_g6

        responses = [_result(["poetry", "run", "pytest"], stdout="TOTAL 100 0 0 0 95.0%\n")]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        success, output = check_gate_g6()
        assert success is True
        assert "PASS" in output

    def test_check_gate_g6_fail_low_coverage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test G6 (tests) fail due to low coverage."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import check_gate_g6

        responses = [
            _result(
                ["poetry", "run", "pytest"],
                returncode=1,
                stdout="TOTAL 100 0 0 0 85.0%\n",
            )
        ]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        success, output = check_gate_g6()
        assert success is False

    def test_check_gate_g7_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test G7 (no float in financial paths) pass."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import check_gate_g7

        responses = [
            _result(
                ["python", "scripts/verify_g7_g8_g9.py"],
                stdout="G7 - No Float: [PASS]\n",
            )
        ]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        success, output = check_gate_g7()
        assert success is True
        assert "PASS" in output

    def test_check_gate_g8_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test G8 (no naive datetime) pass."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import check_gate_g8

        responses = [
            _result(
                ["python", "scripts/verify_g7_g8_g9.py"],
                stdout="G8 - No Naive Datetime: [PASS]\n",
            )
        ]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        success, output = check_gate_g8()
        assert success is True
        assert "PASS" in output

    def test_check_gate_g9_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test G9 (no print statements) pass."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import check_gate_g9

        responses = [
            _result(
                ["python", "scripts/verify_g7_g8_g9.py"],
                stdout="G9 - No Print: [PASS]\n",
            )
        ]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        success, output = check_gate_g9()
        assert success is True
        assert "PASS" in output

    def test_check_gate_g10_pass(self) -> None:
        """Test G10 (function size) pass (placeholder)."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import check_gate_g10

        success, output = check_gate_g10()
        assert success is True  # Placeholder always passes
        assert "placeholder" in output.lower()

    def test_gates_registry_complete(self) -> None:
        """Test that all gates are registered."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import GATES

        expected_gates = {"G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10"}
        assert set(GATES.keys()) == expected_gates

    def test_run_command_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test command execution timeout."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import run_command

        def timeout_run(*args, **kwargs):
            raise subprocess.TimeoutExpired("test", 300)

        monkeypatch.setattr("subprocess.run", timeout_run)

        success, output = run_command(["sleep", "3600"], "Timeout Test")
        assert success is False
        assert "timed out" in output.lower()

    def test_run_command_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test command execution exception."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from run_gate import run_command

        def exception_run(*args, **kwargs):
            raise ValueError("test error")

        monkeypatch.setattr("subprocess.run", exception_run)

        success, output = run_command(["invalid"], "Exception Test")
        assert success is False
        assert "ERROR" in output
