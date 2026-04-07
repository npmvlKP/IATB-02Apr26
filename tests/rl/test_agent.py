from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from iatb.core.exceptions import ConfigError
from iatb.rl.agent import RLAgent, RLAgentConfig, _normalize_action, _versioned_model_path


class _FakeAlgorithm:
    def __init__(
        self,
        policy: str,
        environment: object,
        verbose: int,
        seed: int,
        tensorboard_log: str | None,
    ) -> None:
        self.policy = policy
        self.environment = environment
        self.verbose = verbose
        self.seed = seed
        self.tensorboard_log = tensorboard_log
        self.learn_steps = 0
        self.saved_path: str | None = None

    def learn(self, total_timesteps: int) -> None:
        self.learn_steps = total_timesteps

    def predict(self, observation: list[float], deterministic: bool = True) -> tuple[int, None]:
        _ = deterministic
        _ = observation
        return 1, None

    def save(self, path: str) -> None:
        self.saved_path = path

    @classmethod
    def load(cls, path: str) -> "_FakeAlgorithm":
        instance = cls("MlpPolicy", object(), verbose=0, seed=0, tensorboard_log=None)
        instance.saved_path = path
        return instance


def test_rl_agent_train_predict_save_and_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    fake_module = SimpleNamespace(PPO=_FakeAlgorithm, A2C=_FakeAlgorithm, SAC=_FakeAlgorithm)
    monkeypatch.setattr("iatb.rl.agent.importlib.import_module", lambda _: fake_module)
    agent = RLAgent(RLAgentConfig(algorithm="PPO", timesteps=123, seed=7))
    agent.train(environment=object())
    assert agent.has_model
    action = agent.predict([Decimal("1"), Decimal("2"), Decimal("3")], deterministic=True)
    assert action == 1
    saved_path = agent.save(
        model_dir=str(tmp_path),
        git_hash="abc123def4567890",
        timestamp_utc=datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
    )
    assert "ppo_abc123def456" in saved_path
    assert saved_path.endswith(".zip")
    new_agent = RLAgent(RLAgentConfig(algorithm="PPO"))
    new_agent.load(saved_path)
    assert new_agent.has_model


def test_rl_agent_validates_algorithm_and_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ConfigError, match="unsupported RL algorithm"):
        RLAgent(RLAgentConfig(algorithm="DQN"))
    monkeypatch.setattr(
        "iatb.rl.agent.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    agent = RLAgent(RLAgentConfig(algorithm="PPO"))
    with pytest.raises(ConfigError, match="stable-baselines3 dependency"):
        agent.train(environment=object())


def test_rl_agent_requires_model_for_predict_and_save() -> None:
    agent = RLAgent(RLAgentConfig(algorithm="PPO"))
    with pytest.raises(ConfigError, match="model is not initialized"):
        agent.predict([Decimal("1")])
    with pytest.raises(ConfigError, match="model is not initialized"):
        agent.save("models", git_hash="abc", timestamp_utc=datetime(2026, 1, 5, tzinfo=UTC))


def test_rl_agent_requires_predict_and_save_methods_when_model_is_set() -> None:
    class _NoPredict:
        pass

    class _NoSave:
        def predict(self, observation: list[float], deterministic: bool = True) -> tuple[int, None]:
            _ = observation
            _ = deterministic
            return 1, None

    agent = RLAgent(RLAgentConfig(algorithm="PPO"))
    agent._model = _NoPredict()
    with pytest.raises(ConfigError, match="does not provide predict"):
        agent.predict([Decimal("1")])
    agent._model = _NoSave()
    with pytest.raises(ConfigError, match="does not provide save"):
        agent.save("models", git_hash="abc", timestamp_utc=datetime(2026, 1, 5, tzinfo=UTC))


def test_rl_agent_handles_missing_sb3_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    class _NoLearn:
        def __init__(self, *args: object, **kwargs: object) -> None:  # noqa: ANN401
            _ = args
            _ = kwargs

    class _NoLoad:
        def __init__(self, *args: object, **kwargs: object) -> None:  # noqa: ANN401
            _ = args
            _ = kwargs

        def learn(self, total_timesteps: int) -> None:
            _ = total_timesteps

    monkeypatch.setattr(
        "iatb.rl.agent.importlib.import_module",
        lambda _: SimpleNamespace(PPO=_NoLearn, A2C=_NoLearn, SAC=_NoLearn),
    )
    with pytest.raises(ConfigError, match="does not provide learn"):
        RLAgent(RLAgentConfig(algorithm="PPO")).train(environment=object())

    monkeypatch.setattr(
        "iatb.rl.agent.importlib.import_module",
        lambda _: SimpleNamespace(PPO=_NoLoad, A2C=_NoLoad, SAC=_NoLoad),
    )
    with pytest.raises(ConfigError, match="does not provide load"):
        RLAgent(RLAgentConfig(algorithm="PPO")).load("model.zip")
    monkeypatch.setattr(
        "iatb.rl.agent.importlib.import_module",
        lambda _: SimpleNamespace(A2C=_NoLoad, SAC=_NoLoad),
    )
    with pytest.raises(ConfigError, match="is unavailable"):
        RLAgent(RLAgentConfig(algorithm="PPO")).train(environment=object())


def test_normalize_action_branches_and_versioned_path_guards() -> None:
    class _ItemValue:
        def item(self) -> int:
            return 2

    class _BadItemValue:
        def item(self) -> str:
            return "x"

    assert _normalize_action([1]) == 1
    assert _normalize_action((2,)) == 2
    assert _normalize_action(_ItemValue()) == 2
    with pytest.raises(ConfigError, match="unsupported action type"):
        _normalize_action(_BadItemValue())
    with pytest.raises(ConfigError, match="timezone-aware UTC"):
        _versioned_model_path("models", "ppo", "hash", datetime(2026, 1, 5))  # noqa: DTZ001
    with pytest.raises(ConfigError, match="git_hash cannot be empty"):
        _versioned_model_path("models", "ppo", "", datetime(2026, 1, 5, tzinfo=UTC))
