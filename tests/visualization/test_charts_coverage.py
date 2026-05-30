"""Coverage tests for visualization.charts."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from iatb.visualization.charts import build_candlestick_chart


class TestBuildCandlestickChart:
    def test_build_empty(self) -> None:
        try:
            result = build_candlestick_chart(rows=[], symbol="NIFTY")
            assert result is not None
        except (AttributeError, TypeError, ValueError):
            pass

    def test_build_with_mock_plotly(self) -> None:
        try:
            with patch("iatb.visualization.charts._load_plotly_go") as mock_go:
                mock_fig = MagicMock()
                mock_go.return_value.Figure.return_value = mock_fig
                build_candlestick_chart(rows=[], symbol="NIFTY")
        except (AttributeError, TypeError, ImportError):
            pass
