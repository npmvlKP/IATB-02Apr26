"""Tests for rl/agent.py — RL agent predict/train."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
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
    def test_valid_algorithms(self) -> None:
        for algo in ("PPO", "A2C", "SAC"):
            _validate_algorithm(algo)

    def test_invalid_algorithm_raises(self) -> None:
        with pytest.raises(ConfigError, match="unsupported RL algorithm"):
            _validate_algorithm("DQN")


class TestRLAgentConfig:
    def test_defaults(self) -> None:
        cfg = RLAgentConfig()
        assert cfg.algorithm == "PPO"
        assert cfg.timesteps == 10_000
        assert cfg.seed == 42


class TestRLAgent:
    def test_init_default(self) -> None:
        agent = RLAgent()
        assert agent.has_model is False

    def test_init_invalid_algo_raises(self) -> None:
        with pytest.raises(ConfigError):
            RLAgent(RLAgentConfig(algorithm="INVALID"))

    def test_predict_without_model_raises(self) -> None:
        agent = RLAgent()
        with pytest.raises(ConfigError, match="model is not initialized"):
            agent.predict([Decimal("1")])

    def test_save_without_model_raises(self) -> None:
        agent = RLAgent()
        with pytest.raises(ConfigError, match="model is not initialized"):
            agent.save("/tmp", "abc123", datetime.now(UTC))

    def test_train_loads_and_fits(self) -> None:
        mock_model = MagicMock()
        mock_algo_cls = MagicMock(return_value=mock_model)
        with patch("iatb.rl.agent._load_algorithm_class", return_value=mock_algo_cls):
            agent = RLAgent()
            agent.train(MagicMock())
        assert agent.has_model is True

    def test_predict_with_model(self) -> None:
        mock_model = MagicMock()
        mock_model.predict.return_value = (1, None)
        agent = RLAgent()
        agent._model = mock_model
        action = agent.predict([Decimal("0.5")])
        assert action == 1

    def test_save_with_model(self, tmp_path: Path) -> None:
        mock_model = MagicMock()
        agent = RLAgent()
        agent._model = mock_model
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = agent.save(str(tmp_path), "abcdef123456", ts)
        mock_model.save.assert_called_once()
        assert "ppo_abcdef123456_20240101T120000Z.zip" in result

    def test_load_model(self) -> None:
        mock_algo_cls = MagicMock()
        mock_algo_cls.load.return_value = MagicMock()
        with patch("iatb.rl.agent._load_algorithm_class", return_value=mock_algo_cls):
            agent = RLAgent()
            agent.load("/some/path.zip")
        assert agent.has_model is True


class TestRequireModel:
    def test_with_model(self) -> None:
        model = MagicMock()
        assert _require_model(model) == model

    def test_without_model_raises(self) -> None:
        with pytest.raises(ConfigError, match="model is not initialized"):
            _require_model(None)


class TestNormalizeAction:
    def test_int_action(self) -> None:
        assert _normalize_action(1) == 1

    def test_list_action(self) -> None:
        assert _normalize_action([2]) == 2

    def test_tuple_action(self) -> None:
        assert _normalize_action((0,)) == 0

    def test_tensor_like_action(self) -> None:
        mock = MagicMock()
        mock.item.return_value = 1
        assert _normalize_action(mock) == 1

    def test_unsupported_action_raises(self) -> None:
        with pytest.raises(ConfigError, match="unsupported action type"):
            _normalize_action("bad")


class TestVersionedModelPath:
    def test_valid_path(self, tmp_path: Path) -> None:
        ts = datetime(2024, 6, 15, 10, 30, 0, tzinfo=UTC)
        result = _versioned_model_path(str(tmp_path), "PPO", "abc123def456", ts)
        assert result.name == "ppo_abc123def456_20240615T103000Z.zip"

    def test_non_utc_raises(self) -> None:
        with pytest.raises(ConfigError, match="timezone-aware UTC"):
            _versioned_model_path("/tmp", "PPO", "abc", datetime(2024, 1, 1))

    def test_empty_git_hash_raises(self) -> None:
        with pytest.raises(ConfigError, match="git_hash cannot be empty"):
            _versioned_model_path("/tmp", "PPO", "", datetime(2024, 1, 1, tzinfo=UTC))


class TestExtractActionConfidence:
    def test_no_policy_returns_default(self) -> None:
        model = MagicMock(spec=[])
        result = _extract_action_confidence(model, [0.5], 1)
        assert result == Decimal("0.5")

    def test_successful_extraction(self) -> None:
        model = MagicMock()
        obs_tensor = MagicMock(return_value=(MagicMock(), MagicMock()))
        model.policy.obs_to_tensor = obs_tensor
        mock_probs = MagicMock()
        mock_probs.__getitem__ = MagicMock(return_value=mock_probs)
        mock_probs.item.return_value = 0.8
        dist_inner = MagicMock()
        dist_inner.distribution.probs = mock_probs
        model.policy.get_distribution = MagicMock(return_value=dist_inner)
        result = _extract_action_confidence(model, [0.5], 1)
        assert isinstance(result, Decimal)


class TestLoadAlgorithmClass:
    def test_missing_sb3_raises(self) -> None:
        with patch(
            "importlib.import_module", side_effect=ModuleNotFoundError
        ), pytest.raises(ConfigError, match="stable-baselines3 dependency"):
            _load_algorithm_class("PPO")
