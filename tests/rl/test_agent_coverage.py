"""
Comprehensive coverage tests for agent.py.

Tests RL agent predict/train, SB3 wrapper, and model lifecycle.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.exceptions import ConfigError
from iatb.rl.agent import (
    RLAgent,
    RLAgentConfig,
    _extract_action_confidence,
    _load_algorithm_class,
    _normalize_action,
    _require_model,
    _validate_algorithm,
    _versioned_model_path,
)


class TestValidateAlgorithm:
    """Test algorithm validation."""

    def test_valid_algorithm(self):
        """Test valid algorithm."""
        _validate_algorithm("PPO")  # Should not raise

    def test_invalid_algorithm_raises_error(self):
        """Test that invalid algorithm raises ConfigError."""
        with pytest.raises(ConfigError, match="unsupported RL algorithm"):
            _validate_algorithm("INVALID")


class TestLoadAlgorithmClass:
    """Test algorithm class loading."""

    def test_load_algorithm_success(self):
        """Test successful algorithm loading."""
        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_algorithm_cls = MagicMock()
            mock_module.PPO = mock_algorithm_cls
            mock_import.return_value = mock_module

            result = _load_algorithm_class("PPO")

            assert result == mock_algorithm_cls
            mock_import.assert_called_once_with("stable_baselines3")

    def test_load_algorithm_module_not_found_raises_error(self):
        """Test that missing module raises ConfigError."""
        with patch("importlib.import_module") as mock_import:
            mock_import.side_effect = ModuleNotFoundError("stable_baselines3 not found")

            with pytest.raises(
                ConfigError, match="stable-baselines3 dependency is required"
            ):
                _load_algorithm_class("PPO")

    def test_load_algorithm_class_not_found_raises_error(self):
        """Test that missing algorithm class raises ConfigError."""
        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.PPO = None
            mock_import.return_value = mock_module

            with pytest.raises(
                ConfigError, match="stable_baselines3.PPO is unavailable"
            ):
                _load_algorithm_class("PPO")


class TestRequireModel:
    """Test model requirement check."""

    def test_require_model_with_model(self):
        """Test that model is returned when available."""
        model = MagicMock()
        result = _require_model(model)
        assert result == model

    def test_require_model_without_model_raises_error(self):
        """Test that missing model raises ConfigError."""
        with pytest.raises(ConfigError, match="model is not initialized"):
            _require_model(None)


class TestNormalizeAction:
    """Test action normalization."""

    def test_normalize_int_action(self):
        """Test normalizing int action."""
        result = _normalize_action(1)
        assert result == 1

    def test_normalize_list_action(self):
        """Test normalizing list action."""
        result = _normalize_action([2])
        assert result == 2

    def test_normalize_tuple_action(self):
        """Test normalizing tuple action."""
        result = _normalize_action((0,))
        assert result == 0

    def test_normalize_action_with_item_method(self):
        """Test normalizing action with item() method."""
        mock_action = MagicMock()
        mock_action.item.return_value = 1
        result = _normalize_action(mock_action)
        assert result == 1

    def test_normalize_unsupported_action_raises_error(self):
        """Test that unsupported action raises ConfigError."""
        with pytest.raises(
            ConfigError, match="predict.*returned unsupported action type"
        ):
            _normalize_action("invalid")


class TestVersionedModelPath:
    """Test versioned model path generation."""

    def test_versioned_path_generation(self):
        """Test versioned path generation."""
        timestamp = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
        path = _versioned_model_path("/models", "PPO", "abc123def456", timestamp)

        assert "ppo_" in path.as_posix()
        assert "abc123def456" in path.as_posix()
        assert "20260115T103000Z" in path.as_posix()

    def test_versioned_path_invalid_tz_raises_error(self):
        """Test that invalid timezone raises ConfigError."""
        timestamp = datetime(2026, 1, 15, 10, 30, 0)  # No timezone

        with pytest.raises(
            ConfigError, match="timestamp_utc must be timezone-aware UTC datetime"
        ):
            _versioned_model_path("/models", "PPO", "abc123", timestamp)

    def test_versioned_path_empty_hash_raises_error(self):
        """Test that empty hash raises ConfigError."""
        timestamp = datetime.now(UTC)

        with pytest.raises(ConfigError, match="git_hash cannot be empty"):
            _versioned_model_path("/models", "PPO", "", timestamp)


class TestExtractActionConfidence:
    """Test action confidence extraction."""

    def test_extract_confidence_success(self):
        """Test successful confidence extraction with default fallback."""
        mock_model = MagicMock()
        mock_model.policy = None  # Explicitly set to None to use default
        obs_float = [1.0, 2.0, 3.0]
        action = 1

        confidence = _extract_action_confidence(mock_model, obs_float, action)

        assert confidence == Decimal("0.5")  # Default when no policy

    def test_extract_confidence_no_policy_returns_default(self):
        """Test that missing policy returns default confidence."""
        mock_model = MagicMock()
        mock_model.policy = None
        obs_float = [1.0, 2.0, 3.0]
        action = 1

        confidence = _extract_action_confidence(mock_model, obs_float, action)

        assert confidence == Decimal("0.5")

    def test_extract_confidence_no_get_distribution_returns_default(self):
        """Test that missing get_distribution returns default confidence."""
        mock_model = MagicMock()
        mock_model.policy = MagicMock()
        mock_model.policy.get_distribution = None
        obs_float = [1.0, 2.0, 3.0]
        action = 1

        confidence = _extract_action_confidence(mock_model, obs_float, action)

        assert confidence == Decimal("0.5")


class TestRLAgentConfig:
    """Test agent configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RLAgentConfig()
        assert config.algorithm == "PPO"
        assert config.timesteps == 10_000
        assert config.seed == 42

    def test_custom_config(self):
        """Test custom configuration."""
        config = RLAgentConfig(algorithm="A2C", timesteps=5_000, seed=123)
        assert config.algorithm == "A2C"
        assert config.timesteps == 5_000
        assert config.seed == 123


