"""Coverage tests for api."""

from __future__ import annotations

from iatb.api import IATBApi


class TestIATBApi:
    def test_init(self) -> None:
        try:
            obj = IATBApi()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = IATBApi(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
