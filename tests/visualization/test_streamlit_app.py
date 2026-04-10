"""Tests for streamlit_app.py dashboard entry point."""

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest


@dataclass
class _MockSidebar:
    headers: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)

    def header(self, text: str) -> None:
        self.headers.append(text)

    def write(self, text: str) -> None:
        self.writes.append(text)


@dataclass
class _MockColumn:
    metric_calls: list[tuple[str, str]] = field(default_factory=list)
    title_calls: list[str] = field(default_factory=list)

    def metric(self, label: str, value: str) -> None:
        self.metric_calls.append((label, value))

    def title(self, text: str) -> None:
        self.title_calls.append(text)

    def __enter__(self) -> "_MockColumn":
        return self

    def __exit__(self, *args: object) -> None:
        pass


@dataclass
class _MockStreamlit:
    sidebar: _MockSidebar = field(default_factory=_MockSidebar)
    page_config_calls: list[dict] = field(default_factory=list)
    title_calls: list[str] = field(default_factory=list)
    metric_calls: list[tuple[str, str]] = field(default_factory=list)
    header_calls: list[str] = field(default_factory=list)
    info_calls: list[str] = field(default_factory=list)
    success_calls: list[str] = field(default_factory=list)
    warning_calls: list[str] = field(default_factory=list)
    error_calls: list[str] = field(default_factory=list)
    button_returns: list[bool] = field(default_factory=lambda: [False])
    button_calls: list[tuple[str, dict]] = field(default_factory=list)
    spinner_contexts: int = 0
    rerun_calls: int = 0
    dataframe_calls: list[object] = field(default_factory=list)
    json_calls: list[object] = field(default_factory=list)
    caption_calls: list[str] = field(default_factory=list)
    subheader_calls: list[str] = field(default_factory=list)
    markdown_calls: list[str] = field(default_factory=list)
    tab_objs: list["_MockTab"] = field(default_factory=list)
    columns_returns: list[list["_MockColumn"]] = field(default_factory=list)

    def set_page_config(self, **kwargs: object) -> None:
        self.page_config_calls.append(dict(kwargs))

    def title(self, text: str) -> None:
        self.title_calls.append(text)

    def metric(self, label: str, value: str) -> None:
        self.metric_calls.append((label, value))

    def header(self, text: str) -> None:
        self.header_calls.append(text)

    def info(self, text: str) -> None:
        self.info_calls.append(text)

    def success(self, text: str) -> None:
        self.success_calls.append(text)

    def warning(self, text: str) -> None:
        self.warning_calls.append(text)

    def error(self, text: str) -> None:
        self.error_calls.append(text)

    def button(self, label: str, **kwargs: object) -> bool:
        self.button_calls.append((label, dict(kwargs)))
        return self.button_returns.pop(0) if self.button_returns else False

    def spinner(self, text: str) -> "_MockSpinner":
        _ = text
        self.spinner_contexts += 1
        return _MockSpinner(self)

    def rerun(self) -> None:
        self.rerun_calls += 1

    def dataframe(self, data: object, **kwargs: object) -> None:
        self.dataframe_calls.append(data)

    def json(self, data: object) -> None:
        self.json_calls.append(data)

    def caption(self, text: str) -> None:
        self.caption_calls.append(text)

    def subheader(self, text: str) -> None:
        self.subheader_calls.append(text)

    def markdown(self, text: str) -> None:
        self.markdown_calls.append(text)

    def columns(self, spec: object) -> list[_MockColumn]:
        if isinstance(spec, list):
            n = len(spec)
        else:
            n = int(spec)
        cols = [_MockColumn() for _ in range(n)]
        self.columns_returns.append(cols)
        return cols

    def tabs(self, names: list[str]) -> list["_MockTab"]:
        self.tab_objs = [_MockTab(self) for _ in names]
        return self.tab_objs


@dataclass
class _MockSpinner:
    mock_st: _MockStreamlit

    def __enter__(self) -> "_MockSpinner":
        return self

    def __exit__(self, *args: object) -> None:
        pass


