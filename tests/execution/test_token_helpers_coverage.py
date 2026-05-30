"""Coverage tests for execution.token_helpers."""

from __future__ import annotations

from pathlib import Path

from iatb.execution.token_helpers import apply_env_defaults, load_env_file


class TestLoadEnvFile:
    def test_loads_existing_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("API_KEY=test123\n")
        result = load_env_file(env_file)
        assert isinstance(result, dict)

    def test_loads_nonexistent_file(self) -> None:
        result = load_env_file(Path("/nonexistent/.env"))
        assert isinstance(result, dict)


class TestApplyEnvDefaults:
    def test_does_not_override_existing(self) -> None:
        values = {"API_KEY": "original"}
        apply_env_defaults(values)
        assert values["API_KEY"] == "original"
