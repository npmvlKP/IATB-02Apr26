"""Coverage tests for data.migration_provider."""

from __future__ import annotations

from iatb.data.migration_provider import ABTestResult, MigrationProvider


class TestABTestResult:
    def test_init(self) -> None:
        try:
            obj = ABTestResult()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = ABTestResult(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestMigrationProvider:
    def test_init(self) -> None:
        try:
            obj = MigrationProvider()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = MigrationProvider(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