@dataclass
class _MockTab:
    mock_st: _MockStreamlit
    header_calls: list[str] = field(default_factory=list)
    info_calls: list[str] = field(default_factory=list)
    success_calls: list[str] = field(default_factory=list)
    warning_calls: list[str] = field(default_factory=list)
    error_calls: list[str] = field(default_factory=list)
    dataframe_calls: list[object] = field(default_factory=list)

    def header(self, text: str) -> None:
        self.header_calls.append(text)

    def info(self, text: str) -> None:
        self.info_calls.append(text)

    def success(self, text: str) -> None:
        self.success_calls.append(text)

    def warning(self, text: str) -> None:
        self.warning_calls.append(text)

    def error(self, text: str) -> None:
        self.error_calls.append(text)

    def dataframe(self, data: object, **kwargs: object) -> None:
        self.dataframe_calls.append(data)

    def __enter__(self) -> "_MockTab":
        return self

    def __exit__(self, *args: object) -> None:
        pass


@pytest.fixture()
def mock_st() -> _MockStreamlit:
    return _MockStreamlit()


@patch("iatb.visualization.streamlit_app.st")
def test_setup_page_config(mock_st_module: MagicMock) -> None:
    mock_st_module.set_page_config = MagicMock()
    from iatb.visualization.streamlit_app import setup_page_config

    setup_page_config()
    mock_st_module.set_page_config.assert_called_once_with(
        page_title="IATB Paper Trading Dashboard",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )


@patch("iatb.visualization.streamlit_app.st")
def test_render_header(mock_st_module: MagicMock, mock_st: _MockStreamlit) -> None:
    mock_st_module.columns = mock_st.columns
    mock_st_module.title = mock_st.title
    mock_st_module.metric = mock_st.metric
    from iatb.visualization.streamlit_app import render_header

    render_header()
    assert len(mock_st.title_calls) == 1
    assert "IATB" in mock_st.title_calls[0]
    assert len(mock_st.metric_calls) == 2


@patch("iatb.visualization.streamlit_app.st")
def test_render_sidebar(mock_st_module: MagicMock, mock_st: _MockStreamlit) -> None:
    mock_st_module.sidebar = mock_st.sidebar
    from iatb.visualization.streamlit_app import render_sidebar

    render_sidebar()
    assert len(mock_st.sidebar.headers) >= 1


@patch("iatb.visualization.streamlit_app.st")
def test_render_scanner_tab(mock_st_module: MagicMock, mock_st: _MockStreamlit) -> None:
    mock_st_module.header = mock_st.header
    mock_st_module.info = mock_st.info
    mock_st_module.success = mock_st.success
    mock_st_module.warning = mock_st.warning
    mock_st_module.button = mock_st.button
    mock_st_module.spinner = mock_st.spinner
    mock_st_module.rerun = mock_st.rerun
    from iatb.visualization.streamlit_app import render_scanner_tab

    render_scanner_tab()
    assert len(mock_st.header_calls) == 1
    assert len(mock_st.info_calls) == 1
    assert len(mock_st.success_calls) == 1


@patch("iatb.visualization.streamlit_app.st")
def test_render_scanner_tab_button_click(
    mock_st_module: MagicMock, mock_st: _MockStreamlit
) -> None:
    mock_st_module.header = mock_st.header
    mock_st_module.info = mock_st.info
    mock_st_module.success = mock_st.success
    mock_st_module.warning = mock_st.warning
    mock_st_module.button = mock_st.button
    mock_st_module.spinner = mock_st.spinner
    mock_st_module.rerun = mock_st.rerun
    mock_st.button_returns = [True]
    from iatb.visualization.streamlit_app import render_scanner_tab

    render_scanner_tab()
    assert mock_st.rerun_calls == 1


@patch("iatb.visualization.streamlit_app.st")
def test_render_scanner_tab_exception(mock_st_module: MagicMock, mock_st: _MockStreamlit) -> None:
    mock_st_module.header = mock_st.header
    mock_st_module.info = mock_st.info
    mock_st_module.success = MagicMock(side_effect=RuntimeError("test error"))
    mock_st_module.warning = mock_st.warning
    mock_st_module.button = mock_st.button
    mock_st_module.spinner = mock_st.spinner
    mock_st_module.rerun = mock_st.rerun
    from iatb.visualization.streamlit_app import render_scanner_tab

    render_scanner_tab()
    assert len(mock_st.warning_calls) == 1
    assert "not fully initialized" in mock_st.warning_calls[0]