class TestRLAgent:
    """Test RL agent functionality."""

    def test_agent_initialization(self):
        """Test agent initialization."""
        config = RLAgentConfig()
        agent = RLAgent(config)

        assert agent._config == config
        assert agent._model is None

    def test_agent_invalid_algorithm_raises_error(self):
        """Test that invalid algorithm raises ConfigError."""
        with pytest.raises(ConfigError, match="unsupported RL algorithm"):
            RLAgent(RLAgentConfig(algorithm="INVALID"))

    def test_has_model_property(self):
        """Test has_model property."""
        agent = RLAgent()
        assert agent.has_model is False

    def test_train_with_mock_environment(self):
        """Test training with mock environment."""
        agent = RLAgent()
        mock_env = MagicMock()

        mock_model = MagicMock()
        mock_model.learn = MagicMock()

        with patch("iatb.rl.agent._load_algorithm_class") as mock_load:
            mock_load.return_value = MagicMock(return_value=mock_model)

            agent.train(mock_env)

            assert agent._model == mock_model
            mock_model.learn.assert_called_once_with(total_timesteps=10_000)

    def test_train_no_learn_method_raises_error(self):
        """Test that missing learn method raises ConfigError."""
        agent = RLAgent()
        mock_env = MagicMock()

        mock_model = MagicMock()
        mock_model.learn = None

        with patch("iatb.rl.agent._load_algorithm_class") as mock_load:
            mock_load.return_value = MagicMock(return_value=mock_model)

            with pytest.raises(
                ConfigError, match="loaded SB3 model does not provide learn"
            ):
                agent.train(mock_env)

    def test_predict_without_training_raises_error(self):
        """Test that predict without training raises ConfigError."""
        agent = RLAgent()

        with pytest.raises(ConfigError, match="model is not initialized"):
            agent.predict([Decimal("1.0"), Decimal("2.0")])

    def test_predict_after_training(self):
        """Test predict after training."""
        agent = RLAgent()
        mock_env = MagicMock()

        mock_model = MagicMock()
        mock_model.learn = MagicMock()
        mock_model.predict = MagicMock(return_value=(1, None))

        with patch("iatb.rl.agent._load_algorithm_class") as mock_load:
            mock_load.return_value = MagicMock(return_value=mock_model)

            agent.train(mock_env)

            action = agent.predict([Decimal("1.0"), Decimal("2.0")])

            assert action == 1
            mock_model.predict.assert_called_once()

    def test_predict_no_predict_method_raises_error(self):
        """Test that missing predict method raises ConfigError."""
        agent = RLAgent()
        mock_env = MagicMock()

        mock_model = MagicMock()
        mock_model.learn = MagicMock()
        mock_model.predict = None

        with patch("iatb.rl.agent._load_algorithm_class") as mock_load:
            mock_load.return_value = MagicMock(return_value=mock_model)

            agent.train(mock_env)

            with pytest.raises(
                ConfigError, match="loaded SB3 model does not provide predict"
            ):
                agent.predict([Decimal("1.0"), Decimal("2.0")])

    def test_predict_with_confidence(self):
        """Test predict with confidence - simplified version using default fallback."""
        agent = RLAgent()
        mock_env = MagicMock()

        mock_model = MagicMock()
        mock_model.learn = MagicMock()
        mock_model.predict = MagicMock(return_value=(1, None))
        # Explicitly set policy to None to use default 0.5 confidence
        mock_model.policy = None

        with patch("iatb.rl.agent._load_algorithm_class") as mock_load:
            mock_load.return_value = MagicMock(return_value=mock_model)

            agent.train(mock_env)

            action, confidence = agent.predict_with_confidence(
                [Decimal("1.0"), Decimal("2.0")]
            )

            assert action == 1
            assert confidence == Decimal("0.5")  # Default fallback

    def test_save_model(self, tmp_path):
        """Test saving model."""
        agent = RLAgent()
        mock_env = MagicMock()

        mock_model = MagicMock()
        mock_model.learn = MagicMock()
        mock_model.save = MagicMock()

        with patch("iatb.rl.agent._load_algorithm_class") as mock_load:
            mock_load.return_value = MagicMock(return_value=mock_model)

            agent.train(mock_env)

            timestamp = datetime.now(UTC)
            path = agent.save(str(tmp_path), "abc123def456", timestamp)

            assert path is not None
            mock_model.save.assert_called_once()

    def test_save_model_without_training_raises_error(self):
        """Test that saving without training raises ConfigError."""
        agent = RLAgent()

        with pytest.raises(ConfigError, match="model is not initialized"):
            agent.save("/models", "abc123", datetime.now(UTC))

    def test_save_no_save_method_raises_error(self):
        """Test that missing save method raises ConfigError."""
        agent = RLAgent()
        mock_env = MagicMock()

        mock_model = MagicMock()
        mock_model.learn = MagicMock()
        mock_model.save = None

        with patch("iatb.rl.agent._load_algorithm_class") as mock_load:
            mock_load.return_value = MagicMock(return_value=mock_model)

            agent.train(mock_env)

            with pytest.raises(
                ConfigError, match="loaded SB3 model does not provide save"
            ):
                agent.save("/models", "abc123", datetime.now(UTC))

    def test_load_model(self):
        """Test loading model."""
        agent = RLAgent()

        mock_algorithm_cls = MagicMock()
        mock_model = MagicMock()
        mock_algorithm_cls.load = MagicMock(return_value=mock_model)

        with patch("iatb.rl.agent._load_algorithm_class") as mock_load:
            mock_load.return_value = mock_algorithm_cls

            agent.load("/models/ppo_model.zip")

            assert agent._model == mock_model
            mock_algorithm_cls.load.assert_called_once_with("/models/ppo_model.zip")

    def test_load_no_load_method_raises_error(self):
        """Test that missing load method raises ConfigError."""
        agent = RLAgent()

        mock_algorithm_cls = MagicMock()
        mock_algorithm_cls.load = None

        with patch("iatb.rl.agent._load_algorithm_class") as mock_load:
            mock_load.return_value = mock_algorithm_cls

            with pytest.raises(
                ConfigError, match="selected SB3 algorithm does not provide load"
            ):
                agent.load("/models/ppo_model.zip")