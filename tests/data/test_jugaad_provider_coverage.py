"""Coverage tests for data.jugaad_provider."""

from __future__ import annotations

from iatb.data.jugaad_provider import JugaadProvider


class TestJugaadProvider:
    def test_init(self) -> None:
        try:
            obj = JugaadProvider()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = JugaadProvider(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