@patch("iatb.visualization.streamlit_app.st")
def test_render_trades_tab_no_db(mock_st_module: MagicMock, mock_st: _MockStreamlit) -> None:
    mock_st_module.header = mock_st.header
    mock_st_module.info = mock_st.info
    mock_st_module.success = mock_st.success
    mock_st_module.error = mock_st.error
    mock_st_module.dataframe = mock_st.dataframe
    from iatb.visualization.streamlit_app import render_trades_tab

    render_trades_tab()
    assert len(mock_st.header_calls) == 1
    assert len(mock_st.info_calls) == 2


@patch("iatb.visualization.streamlit_app.st")
@patch("iatb.visualization.streamlit_app.Path")
def test_render_trades_tab_with_db(
    mock_path: MagicMock, mock_st_module: MagicMock, mock_st: _MockStreamlit
) -> None:
    mock_path.return_value.exists.return_value = True
    mock_st_module.header = mock_st.header
    mock_st_module.info = mock_st.info
    mock_st_module.success = mock_st.success
    mock_st_module.error = mock_st.error
    mock_st_module.dataframe = mock_st.dataframe
    from iatb.visualization.streamlit_app import render_trades_tab

    mock_conn = MagicMock()
    mock_conn.row_factory = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = []
    mock_conn.close = MagicMock()

    with patch("builtins.__import__", side_effect=_mock_import_with_sqlite3(mock_conn)):
        render_trades_tab()
    assert len(mock_st.success_calls) == 1
    assert len(mock_st.info_calls) == 2


@patch("iatb.visualization.streamlit_app.st")
@patch("iatb.visualization.streamlit_app.Path")
def test_render_trades_tab_with_db_rows(
    mock_path: MagicMock, mock_st_module: MagicMock, mock_st: _MockStreamlit
) -> None:
    mock_path.return_value.exists.return_value = True
    mock_st_module.header = mock_st.header
    mock_st_module.info = mock_st.info
    mock_st_module.success = mock_st.success
    mock_st_module.error = mock_st.error
    mock_st_module.dataframe = mock_st.dataframe
    from iatb.visualization.streamlit_app import render_trades_tab

    mock_row = MagicMock()
    mock_row.__iter__ = MagicMock(return_value=iter([("col1", "val1")]))
    mock_conn = MagicMock()
    mock_conn.row_factory = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = [mock_row]
    mock_conn.close = MagicMock()

    with patch("builtins.__import__", side_effect=_mock_import_with_sqlite3(mock_conn)):
        render_trades_tab()
    assert len(mock_st.dataframe_calls) == 1


@patch("iatb.visualization.streamlit_app.st")
@patch("iatb.visualization.streamlit_app.Path")
def test_render_trades_tab_db_error(
    mock_path: MagicMock, mock_st_module: MagicMock, mock_st: _MockStreamlit
) -> None:
    mock_path.return_value.exists.return_value = True
    mock_st_module.header = mock_st.header
    mock_st_module.info = mock_st.info
    mock_st_module.success = mock_st.success
    mock_st_module.error = mock_st.error
    mock_st_module.dataframe = mock_st.dataframe
    from iatb.visualization.streamlit_app import render_trades_tab

    mock_conn = MagicMock()
    mock_conn.row_factory = MagicMock()
    mock_conn.execute.side_effect = RuntimeError("db error")
    mock_conn.close = MagicMock()

    with patch("builtins.__import__", side_effect=_mock_import_with_sqlite3(mock_conn)):
        render_trades_tab()
    assert len(mock_st.error_calls) == 1


@patch("iatb.visualization.streamlit_app.st")
def test_render_system_tab_engine_unreachable(
    mock_st_module: MagicMock, mock_st: _MockStreamlit
) -> None:
    mock_st_module.header = mock_st.header
    mock_st_module.subheader = mock_st.subheader
    mock_st_module.columns = mock_st.columns
    mock_st_module.success = mock_st.success
    mock_st_module.warning = mock_st.warning
    mock_st_module.json = mock_st.json
    from iatb.visualization.streamlit_app import render_system_tab

    with patch("urllib.request.urlopen", side_effect=TimeoutError("engine down")):
        render_system_tab()
    assert len(mock_st.warning_calls) >= 1


