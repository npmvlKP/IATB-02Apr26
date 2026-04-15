"""
Tests for ML Model Registry.

Tests model health checking, availability tracking, and graceful degradation.
"""

import sys
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from iatb.ml.model_registry import (
    ModelHealth,
    ModelRegistry,
    ModelStatus,
    RegistryStatus,
    get_registry,
)


class TestModelStatus:
    """Test ModelStatus enum."""

    def test_status_values(self) -> None:
        """Test ModelStatus enum values."""
        assert ModelStatus.AVAILABLE.value == "available"
        assert ModelStatus.UNAVAILABLE.value == "unavailable"
        assert ModelStatus.DEGRADED.value == "degraded"
        assert ModelStatus.ERROR.value == "error"


class TestModelHealth:
    """Test ModelHealth dataclass."""

    def test_model_health_creation(self) -> None:
        """Test ModelHealth object creation."""
        health = ModelHealth(
            model_name="test_model",
            status=ModelStatus.AVAILABLE,
            last_check=datetime.now(UTC),
            error_message=None,
            load_time_ms=Decimal("100.5"),
            dll_loaded=True,
            fallback_available=True,
        )
        assert health.model_name == "test_model"
        assert health.status == ModelStatus.AVAILABLE
        assert health.dll_loaded is True
        assert health.fallback_available is True

    def test_model_health_defaults(self) -> None:
        """Test ModelHealth with default values."""
        health = ModelHealth(
            model_name="test_model",
            status=ModelStatus.AVAILABLE,
            last_check=datetime.now(UTC),
        )
        assert health.error_message is None
        assert health.load_time_ms is None
        assert health.dll_loaded is True
        assert health.fallback_available is False


