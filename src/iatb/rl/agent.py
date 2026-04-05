"""
Stable-Baselines3 wrapper for PPO/A2C/SAC training workflows.
"""

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

from iatb.core.exceptions import ConfigError

_SUPPORTED_ALGOS = {"PPO", "A2C", "SAC"}


@dataclass(frozen=True)
class RLAgentConfig:
    algorithm: str = "PPO"
    policy: str = "MlpPolicy"
    timesteps: int = 10_000
    seed: int = 42
    verbose: int = 0
    tensorboard_log_dir: str | None = None


class RLAgent:
    """Thin wrapper around stable-baselines3 model lifecycle."""

    def __init__(self, config: RLAgentConfig | None = None) -> None:
        self._config = config or RLAgentConfig()
        _validate_algorithm(self._config.algorithm)
        self._model: object | None = None

    @property
    def has_model(self) -> bool:
        return self._model is not None

    def train(self, environment: object) -> None:
        model_cls = _load_algorithm_class(self._config.algorithm)
        self._model = model_cls(
            self._config.policy,
            environment,
            verbose=self._config.verbose,
            seed=self._config.seed,
            tensorboard_log=self._config.tensorboard_log_dir,
        )
        learn_method = getattr(self._model, "learn", None)
        if not callable(learn_method):
            msg = "loaded SB3 model does not provide learn()"
            raise ConfigError(msg)
        learn_method(total_timesteps=self._config.timesteps)

    def predict(self, observation: list[Decimal], deterministic: bool = True) -> int:
        model = _require_model(self._model)
        predict_method = getattr(model, "predict", None)
        if not callable(predict_method):
            msg = "loaded SB3 model does not provide predict()"
            raise ConfigError(msg)
        # API boundary: SB3 requires float-like numeric arrays.
        action, _state = predict_method(
            [float(value) for value in observation], deterministic=deterministic
        )
        return _normalize_action(action)

    def predict_with_confidence(
        self,
        observation: list[Decimal],
    ) -> tuple[int, Decimal]:
        """Predict action and extract policy confidence as Decimal."""
        model = _require_model(self._model)
        # API boundary: SB3 float arrays + policy distribution.
        obs_float = [float(value) for value in observation]
        action = self.predict(observation, deterministic=True)
        confidence = _extract_action_confidence(model, obs_float, action)
        return action, confidence

    def save(self, model_dir: str, git_hash: str, timestamp_utc: datetime) -> str:
        model = _require_model(self._model)
        save_method = getattr(model, "save", None)
        if not callable(save_method):
            msg = "loaded SB3 model does not provide save()"
            raise ConfigError(msg)
        target_path = _versioned_model_path(
            model_dir, self._config.algorithm, git_hash, timestamp_utc
        )
        save_method(target_path.as_posix())
        return target_path.as_posix()

    def load(self, model_path: str) -> None:
        model_cls = _load_algorithm_class(self._config.algorithm)
        load_method = getattr(model_cls, "load", None)
        if not callable(load_method):
            msg = "selected SB3 algorithm does not provide load()"
            raise ConfigError(msg)
        self._model = load_method(model_path)


def _extract_action_confidence(
    model: object,
    obs_float: list[float],
    action: int,
) -> Decimal:
    """Extract softmax probability for the chosen action."""
    try:
        import numpy as np  # noqa: I001  # float API boundary

        policy = getattr(model, "policy", None)
        if policy is None:
            return Decimal("0.5")
        get_dist = getattr(policy, "get_distribution", None)
        if not callable(get_dist):
            return Decimal("0.5")
        obs_tensor = getattr(policy, "obs_to_tensor", None)
        if not callable(obs_tensor):
            return Decimal("0.5")
        tensor_obs, _ = obs_tensor(np.array([obs_float]))
        dist = get_dist(tensor_obs)
        probs_attr = getattr(getattr(dist, "distribution", None), "probs", None)
        if probs_attr is None:
            return Decimal("0.5")
        # float required: torch tensor → float → Decimal
        prob = float(probs_attr[0][action].item())
        return max(Decimal("0"), min(Decimal("1"), Decimal(str(prob))))
    except (ImportError, IndexError, TypeError, AttributeError):
        return Decimal("0.5")


def _validate_algorithm(algorithm: str) -> None:
    if algorithm not in _SUPPORTED_ALGOS:
        msg = f"unsupported RL algorithm: {algorithm}"
        raise ConfigError(msg)


def _load_algorithm_class(algorithm: str) -> Callable[..., object]:
    try:
        module = importlib.import_module("stable_baselines3")
    except ModuleNotFoundError as exc:
        msg = "stable-baselines3 dependency is required for RLAgent"
        raise ConfigError(msg) from exc
    algorithm_cls = getattr(module, algorithm, None)
    if not callable(algorithm_cls):
        msg = f"stable_baselines3.{algorithm} is unavailable"
        raise ConfigError(msg)
    return cast(Callable[..., object], algorithm_cls)


def _require_model(model: object | None) -> object:
    if model is None:
        msg = "model is not initialized; call train() or load() first"
        raise ConfigError(msg)
    return model


def _normalize_action(action: object) -> int:
    if isinstance(action, int):
        return action
    if isinstance(action, list) and action:
        first = action[0]
        if isinstance(first, int):
            return first
    if isinstance(action, tuple) and action:
        first = action[0]
        if isinstance(first, int):
            return first
    item_method = getattr(action, "item", None)
    if callable(item_method):
        item_value = item_method()
        if isinstance(item_value, int):
            return item_value
    msg = "predict() returned unsupported action type"
    raise ConfigError(msg)


def _versioned_model_path(
    model_dir: str,
    algorithm: str,
    git_hash: str,
    timestamp_utc: datetime,
) -> Path:
    if timestamp_utc.tzinfo != UTC:
        msg = "timestamp_utc must be timezone-aware UTC datetime"
        raise ConfigError(msg)
    if not git_hash:
        msg = "git_hash cannot be empty"
        raise ConfigError(msg)
    directory = Path(model_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = timestamp_utc.strftime("%Y%m%dT%H%M%SZ")
    short_hash = git_hash[:12]
    return directory / f"{algorithm.lower()}_{short_hash}_{stamp}.zip"
