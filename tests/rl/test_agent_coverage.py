"""Additional tests for rl/agent.py to improve coverage to 90%+."""

import random
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.rl.agent import RLAgent, RLAgentConfig, _extract_action_confidence, _load_algorithm_class

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class _MockSB3Model:
    def __init__(
        self, policy: str, environment: object, verbose: int, seed: int, tensorboard_log: str | None
    ) -> None:
        self.policy = policy
        self.environment = environment
        self.verbose = verbose
        self.seed = seed
        self.tensorboard_log = tensorboard_log
        self.learn_steps = 0

    def learn(self, total_timesteps: int) -> None:
        self.learn_steps = total_timesteps

    def predict(
        self, observation: list[float], deterministic: bool = True
    ) -> tuple[list[int], None]:
        _ = deterministic
        _ = observation
        return [1], None

    def save(self, path: str) -> None:
        self.saved_path = path

    @classmethod
    def load(cls, path: str) -> "_MockSB3Model":
        instance = cls("MlpPolicy", object(), verbose=0, seed=0, tensorboard_log=None)
        instance.saved_path = path
        return instance


def test_rl_agent_init_with_default_config():
    """Test initialization with default config."""
    agent = RLAgent()
    assert agent._config.algorithm == "PPO"
    assert agent._config.policy == "MlpPolicy"
    assert agent._config.timesteps == 10_000
    assert agent._config.seed == 42
    assert agent.has_model is False


def test_rl_agent_init_with_custom_config():
    """Test initialization with custom config."""
    config = RLAgentConfig(
        algorithm="A2C",
        policy="CnnPolicy",
        timesteps=5000,
        seed=123,
        verbose=1,
        tensorboard_log_dir="logs/",
    )
    agent = RLAgent(config)
    assert agent._config.algorithm == "A2C"
    assert agent._config.policy == "CnnPolicy"
    assert agent._config.timesteps == 5000
    assert agent._config.seed == 123
    assert agent._config.verbose == 1
    assert agent._config.tensorboard_log_dir == "logs/"


def test_rl_agent_train_creates_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that train creates a model and calls learn."""
    fake_module = type(
        "Module", (), {"PPO": _MockSB3Model, "A2C": _MockSB3Model, "SAC": _MockSB3Model}
    )()
    monkeypatch.setattr("iatb.rl.agent.importlib.import_module", lambda _: fake_module)

    agent = RLAgent(RLAgentConfig(algorithm="PPO", timesteps=1000))
    agent.train(environment=object())

    assert agent.has_model is True
    assert agent._model is not None
    assert agent._model.learn_steps == 1000


def test_rl_agent_train_calls_learn_with_timesteps(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that learn is called with correct timesteps."""
    fake_module = type(
        "Module", (), {"PPO": _MockSB3Model, "A2C": _MockSB3Model, "SAC": _MockSB3Model}
    )()
    monkeypatch.setattr("iatb.rl.agent.importlib.import_module", lambda _: fake_module)

    agent = RLAgent(RLAgentConfig(algorithm="A2C", timesteps=5000))
    agent.train(environment=object())

    assert agent._model.learn_steps == 5000


def test_rl_agent_predict_with_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test predict with trained model."""
    fake_module = type(
        "Module", (), {"PPO": _MockSB3Model, "A2C": _MockSB3Model, "SAC": _MockSB3Model}
    )()
    monkeypatch.setattr("iatb.rl.agent.importlib.import_module", lambda _: fake_module)

    agent = RLAgent(RLAgentConfig(algorithm="PPO"))
    agent.train(environment=object())

    observation = [Decimal("0.5"), Decimal("0.3"), Decimal("0.7")]
    action = agent.predict(observation, deterministic=True)

    assert action == 1


def test_rl_agent_predict_with_deterministic_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test predict with deterministic=False."""
    fake_module = type(
        "Module", (), {"PPO": _MockSB3Model, "A2C": _MockSB3Model, "SAC": _MockSB3Model}
    )()
    monkeypatch.setattr("iatb.rl.agent.importlib.import_module", lambda _: fake_module)

    agent = RLAgent(RLAgentConfig(algorithm="PPO"))
    agent.train(environment=object())

    observation = [Decimal("0.5"), Decimal("0.3"), Decimal("0.7")]
    action = agent.predict(observation, deterministic=False)

    assert action == 1


