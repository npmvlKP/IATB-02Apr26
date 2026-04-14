"""
ML Model Registry for tracking model availability and health.

This module provides a centralized registry for ML models, enabling:
- Model health checks and availability tracking
- Graceful degradation when models fail to load
- Runtime model status querying
- Windows DLL issue detection and handling
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

_LOGGER = logging.getLogger(__name__)


class ModelStatus(str, Enum):
    """Model availability status."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    ERROR = "error"


@dataclass(frozen=True)
class ModelHealth:
    """Health status of a single model."""

    model_name: str
    status: ModelStatus
    last_check: datetime
    error_message: str | None = None
    load_time_ms: Decimal | None = None
    dll_loaded: bool = True
    fallback_available: bool = False


@dataclass(frozen=True)
class RegistryStatus:
    """Overall registry status."""

    timestamp: datetime
    total_models: int
    available_models: int
    degraded_models: int
    unavailable_models: int
    model_health: dict[str, ModelHealth]


class ModelRegistry:
    """Registry for tracking ML model availability and health."""

    def __init__(self) -> None:
        self._health: dict[str, ModelHealth] = {}
        self._initialized = False

    def check_pytorch_availability(self) -> ModelStatus:
        """Check if PyTorch is available and functional.

        Returns:
            ModelStatus indicating PyTorch availability.
        """
        try:
            import torch

            _LOGGER.debug("PyTorch version: %s", torch.__version__)

            # Test basic tensor operation to verify DLL loading
            test_tensor = torch.tensor([1.0, 2.0, 3.0])
            result = test_tensor.sum().item()

            if abs(result - 6.0) > Decimal("0.01"):
                _LOGGER.error("PyTorch tensor operation returned unexpected result")
                return ModelStatus.ERROR

            return ModelStatus.AVAILABLE
        except ImportError as exc:
            _LOGGER.warning("PyTorch not installed: %s", exc)
            return ModelStatus.UNAVAILABLE
        except Exception as exc:
            _LOGGER.error("PyTorch check failed: %s", exc)
            return ModelStatus.ERROR

    def check_transformers_availability(self) -> ModelStatus:
        """Check if Transformers library is available and functional.

        Returns:
            ModelStatus indicating Transformers availability.
        """
        try:
            from transformers import AutoTokenizer

            # Test tokenizer loading
            tokenizer = AutoTokenizer.from_pretrained(  # type: ignore[no-untyped-call] # nosec B615
                "distilbert-base-uncased"
            )

            if tokenizer is None:
                _LOGGER.error("Transformers tokenizer loading failed")
                return ModelStatus.ERROR

            return ModelStatus.AVAILABLE
        except ImportError as exc:
            _LOGGER.warning("Transformers not installed: %s", exc)
            return ModelStatus.UNAVAILABLE
        except Exception as exc:
            _LOGGER.error("Transformers check failed: %s", exc)
            return ModelStatus.ERROR

    def _create_health_result(
        self,
        model_name: str,
        status: ModelStatus,
        error_message: str | None = None,
        load_time_ms: Decimal | None = None,
        dll_loaded: bool = True,
        fallback_available: bool = False,
    ) -> ModelHealth:
        """Create a ModelHealth object with current timestamp.

        Args:
            model_name: Name of the model.
            status: Model status.
            error_message: Optional error message.
            load_time_ms: Optional load time in milliseconds.
            dll_loaded: Whether DLLs loaded successfully.
            fallback_available: Whether fallback is available.

        Returns:
            ModelHealth object.
        """
        return ModelHealth(
            model_name=model_name,
            status=status,
            last_check=datetime.now(UTC),
            error_message=error_message,
            load_time_ms=load_time_ms,
            dll_loaded=dll_loaded,
            fallback_available=fallback_available,
        )

    def _load_and_test_finbert(self) -> tuple[bool, str | None, bool]:
        """Attempt to load and test FinBERT model.

        Returns:
            Tuple of (success, error_message, dll_loaded).
        """
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            model = AutoModelForSequenceClassification.from_pretrained(  # nosec B615
                "ProsusAI/finbert"
            )
            tokenizer = AutoTokenizer.from_pretrained(  # type: ignore[no-untyped-call] # nosec B615
                "ProsusAI/finbert"
            )

            if model is None or tokenizer is None:
                return False, "FinBERT model or tokenizer is None", True

            # Test inference
            test_input = tokenizer("Test", return_tensors="pt")
            _ = model(**test_input)
            _LOGGER.debug("FinBERT health check passed")
            return True, None, True

        except Exception as exc:
            error_msg = str(exc)
            dll_loaded = "DLL" not in error_msg.upper()
            return False, error_msg, dll_loaded

    def check_finbert_availability(self) -> ModelHealth:
        """Check FinBERT model availability and health.

        Returns:
            ModelHealth for FinBERT.
        """
        start_time = datetime.now(UTC)

        # Check if transformers is available
        transformers_status = self.check_transformers_availability()
        if transformers_status != ModelStatus.AVAILABLE:
            return self._create_health_result(
                model_name="finbert",
                status=ModelStatus.UNAVAILABLE,
                error_message="Transformers library unavailable",
                fallback_available=True,
            )

        # Try to load and test FinBERT
        success, error_msg, dll_loaded = self._load_and_test_finbert()

        if success:
            status = ModelStatus.AVAILABLE
            fallback_available = False
        else:
            status = ModelStatus.ERROR
            fallback_available = True
            _LOGGER.warning("FinBERT unavailable (will fallback to VADER): %s", error_msg)

        load_time = datetime.now(UTC) - start_time
        load_time_ms = Decimal(str(load_time.total_seconds() * 1000))

        return self._create_health_result(
            model_name="finbert",
            status=status,
            error_message=error_msg,
            load_time_ms=load_time_ms,
            dll_loaded=dll_loaded,
            fallback_available=fallback_available,
        )

    def check_vader_availability(self) -> ModelHealth:
        """Check VADER sentiment analyzer availability.

        Returns:
            ModelHealth for VADER.
        """
        start_time = datetime.now(UTC)
        error_message = None
        status = ModelStatus.AVAILABLE
        dll_loaded = True

        try:
            module = importlib.import_module("vaderSentiment.vaderSentiment")
            analyzer_cls = getattr(module, "SentimentIntensityAnalyzer", None)

            if not callable(analyzer_cls):
                status = ModelStatus.ERROR
                error_message = "SentimentIntensityAnalyzer not found"
            else:
                # Test analysis
                analyzer = analyzer_cls()
                result = analyzer.polarity_scores("Test")
                if not isinstance(result, dict):
                    status = ModelStatus.ERROR
                    error_message = "VADER returned unexpected type"

        except ImportError as exc:
            status = ModelStatus.UNAVAILABLE
            error_message = "vaderSentiment not installed"
            dll_loaded = True
            _LOGGER.warning("VADER unavailable: %s", exc)
        except Exception as exc:
            status = ModelStatus.ERROR
            error_message = str(exc)
            dll_loaded = "DLL" not in str(exc).upper()
            _LOGGER.error("VADER check failed: %s", exc)

        load_time = datetime.now(UTC) - start_time
        load_time_ms = Decimal(str(load_time.total_seconds() * 1000))

        return ModelHealth(
            model_name="vader",
            status=status,
            last_check=datetime.now(UTC),
            error_message=error_message,
            load_time_ms=load_time_ms,
            dll_loaded=dll_loaded,
            fallback_available=False,
        )

    def check_aion_availability(self) -> ModelHealth:
        """Check AION analyzer availability.

        Returns:
            ModelHealth for AION.
        """
        start_time = datetime.now(UTC)
        error_message = None
        status = ModelStatus.AVAILABLE
        dll_loaded = True

        try:
            from iatb.sentiment.aion_analyzer import AionAnalyzer

            analyzer = AionAnalyzer()
            result = analyzer.analyze("Test")

            if result.source != "aion":
                status = ModelStatus.ERROR
                error_message = "AION returned unexpected source"

        except ImportError as exc:
            status = ModelStatus.UNAVAILABLE
            error_message = "AION analyzer not available"
            dll_loaded = True
            _LOGGER.warning("AION unavailable: %s", exc)
        except Exception as exc:
            status = ModelStatus.ERROR
            error_message = str(exc)
            dll_loaded = "DLL" not in str(exc).upper()
            _LOGGER.error("AION check failed: %s", exc)

        load_time = datetime.now(UTC) - start_time
        load_time_ms = Decimal(str(load_time.total_seconds() * 1000))

        return ModelHealth(
            model_name="aion",
            status=status,
            last_check=datetime.now(UTC),
            error_message=error_message,
            load_time_ms=load_time_ms,
            dll_loaded=dll_loaded,
            fallback_available=False,
        )

    def initialize(self) -> RegistryStatus:
        """Initialize registry with all model health checks.

        Returns:
            RegistryStatus with all model health information.
        """
        _LOGGER.info("Initializing ML Model Registry...")

        # Check all models
        self._health["finbert"] = self.check_finbert_availability()
        self._health["vader"] = self.check_vader_availability()
        self._health["aion"] = self.check_aion_availability()

        self._initialized = True

        status = self.get_status()
        _LOGGER.info(
            "ML Registry initialized: %d available, %d degraded, %d unavailable",
            status.available_models,
            status.degraded_models,
            status.unavailable_models,
        )

        return status

    def get_status(self) -> RegistryStatus:
        """Get current registry status.

        Returns:
            RegistryStatus with summary and individual model health.
        """
        if not self._initialized:
            self.initialize()

        available = sum(1 for h in self._health.values() if h.status == ModelStatus.AVAILABLE)
        degraded = sum(1 for h in self._health.values() if h.status == ModelStatus.DEGRADED)
        unavailable = sum(
            1
            for h in self._health.values()
            if h.status in (ModelStatus.UNAVAILABLE, ModelStatus.ERROR)
        )

        return RegistryStatus(
            timestamp=datetime.now(UTC),
            total_models=len(self._health),
            available_models=available,
            degraded_models=degraded,
            unavailable_models=unavailable,
            model_health=self._health.copy(),
        )

    def is_model_available(self, model_name: str) -> bool:
        """Check if a specific model is available.

        Args:
            model_name: Name of the model to check.

        Returns:
            True if model is available, False otherwise.
        """
        if not self._initialized:
            self.initialize()

        health = self._health.get(model_name)
        return health is not None and health.status == ModelStatus.AVAILABLE

    def get_fallback_chain(self, primary_model: str) -> list[str]:
        """Get fallback chain for a given primary model.

        Args:
            primary_model: Name of the primary model.

        Returns:
            List of model names in fallback order.
        """
        fallback_chains = {
            "finbert": ["vader"],
            "aion": ["vader"],
            "vader": [],
        }
        return fallback_chains.get(primary_model, [])


# Global registry instance
_registry: ModelRegistry | None = None


def get_registry() -> ModelRegistry:
    """Get or create global ModelRegistry instance.

    Returns:
        Global ModelRegistry instance.
    """
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
