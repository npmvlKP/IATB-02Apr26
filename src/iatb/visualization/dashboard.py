"""
Streamlit dashboard helpers for multi-market monitoring.
"""

import importlib
from collections.abc import Mapping

from iatb.core.exceptions import ConfigError

REQUIRED_MARKET_TABS = ("NSE EQ", "NSE F&O", "BSE", "MCX", "Currency F&O", "Crypto")


def build_dashboard_payload(
    market_payloads: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    payload: dict[str, dict[str, object]] = {}
    for tab in REQUIRED_MARKET_TABS:
        source = market_payloads.get(tab, {})
        payload[tab] = dict(source)
    return payload


def render_dashboard(
    payload: Mapping[str, Mapping[str, object]], streamlit_module: object | None = None
) -> list[str]:
    streamlit = streamlit_module or _load_streamlit()
    title = getattr(streamlit, "title", None)
    tabs_fn = getattr(streamlit, "tabs", None)
    if not callable(title) or not callable(tabs_fn):
        msg = "streamlit module missing title()/tabs() required for dashboard rendering"
        raise ConfigError(msg)
    title("IATB Multi-Market Dashboard")
    tabs = tabs_fn(list(REQUIRED_MARKET_TABS))
    rendered: list[str] = []
    for index, tab_name in enumerate(REQUIRED_MARKET_TABS):
        panel = tabs[index]
        write_fn = getattr(panel, "write", None)
        if callable(write_fn):
            write_fn(payload.get(tab_name, {}))
        rendered.append(tab_name)
    return rendered


def _load_streamlit() -> object:
    try:
        return importlib.import_module("streamlit")
    except ModuleNotFoundError as exc:
        msg = "streamlit dependency is required for dashboard rendering"
        raise ConfigError(msg) from exc