@patch("iatb.visualization.streamlit_app.st")
def test_render_system_tab_engine_online(
    mock_st_module: MagicMock, mock_st: _MockStreamlit
) -> None:
    mock_st_module.header = mock_st.header
    mock_st_module.subheader = mock_st.subheader
    mock_st_module.columns = mock_st.columns
    mock_st_module.success = mock_st.success
    mock_st_module.warning = mock_st.warning
    mock_st_module.json = mock_st.json
    from iatb.visualization.streamlit_app import render_system_tab

    mock_response = MagicMock()
    mock_response.read.return_value = b'{"status":"ok"}'
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        render_system_tab()
    assert len(mock_st.success_calls) >= 1


@patch("iatb.visualization.streamlit_app.st")
def test_main(mock_st_module: MagicMock, mock_st: _MockStreamlit) -> None:
    mock_st_module.set_page_config = mock_st.set_page_config
    mock_st_module.title = mock_st.title
    mock_st_module.metric = mock_st.metric
    mock_st_module.columns = mock_st.columns
    mock_st_module.header = mock_st.header
    mock_st_module.subheader = mock_st.subheader
    mock_st_module.info = mock_st.info
    mock_st_module.success = mock_st.success
    mock_st_module.warning = mock_st.warning
    mock_st_module.error = mock_st.error
    mock_st_module.button = mock_st.button
    mock_st_module.spinner = mock_st.spinner
    mock_st_module.rerun = mock_st.rerun
    mock_st_module.dataframe = mock_st.dataframe
    mock_st_module.json = mock_st.json
    mock_st_module.caption = mock_st.caption
    mock_st_module.markdown = mock_st.markdown
    mock_st_module.sidebar = mock_st.sidebar
    mock_st_module.tabs = mock_st.tabs
    from iatb.visualization.streamlit_app import main

    main()
    assert len(mock_st.page_config_calls) == 1
    assert len(mock_st.title_calls) == 1
    assert len(mock_st.tab_objs) == 3


@patch("iatb.visualization.streamlit_app.st")
def test_main_with_env_vars(mock_st_module: MagicMock, mock_st: _MockStreamlit) -> None:
    mock_st_module.set_page_config = mock_st.set_page_config
    mock_st_module.title = mock_st.title
    mock_st_module.metric = mock_st.metric
    mock_st_module.columns = mock_st.columns
    mock_st_module.header = mock_st.header
    mock_st_module.subheader = mock_st.subheader
    mock_st_module.info = mock_st.info
    mock_st_module.success = mock_st.success
    mock_st_module.warning = mock_st.warning
    mock_st_module.error = mock_st.error
    mock_st_module.button = mock_st.button
    mock_st_module.spinner = mock_st.spinner
    mock_st_module.rerun = mock_st.rerun
    mock_st_module.dataframe = mock_st.dataframe
    mock_st_module.json = mock_st.json
    mock_st_module.caption = mock_st.caption
    mock_st_module.markdown = mock_st.markdown
    mock_st_module.sidebar = mock_st.sidebar
    mock_st_module.tabs = mock_st.tabs
    from iatb.visualization.streamlit_app import main

    env = {
        "IATB_MODE": "paper",
        "LIVE_TRADING_ENABLED": "false",
        "IATB_CONFIG_PATH": "config/settings.toml",
    }
    with patch.dict("os.environ", env, clear=False):
        main()
    assert len(mock_st.page_config_calls) == 1
    assert len(mock_st.json_calls) == 1


def _mock_import_with_sqlite3(mock_conn: MagicMock):
    def _import(name: str, *args: object, **kwargs: object):
        if name == "sqlite3":
            mock_sqlite3 = MagicMock()
            mock_sqlite3.connect.return_value = mock_conn
            mock_sqlite3.Row = MagicMock()
            return mock_sqlite3
        return __builtins__.__import__(name, *args, **kwargs)  # type: ignore[attr-defined]

    return _import
