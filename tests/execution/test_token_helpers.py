"""Comprehensive tests for token_helpers.py module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from iatb.execution.token_helpers import apply_env_defaults, load_env_file


class TestLoadEnvFile:
    def test_loads_valid_env_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=value1\nKEY2=value2\nKEY3=value3\n", encoding="utf-8")
        result = load_env_file(env_file)
        assert result == {"KEY1": "value1", "KEY2": "value2", "KEY3": "value3"}

    def test_nonexistent_file_returns_empty(self, tmp_path: Path) -> None:
        result = load_env_file(tmp_path / "nonexistent.env")
        assert result == {}

    def test_ignores_comment_lines(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# This is a comment\nKEY1=value1\n# Another comment\nKEY2=value2\n",
            encoding="utf-8",
        )
        result = load_env_file(env_file)
        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_ignores_empty_lines(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("\n\nKEY1=value1\n\n\n", encoding="utf-8")
        result = load_env_file(env_file)
        assert result == {"KEY1": "value1"}

    def test_ignores_lines_without_equals(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=value1\nINVALID_LINE\nKEY2=value2\n", encoding="utf-8")
        result = load_env_file(env_file)
        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_strips_quotes_from_values(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=\"value1\"\nKEY2='value2'\nKEY3=value3\n", encoding="utf-8")
        result = load_env_file(env_file)
        assert result == {"KEY1": "value1", "KEY2": "value2", "KEY3": "value3"}

    def test_strips_whitespace_from_keys_and_values(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("  KEY1  =  value1  \n  KEY2  =  value2  \n", encoding="utf-8")
        result = load_env_file(env_file)
        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_value_with_equals_sign(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=value=with=equals\n", encoding="utf-8")
        result = load_env_file(env_file)
        assert result == {"KEY1": "value=with=equals"}

    def test_empty_value(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=\n", encoding="utf-8")
        result = load_env_file(env_file)
        assert result == {"KEY1": ""}

    def test_handles_os_error_gracefully(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=value1\n", encoding="utf-8")
        with patch.object(Path, "read_text", side_effect=OSError("Permission denied")):
            result = load_env_file(env_file)
        assert result == {}

    def test_file_with_only_comments(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("# comment1\n# comment2\n", encoding="utf-8")
        result = load_env_file(env_file)
        assert result == {}

    def test_file_with_only_empty_lines(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("\n\n\n", encoding="utf-8")
        result = load_env_file(env_file)
        assert result == {}

    def test_unicode_values(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=café\nKEY2=日本語\n", encoding="utf-8")
        result = load_env_file(env_file)
        assert result == {"KEY1": "café", "KEY2": "日本語"}


class TestApplyEnvDefaults:
    def test_applies_values_to_environ(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TEST_KEY", raising=False)
        apply_env_defaults({"TEST_KEY": "test_value"})
        assert os.environ["TEST_KEY"] == "test_value"
        monkeypatch.delenv("TEST_KEY", raising=False)

    def test_does_not_override_existing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_KEY", "existing_value")
        apply_env_defaults({"TEST_KEY": "new_value"})
        assert os.environ["TEST_KEY"] == "existing_value"
        monkeypatch.delenv("TEST_KEY", raising=False)

    def test_skips_empty_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TEST_KEY", raising=False)
        apply_env_defaults({"TEST_KEY": ""})
        assert "TEST_KEY" not in os.environ

    def test_applies_multiple_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("KEY1", raising=False)
        monkeypatch.delenv("KEY2", raising=False)
        apply_env_defaults({"KEY1": "val1", "KEY2": "val2"})
        assert os.environ["KEY1"] == "val1"
        assert os.environ["KEY2"] == "val2"
        monkeypatch.delenv("KEY1", raising=False)
        monkeypatch.delenv("KEY2", raising=False)

    def test_empty_dict_does_nothing(self) -> None:
        original_environ = dict(os.environ)
        apply_env_defaults({})
        assert os.environ == original_environ

    def test_integration_load_and_apply(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("API_KEY=secret123\nAPI_HOST=localhost\n", encoding="utf-8")
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.delenv("API_HOST", raising=False)
        values = load_env_file(env_file)
        apply_env_defaults(values)
        assert os.environ["API_KEY"] == "secret123"
        assert os.environ["API_HOST"] == "localhost"
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.delenv("API_HOST", raising=False)
