from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import torch
from iatb.execution.zerodha_token_manager import ZerodhaTokenManager, load_env_file

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_resolve_saved_access_token_reuses_same_day_value(tmp_path: Path) -> None:
    today = datetime.now(UTC).date()
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            (
                "ZERODHA_API_KEY=kite-key",
                "ZERODHA_API_SECRET=kite-secret",
                "ZERODHA_ACCESS_TOKEN=access-today",
                f"ZERODHA_ACCESS_TOKEN_DATE_UTC={today.isoformat()}",
            ),
        )
        + "\n",
        encoding="utf-8",
    )
    manager = ZerodhaTokenManager(
        env_path=env_path,
        env_values=load_env_file(env_path),
        today_utc=today,
    )
    assert manager.resolve_saved_access_token() == "access-today"


def test_resolve_saved_access_token_rejects_stale_date(tmp_path: Path) -> None:
    today = datetime.now(UTC).date()
    stale = today - timedelta(days=1)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            (
                "ZERODHA_API_KEY=kite-key",
                "ZERODHA_API_SECRET=kite-secret",
                "ZERODHA_ACCESS_TOKEN=access-stale",
                f"ZERODHA_ACCESS_TOKEN_DATE_UTC={stale.isoformat()}",
            ),
        )
        + "\n",
        encoding="utf-8",
    )
    manager = ZerodhaTokenManager(
        env_path=env_path,
        env_values=load_env_file(env_path),
        today_utc=today,
    )
    assert manager.resolve_saved_access_token() is None


def test_resolve_saved_request_token_reads_dotenv_store_for_example_file(tmp_path: Path) -> None:
    today = datetime.now(UTC).date()
    env_example_path = tmp_path / ".env.example"
    env_example_path.write_text(
        "ZERODHA_API_KEY=kite-key\nZERODHA_API_SECRET=kite-secret\n",
        encoding="utf-8",
    )
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "\n".join(
            (
                "ZERODHA_REQUEST_TOKEN=req-fresh",
                f"ZERODHA_REQUEST_TOKEN_DATE_UTC={today.isoformat()}",
            ),
        )
        + "\n",
        encoding="utf-8",
    )
    manager = ZerodhaTokenManager(
        env_path=env_example_path,
        env_values=load_env_file(env_example_path),
        today_utc=today,
    )
    assert manager.resolve_saved_request_token() == "req-fresh"


def test_resolve_saved_request_token_ignores_example_file_token_values(tmp_path: Path) -> None:
    today = datetime.now(UTC).date()
    env_example_path = tmp_path / ".env.example"
    env_example_path.write_text(
        "\n".join(
            (
                "ZERODHA_API_KEY=kite-key",
                "ZERODHA_API_SECRET=kite-secret",
                "ZERODHA_REQUEST_TOKEN=req-stale-example",
                f"ZERODHA_REQUEST_TOKEN_DATE_UTC={today.isoformat()}",
            ),
        )
        + "\n",
        encoding="utf-8",
    )
    manager = ZerodhaTokenManager(
        env_path=env_example_path,
        env_values=load_env_file(env_example_path),
        today_utc=today,
    )
    assert manager.resolve_saved_request_token() is None


def test_persist_session_tokens_writes_to_dotenv_when_env_file_is_example(tmp_path: Path) -> None:
    today = datetime.now(UTC).date()
    env_example_path = tmp_path / ".env.example"
    env_example_path.write_text(
        "ZERODHA_API_KEY=kite-key\nZERODHA_API_SECRET=kite-secret\n",
        encoding="utf-8",
    )
    manager = ZerodhaTokenManager(
        env_path=env_example_path,
        env_values=load_env_file(env_example_path),
        today_utc=today,
    )
    written_path = manager.persist_session_tokens(
        access_token="access-new",  # noqa: S106
        request_token="req-new",  # noqa: S106
    )
    assert written_path == tmp_path / ".env"
    persisted = written_path.read_text(encoding="utf-8")
    assert "ZERODHA_ACCESS_TOKEN=access-new" in persisted
    assert f"ZERODHA_ACCESS_TOKEN_DATE_UTC={today.isoformat()}" in persisted
    assert "ZERODHA_REQUEST_TOKEN=req-new" in persisted
    assert f"ZERODHA_REQUEST_TOKEN_DATE_UTC={today.isoformat()}" in persisted
    assert "BROKER_OAUTH_2FA_VERIFIED=true" in persisted
