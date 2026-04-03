from dataclasses import dataclass, field

import pytest
from iatb.core.exceptions import ConfigError
from iatb.visualization.dashboard import (
    REQUIRED_MARKET_TABS,
    build_dashboard_payload,
    render_dashboard,
)


@dataclass
class _FakeTab:
    writes: list[object] = field(default_factory=list)

    def write(self, value: object) -> None:
        self.writes.append(value)


class _FakeStreamlit:
    def __init__(self) -> None:
        self.titles: list[str] = []
        self._tabs = [_FakeTab() for _ in REQUIRED_MARKET_TABS]

    def title(self, text: str) -> None:
        self.titles.append(text)

    def tabs(self, names: list[str]) -> list[_FakeTab]:
        _ = names
        return self._tabs


def test_dashboard_payload_and_render() -> None:
    payload = build_dashboard_payload({"NSE EQ": {"signals": 3}, "Crypto": {"signals": 5}})
    assert set(payload.keys()) == set(REQUIRED_MARKET_TABS)
    streamlit = _FakeStreamlit()
    rendered = render_dashboard(payload, streamlit)
    assert rendered == list(REQUIRED_MARKET_TABS)
    assert streamlit.titles == ["IATB Multi-Market Dashboard"]


def test_dashboard_missing_streamlit_api_raises() -> None:
    with pytest.raises(ConfigError, match="missing title\\(\\)/tabs\\(\\)"):
        render_dashboard({}, streamlit_module=object())