def test_rl_agent_predict_without_model_raises_error() -> None:
    """Test that predict without model raises error."""
    agent = RLAgent(RLAgentConfig(algorithm="PPO"))

    with pytest.raises(ConfigError, match="model is not initialized"):
        agent.predict([Decimal("0.5")])


def test_rl_agent_predict_with_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test predict_with_confidence method."""
    fake_module = type(
        "Module", (), {"PPO": _MockSB3Model, "A2C": _MockSB3Model, "SAC": _MockSB3Model}
    )()
    monkeypatch.setattr("iatb.rl.agent.importlib.import_module", lambda _: fake_module)

    agent = RLAgent(RLAgentConfig(algorithm="PPO"))
    agent.train(environment=object())

    observation = [Decimal("0.5"), Decimal("0.3"), Decimal("0.7")]
    action, confidence = agent.predict_with_confidence(observation)

    assert action == 1
    assert isinstance(confidence, Decimal)
    assert Decimal("0") <= confidence <= Decimal("1")


def test_rl_agent_save_creates_versioned_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    """Test that save creates versioned model path."""
    fake_module = type(
        "Module", (), {"PPO": _MockSB3Model, "A2C": _MockSB3Model, "SAC": _MockSB3Model}
    )()
    monkeypatch.setattr("iatb.rl.agent.importlib.import_module", lambda _: fake_module)

    agent = RLAgent(RLAgentConfig(algorithm="PPO"))
    agent.train(environment=object())

    timestamp = datetime(2026, 1, 5, 10, 30, 45, tzinfo=UTC)
    saved_path = agent.save(str(tmp_path), "abc123def4567890", timestamp)

    assert "ppo_abc123def456" in saved_path
    assert "20260105T103045Z" in saved_path
    assert saved_path.endswith(".zip")


def test_rl_agent_save_without_model_raises_error() -> None:
    """Test that save without model raises error."""
    agent = RLAgent(RLAgentConfig(algorithm="PPO"))

    with pytest.raises(ConfigError, match="model is not initialized"):
        agent.save("models", "abc123", datetime(2026, 1, 5, tzinfo=UTC))


def test_rl_agent_load_from_file(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    """Test loading model from file."""
    fake_module = type(
        "Module", (), {"PPO": _MockSB3Model, "A2C": _MockSB3Model, "SAC": _MockSB3Model}
    )()
    monkeypatch.setattr("iatb.rl.agent.importlib.import_module", lambda _: fake_module)

    # First create and save a model
    agent1 = RLAgent(RLAgentConfig(algorithm="PPO"))
    agent1.train(environment=object())
    saved_path = agent1.save(str(tmp_path), "abc123", datetime(2026, 1, 5, tzinfo=UTC))

    # Load the model
    agent2 = RLAgent(RLAgentConfig(algorithm="PPO"))
    agent2.load(saved_path)

    assert agent2.has_model is True


def test_rl_agent_load_without_algorithm_raises_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that load with unsupported algorithm raises error."""
    fake_module = type(
        "Module", (), {"PPO": _MockSB3Model, "A2C": _MockSB3Model, "SAC": _MockSB3Model}
    )()
    monkeypatch.setattr("iatb.rl.agent.importlib.import_module", lambda _: fake_module)

    agent = RLAgent(RLAgentConfig(algorithm="PPO"))
    # Try to load with an algorithm that doesn't exist in the mock module
    # We need to change the agent's config to use an unsupported algorithm
    agent._config = RLAgentConfig(algorithm="DQN")  # DQN is not in our mock module
    with pytest.raises(ConfigError, match="is unavailable"):
        agent.load("model.zip")


