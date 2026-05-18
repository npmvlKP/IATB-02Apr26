"""
Comprehensive coverage tests for vader_analyzer.py.

Tests VADER sentiment analyzer wrapper.
"""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError


class TestVaderAnalyzer:
    """Test VADER analyzer."""

    def test_analyze_positive_text(self):
        """Test analyzing positive text."""
        try:
            from iatb.sentiment.vader_analyzer import VaderAnalyzer

            analyzer = VaderAnalyzer()
            text = "This is amazing! Great job!"

            result = analyzer.analyze(text)

            assert result.source == "vader"
            assert result.score > Decimal("0")
            assert result.label == "POSITIVE"
        except ConfigError:
            pytest.skip("VADER dependency not available")

    def test_analyze_negative_text(self):
        """Test analyzing negative text."""
        try:
            from iatb.sentiment.vader_analyzer import VaderAnalyzer

            analyzer = VaderAnalyzer()
            text = "This is terrible! Very bad!"

            result = analyzer.analyze(text)

            assert result.source == "vader"
            assert result.score < Decimal("0")
            assert result.label == "NEGATIVE"
        except ConfigError:
            pytest.skip("VADER dependency not available")

    def test_analyze_neutral_text(self):
        """Test analyzing neutral text."""
        try:
            from iatb.sentiment.vader_analyzer import VaderAnalyzer

            analyzer = VaderAnalyzer()
            text = "This is a statement."

            result = analyzer.analyze(text)

            assert result.source == "vader"
            assert Decimal("-0.1") <= result.score <= Decimal("0.1")
        except ConfigError:
            pytest.skip("VADER dependency not available")

    def test_analyze_empty_text_raises_error(self):
        """Test that empty text raises ConfigError."""
        try:
            from iatb.sentiment.vader_analyzer import VaderAnalyzer

            analyzer = VaderAnalyzer()

            with pytest.raises(ConfigError, match="text cannot be empty"):
                analyzer.analyze("")
        except ConfigError:
            pytest.skip("VADER dependency not available")

    def test_analyze_whitespace_text_raises_error(self):
        """Test that whitespace-only text raises ConfigError."""
        try:
            from iatb.sentiment.vader_analyzer import VaderAnalyzer

            analyzer = VaderAnalyzer()

            with pytest.raises(ConfigError, match="text cannot be empty"):
                analyzer.analyze("   ")
        except ConfigError:
            pytest.skip("VADER dependency not available")

    def test_score_clamped_to_range(self):
        """Test that score is clamped to [-1, 1]."""
        try:
            from iatb.sentiment.vader_analyzer import VaderAnalyzer

            analyzer = VaderAnalyzer()
            # Extremely positive text
            text = "AMAZING INCREDIBLE FANTASTIC WONDERFUL PERFECT"

            result = analyzer.analyze(text)

            assert result.score <= Decimal("1")
            assert result.score >= Decimal("-1")
        except ConfigError:
            pytest.skip("VADER dependency not available")

    def test_confidence_in_range(self):
        """Test that confidence is in [0, 1]."""
        try:
            from iatb.sentiment.vader_analyzer import VaderAnalyzer

            analyzer = VaderAnalyzer()
            text = "Test text"

            result = analyzer.analyze(text)

            assert Decimal("0") <= result.confidence <= Decimal("1")
        except ConfigError:
            pytest.skip("VADER dependency not available")

    def test_weight_attribute(self):
        """Test that analyzer has weight attribute."""
        try:
            from iatb.sentiment.vader_analyzer import VaderAnalyzer

            assert VaderAnalyzer.weight == Decimal("0.2")
        except ConfigError:
            pytest.skip("VADER dependency not available")
