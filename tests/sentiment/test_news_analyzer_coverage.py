"""
Comprehensive coverage tests for news_analyzer.py.

Tests news sentiment analysis, keyword extraction, and error paths.
"""

from decimal import Decimal

from iatb.sentiment.news_analyzer import (
    NewsAnalyzer,
    extract_keywords,
)


class TestExtractKeywords:
    """Test extract_keywords function."""

    def test_extract_basic_keywords(self) -> None:
        """Test basic keyword extraction."""
        text = "Company reports strong earnings growth in Q3."
        keywords = extract_keywords(text)
        assert len(keywords) > 0
        assert "earnings" in keywords or "growth" in keywords

    def test_extract_keywords_empty_text(self) -> None:
        """Test with empty text."""
        text = ""
        keywords = extract_keywords(text)
        assert keywords == []

    def test_extract_keywords_stopwords(self) -> None:
        """Test keyword filtering with stopwords."""
        text = "The company reported strong earnings in the third quarter."
        keywords = extract_keywords(text)
        # Should not contain stopwords
        assert "the" not in keywords
        assert "in" not in keywords

    def test_extract_keywords_special_chars(self) -> None:
        """Test with special characters."""
        text = "Earnings up 50%! Strong growth ahead."
        keywords = extract_keywords(text)
        assert len(keywords) > 0


class TestNewsAnalyzer:
    """Test NewsAnalyzer class."""

    def test_analyzer_initialization(self) -> None:
        """Test analyzer initialization."""
        analyzer = NewsAnalyzer()
        assert analyzer is not None

    def test_analyze_positive_news(self) -> None:
        """Test positive news analysis."""
        analyzer = NewsAnalyzer()
        text = "Company reports record earnings, beats expectations by 20%."
        result = analyzer.analyze(text)
        assert result > Decimal("0.5")

    def test_analyze_negative_news(self) -> None:
        """Test negative news analysis."""
        analyzer = NewsAnalyzer()
        text = "Company misses earnings target, downgrades guidance."
        result = analyzer.analyze(text)
        assert result < Decimal("0.5")

    def test_analyze_neutral_news(self) -> None:
        """Test neutral news analysis."""
        analyzer = NewsAnalyzer()
        text = "Company reports quarterly results as expected."
        result = analyzer.analyze(text)
        # Should be around 0.5
        assert Decimal("0.4") < result < Decimal("0.6")

    def test_analyze_empty_text(self) -> None:
        """Test with empty text."""
        analyzer = NewsAnalyzer()
        text = ""
        result = analyzer.analyze(text)
        # Should return neutral sentiment
        assert result == Decimal("0.5")

    def test_analyze_with_keywords(self) -> None:
        """Test analysis with keyword extraction."""
        analyzer = NewsAnalyzer(extract_keywords=True)
        text = "Strong earnings growth, revenue up 30%."
        result = analyzer.analyze(text)
        assert Decimal("0.0") <= result <= Decimal("1.0")

    def test_analyze_batch(self) -> None:
        """Test batch analysis."""
        analyzer = NewsAnalyzer()
        news_items = [
            {"title": "Strong earnings", "content": "Company beats expectations"},
            {"title": "Weak guidance", "content": "Company downgrades outlook"},
        ]
        results = analyzer.analyze_batch(news_items)
        assert len(results) == 2
        # First should be positive, second negative
        assert results[0] > results[1]