def test_extract_action_confidence_without_policy() -> None:
    """Test confidence extraction when model has no policy."""
    mock_model = type("Model", (), {})()

    confidence = _extract_action_confidence(mock_model, [0.5, 0.3, 0.7], 0)
    assert confidence == Decimal("0.5")


def test_extract_action_confidence_without_get_distribution() -> None:
    """Test confidence extraction when policy has no get_distribution."""
    mock_policy = type("Policy", (), {})()
    mock_model = type("Model", (), {"policy": mock_policy})()

    confidence = _extract_action_confidence(mock_model, [0.5, 0.3, 0.7], 0)
    assert confidence == Decimal("0.5")


def test_extract_action_confidence_without_obs_to_tensor() -> None:
    """Test confidence extraction when policy has no obs_to_tensor."""
    mock_policy = type("Policy", (), {"get_distribution": lambda self, obs: None})()
    mock_model = type("Model", (), {"policy": mock_policy})()

    confidence = _extract_action_confidence(mock_model, [0.5, 0.3, 0.7], 0)
    assert confidence == Decimal("0.5")


def test_extract_action_confidence_without_distribution_probs() -> None:
    """Test confidence extraction when distribution has no probs."""

    # Create a distribution without probs attribute
    class MockDist:
        pass

    class MockPolicy:
        def get_distribution(self, obs):
            return MockDist()

        def obs_to_tensor(self, obs):
            return (np.array([obs]), None)

    mock_policy = MockPolicy()
    mock_model = type("Model", (), {"policy": mock_policy})()

    confidence = _extract_action_confidence(mock_model, [0.5, 0.3, 0.7], 0)
    assert confidence == Decimal("0.5")


def test_extract_action_confidence_exception_handling() -> None:
    """Test that exceptions in confidence extraction return default."""
    mock_model = type("Model", (), {"policy": object()})()

    confidence = _extract_action_confidence(mock_model, [0.5, 0.3, 0.7], 0)
    assert confidence == Decimal("0.5")


def test_load_algorithm_class_unavailable_algorithm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test loading unavailable algorithm raises error."""
    fake_module = type("Module", (), {"PPO": _MockSB3Model, "A2C": _MockSB3Model})()  # No SAC
    monkeypatch.setattr("iatb.rl.agent.importlib.import_module", lambda _: fake_module)

    with pytest.raises(ConfigError, match="stable_baselines3.SAC is unavailable"):
        _load_algorithm_class("SAC")


def test_load_algorithm_class_module_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that missing stable-baselines3 raises error."""
    monkeypatch.setattr(
        "iatb.rl.agent.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError("stable_baselines3")),
    )

    with pytest.raises(ConfigError, match="stable-baselines3 dependency is required"):
        _load_algorithm_class("PPO")


def test_rl_agent_config_all_fields() -> None:
    """Test RLAgentConfig with all fields set."""
    config = RLAgentConfig(
        algorithm="SAC",
        policy="MlpPolicy",
        timesteps=20_000,
        seed=999,
        verbose=2,
        tensorboard_log_dir="custom_logs/",
    )

    assert config.algorithm == "SAC"
    assert config.policy == "MlpPolicy"
    assert config.timesteps == 20_000
    assert config.seed == 999
    assert config.verbose == 2
    assert config.tensorboard_log_dir == "custom_logs/"


def test_rl_agent_config_frozen() -> None:
    """Test that RLAgentConfig is frozen."""
    config = RLAgentConfig()

    with pytest.raises(FrozenInstanceError):  # type: ignore[arg-type]
        config.algorithm = "A2C"


def test_rl_agent_train_with_tensorboard_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test training with tensorboard logging enabled."""
    fake_module = type(
        "Module", (), {"PPO": _MockSB3Model, "A2C": _MockSB3Model, "SAC": _MockSB3Model}
    )()
    monkeypatch.setattr("iatb.rl.agent.importlib.import_module", lambda _: fake_module)

    agent = RLAgent(RLAgentConfig(algorithm="PPO", tensorboard_log_dir="logs/", verbose=1))
    agent.train(environment=object())

    assert agent.has_model is True
    assert agent._model.tensorboard_log == "logs/"
