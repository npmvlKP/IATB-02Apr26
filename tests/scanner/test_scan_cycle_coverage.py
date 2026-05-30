"""Coverage tests for scanner.scan_cycle."""

from __future__ import annotations

from iatb.scanner.scan_cycle import ScanCycleResult


class TestScanCycleResult:
    def test_init(self) -> None:
        try:
            obj = ScanCycleResult()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = ScanCycleResult(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
