"""Coverage tests for iatb.ml.model_registry - ModelRegistry and helpers."""

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
    def test_available_value(self) -> None:
        assert ModelStatus.AVAILABLE.value == "available"

    def test_unavailable_value(self) -> None:
        assert ModelStatus.UNAVAILABLE.value == "unavailable"

    def test_degraded_value(self) -> None:
        assert ModelStatus.DEGRADED.value == "degraded"

    def test_error_value(self) -> None:
        assert ModelStatus.ERROR.value == "error"


class TestModelHealth:
    def test_creation_with_defaults(self) -> None:
        health = ModelHealth(
            model_name="test",
            status=ModelStatus.AVAILABLE,
            last_check=datetime.now(UTC),
        )
        assert health.error_message is None
        assert health.dll_loaded is True
        assert health.fallback_available is False

    def test_creation_with_all_fields(self) -> None:
        health = ModelHealth(
            model_name="finbert",
            status=ModelStatus.ERROR,
            last_check=datetime.now(UTC),
            error_message="DLL missing",
            load_time_ms=Decimal("1500"),
            dll_loaded=False,
            fallback_available=True,
        )
        assert health.error_message == "DLL missing"
        assert health.dll_loaded is False


class TestRegistryStatus:
    def test_creation(self) -> None:
        status = RegistryStatus(
            timestamp=datetime.now(UTC),
            total_models=3,
            available_models=1,
            degraded_models=0,
            unavailable_models=2,
            model_health={},
        )
        assert status.total_models == 3


class TestModelRegistry:
    def test_init(self) -> None:
        registry = ModelRegistry()
        assert registry._initialized is False
        assert registry._health == {}

    def test_check_pytorch_availability_error(self) -> None:
        registry = ModelRegistry()
        with patch.dict("sys.modules", {"torch": None}):
            status = registry.check_pytorch_availability()
            assert status in (ModelStatus.UNAVAILABLE, ModelStatus.ERROR)

    def test_check_vader_availability_success(self) -> None:
        registry = ModelRegistry()
        mock_module = MagicMock()
        mock_analyzer = MagicMock()
        mock_analyzer.polarity_scores.return_value = {"compound": 0.5}
        mock_module.SentimentIntensityAnalyzer = MagicMock(
            return_value=mock_analyzer,
        )
        with patch(
            "iatb.ml.model_registry.importlib.import_module",
            return_value=mock_module,
        ):
            health = registry.check_vader_availability()
            assert health.model_name == "vader"
            assert health.status == ModelStatus.AVAILABLE

    def test_check_finbert_transformers_unavailable(self) -> None:
        registry = ModelRegistry()
        with patch.dict("sys.modules", {"transformers": None}):
            health = registry.check_finbert_availability()
            assert health.status == ModelStatus.UNAVAILABLE
            assert health.fallback_available is True

    def test_create_health_result(self) -> None:
        registry = ModelRegistry()
        health = registry._create_health_result(
            model_name="test",
            status=ModelStatus.AVAILABLE,
        )
        assert health.model_name == "test"
        assert health.status == ModelStatus.AVAILABLE

    def test_is_model_available_initialized(self) -> None:
        registry = ModelRegistry()
        registry._initialized = True
        registry._health = {
            "finbert": ModelHealth(
                model_name="finbert",
                status=ModelStatus.AVAILABLE,
                last_check=datetime.now(UTC),
            ),
        }
        assert registry.is_model_available("finbert") is True
        assert registry.is_model_available("nonexistent") is False

    def test_get_fallback_chain(self) -> None:
        registry = ModelRegistry()
        assert registry.get_fallback_chain("finbert") == ["vader"]
        assert registry.get_fallback_chain("vader") == []


class TestGetRegistry:
    def test_returns_existing(self) -> None:
        import iatb.ml.model_registry as mod

        existing = ModelRegistry()
        original = mod._registry
        mod._registry = existing
        try:
            assert get_registry() is existing
        finally:
            mod._registry = original