class TestModelRegistry:
    """Test ModelRegistry class."""

    def test_registry_initialization(self) -> None:
        """Test registry initialization."""
        registry = ModelRegistry()
        assert registry._health == {}
        assert registry._initialized is False

    def test_check_pytorch_availability_success(self) -> None:
        """Test PyTorch availability check when available."""
        # Mock torch module
        mock_torch = MagicMock()
        mock_torch.__version__ = "2.0.0"
        mock_torch.tensor.return_value.sum.return_value.item.return_value = 6.0

        # Inject mock into sys.modules
        torch_backup = sys.modules.get("torch")
        sys.modules["torch"] = mock_torch

        try:
            registry = ModelRegistry()
            status = registry.check_pytorch_availability()

            assert status == ModelStatus.AVAILABLE
            mock_torch.tensor.assert_called_once()
        finally:
            # Restore original module
            if torch_backup is None:
                sys.modules.pop("torch", None)
            else:
                sys.modules["torch"] = torch_backup

    def test_check_pytorch_availability_not_installed(self) -> None:
        """Test PyTorch availability check when not installed."""
        # Use patch.object to mock the built-in import at the module level
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "torch":
                raise ImportError("torch not found")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            registry = ModelRegistry()
            status = registry.check_pytorch_availability()
            assert status == ModelStatus.UNAVAILABLE

    def test_check_pytorch_availability_error(self) -> None:
        """Test PyTorch availability check with error."""
        # Mock torch module that raises error
        mock_torch = MagicMock()
        mock_torch.tensor.side_effect = RuntimeError("DLL load failed")

        # Inject mock into sys.modules
        torch_backup = sys.modules.get("torch")
        sys.modules["torch"] = mock_torch

        try:
            registry = ModelRegistry()
            status = registry.check_pytorch_availability()

            assert status == ModelStatus.ERROR
        finally:
            # Restore original module
            if torch_backup is None:
                sys.modules.pop("torch", None)
            else:
                sys.modules["torch"] = torch_backup

    def test_check_transformers_availability_success(self) -> None:
        """Test Transformers availability check when available."""
        # Mock transformers module
        mock_transformers = MagicMock()
        mock_tokenizer = MagicMock()
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer

        # Inject mock into sys.modules
        transformers_backup = sys.modules.get("transformers")
        sys.modules["transformers"] = mock_transformers

        try:
            registry = ModelRegistry()
            status = registry.check_transformers_availability()

            assert status == ModelStatus.AVAILABLE
            mock_transformers.AutoTokenizer.from_pretrained.assert_called_once()
        finally:
            # Restore original module
            if transformers_backup is None:
                sys.modules.pop("transformers", None)
            else:
                sys.modules["transformers"] = transformers_backup

    def test_check_transformers_availability_not_installed(self) -> None:
        """Test Transformers availability check when not installed."""
        # Use patch.object to mock the built-in import at the module level
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "transformers":
                raise ImportError("transformers not found")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            registry = ModelRegistry()
            status = registry.check_transformers_availability()
            assert status == ModelStatus.UNAVAILABLE

    @patch("iatb.ml.model_registry.importlib.import_module")
    def test_check_vader_availability_success(self, mock_import: MagicMock) -> None:
        """Test VADER availability check when available."""
        # Mock vaderSentiment module
        mock_vader = MagicMock()
        mock_analyzer = MagicMock()
        mock_analyzer.polarity_scores.return_value = {"compound": 0.5}
        mock_vader.SentimentIntensityAnalyzer.return_value = mock_analyzer
        mock_import.return_value = mock_vader

        registry = ModelRegistry()
        health = registry.check_vader_availability()

        assert health.status == ModelStatus.AVAILABLE
        assert health.model_name == "vader"
        assert health.dll_loaded is True

    @patch("iatb.ml.model_registry.importlib.import_module")
    def test_check_vader_availability_not_installed(self, mock_import: MagicMock) -> None:
        """Test VADER availability check when not installed."""
        mock_import.side_effect = ImportError("vaderSentiment not found")

        registry = ModelRegistry()
        health = registry.check_vader_availability()

        assert health.status == ModelStatus.UNAVAILABLE
        assert health.error_message is not None
        assert "not installed" in health.error_message

    @patch("iatb.ml.model_registry.importlib.import_module")
    def test_check_vader_availability_error(self, mock_import: MagicMock) -> None:
        """Test VADER availability check with error."""
        mock_vader = MagicMock()
        mock_vader.SentimentIntensityAnalyzer = None
        mock_import.return_value = mock_vader

        registry = ModelRegistry()
        health = registry.check_vader_availability()

        assert health.status == ModelStatus.ERROR
        assert health.error_message is not None

    @patch("iatb.ml.model_registry.importlib.import_module")
    def test_check_vader_availability_dll_error(self, mock_import: MagicMock) -> None:
        """Test VADER availability check with DLL error."""
        mock_import.side_effect = RuntimeError("DLL load failed: some.dll")

        registry = ModelRegistry()
        health = registry.check_vader_availability()

        assert health.status == ModelStatus.ERROR
        assert health.dll_loaded is False

    def test_check_aion_availability_success(self) -> None:
        """Test AION availability check when available."""
        with patch("iatb.sentiment.aion_analyzer.AionAnalyzer") as mock_aion_cls:
            # Mock AION analyzer
            mock_aion_analyzer = MagicMock()
            mock_aion_analyzer.analyze.return_value = MagicMock(source="aion")
            mock_aion_cls.return_value = mock_aion_analyzer

            registry = ModelRegistry()
            health = registry.check_aion_availability()

            assert health.status == ModelStatus.AVAILABLE
            assert health.model_name == "aion"

    def test_check_aion_availability_not_installed(self) -> None:
        """Test AION availability check when not installed."""
        with patch("builtins.__import__", side_effect=ImportError("AION not found")):
            registry = ModelRegistry()
            health = registry.check_aion_availability()
            assert health.status == ModelStatus.UNAVAILABLE

    @patch("iatb.ml.model_registry.ModelRegistry.check_vader_availability")
    @patch("iatb.ml.model_registry.ModelRegistry.check_transformers_availability")
    def test_check_finbert_availability_fallback_to_vader(
        self,
        mock_transformers_check: MagicMock,
        mock_vader_check: MagicMock,
    ) -> None:
        """Test FinBERT availability check with VADER fallback."""
        # Mock transformers as unavailable to trigger fallback
        mock_transformers_check.return_value = ModelStatus.UNAVAILABLE
        # Mock VADER as available
        mock_vader_check.return_value = ModelHealth(
            model_name="vader",
            status=ModelStatus.AVAILABLE,
            last_check=datetime.now(UTC),
            dll_loaded=True,
            fallback_available=False,
        )

        registry = ModelRegistry()
        health = registry.check_finbert_availability()

        assert health.status == ModelStatus.UNAVAILABLE
        assert health.fallback_available is True

    def test_initialize_registry(self) -> None:
        """Test registry initialization."""
        registry = ModelRegistry()
        with patch.object(registry, "check_finbert_availability") as mock_finbert, patch.object(
            registry, "check_vader_availability"
        ) as mock_vader, patch.object(registry, "check_aion_availability") as mock_aion:
            mock_finbert.return_value = ModelHealth(
                model_name="finbert",
                status=ModelStatus.AVAILABLE,
                last_check=datetime.now(UTC),
            )
            mock_vader.return_value = ModelHealth(
                model_name="vader",
                status=ModelStatus.AVAILABLE,
                last_check=datetime.now(UTC),
            )
            mock_aion.return_value = ModelHealth(
                model_name="aion",
                status=ModelStatus.AVAILABLE,
                last_check=datetime.now(UTC),
            )

            status = registry.initialize()

            assert isinstance(status, RegistryStatus)
            assert status.total_models == 3
            assert status.available_models == 3
            assert registry._initialized is True

    def test_get_status(self) -> None:
        """Test getting registry status."""
        registry = ModelRegistry()
        with patch.object(registry, "check_finbert_availability") as mock_finbert, patch.object(
            registry, "check_vader_availability"
        ) as mock_vader, patch.object(registry, "check_aion_availability") as mock_aion:
            mock_finbert.return_value = ModelHealth(
                model_name="finbert",
                status=ModelStatus.AVAILABLE,
                last_check=datetime.now(UTC),
            )
            mock_vader.return_value = ModelHealth(
                model_name="vader",
                status=ModelStatus.ERROR,
                last_check=datetime.now(UTC),
                error_message="Test error",
            )
            mock_aion.return_value = ModelHealth(
                model_name="aion",
                status=ModelStatus.DEGRADED,
                last_check=datetime.now(UTC),
            )

            status = registry.get_status()

            assert status.total_models == 3
            assert status.available_models == 1
            assert status.degraded_models == 1
            assert status.unavailable_models == 1
            assert "finbert" in status.model_health
            assert "vader" in status.model_health
            assert "aion" in status.model_health

    def test_is_model_available(self) -> None:
        """Test checking if a specific model is available."""
        registry = ModelRegistry()
        with patch.object(registry, "check_vader_availability") as mock_vader, patch.object(
            registry, "check_finbert_availability"
        ) as mock_finbert, patch.object(registry, "check_aion_availability") as mock_aion:
            mock_vader.return_value = ModelHealth(
                model_name="vader",
                status=ModelStatus.AVAILABLE,
                last_check=datetime.now(UTC),
            )
            mock_finbert.return_value = ModelHealth(
                model_name="finbert",
                status=ModelStatus.ERROR,
                last_check=datetime.now(UTC),
                error_message="Test error",
            )
            mock_aion.return_value = ModelHealth(
                model_name="aion",
                status=ModelStatus.ERROR,
                last_check=datetime.now(UTC),
                error_message="Test error",
            )

            registry.initialize()

            assert registry.is_model_available("vader") is True
            assert registry.is_model_available("finbert") is False

    def test_get_fallback_chain(self) -> None:
        """Test getting fallback chain for models."""
        registry = ModelRegistry()

        finbert_fallback = registry.get_fallback_chain("finbert")
        assert finbert_fallback == ["vader"]

        aion_fallback = registry.get_fallback_chain("aion")
        assert aion_fallback == ["vader"]

        vader_fallback = registry.get_fallback_chain("vader")
        assert vader_fallback == []

        unknown_fallback = registry.get_fallback_chain("unknown")
        assert unknown_fallback == []


class TestGetRegistry:
    """Test get_registry function."""

    def test_get_registry_singleton(self) -> None:
        """Test that get_registry returns singleton instance."""
        registry1 = get_registry()
        registry2 = get_registry()

        assert registry1 is registry2

    def test_get_registry_creates_instance(self) -> None:
        """Test that get_registry creates instance on first call."""
        # Clear the global registry
        import iatb.ml.model_registry as model_registry_module

        model_registry_module._registry = None

        registry = get_registry()

        assert isinstance(registry, ModelRegistry)
        assert registry is get_registry()
