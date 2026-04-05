#!/usr/bin/env python
"""
Unified paper-trading deployment and dashboard runner.

This script integrates deployment status checks and dashboard visibility into a
single command:
    poetry run python scripts/deploy_paper_trade.py
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from iatb.core.enums import Exchange
from iatb.paper_trade.deployment_dashboard import (
    DeploymentReport,
    build_deployment_report,
    render_deployment_dashboard,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deploy paper trading with integrated dashboard and health checks."
    )
    parser.add_argument(
        "--instrument-dir",
        type=Path,
        default=Path("data/instruments"),
        help="Directory containing exchange instrument snapshots.",
    )
    parser.add_argument(
        "--refresh-seconds",
        type=int,
        default=15,
        help="Seconds between dashboard refreshes.",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=0,
        help="Maximum refresh cycles (0 means unlimited).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one cycle only and exit.",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Do not prompt for input; exit based on health status.",
    )
    return parser.parse_args()


def _clear_terminal() -> None:
    print("\033[2J\033[H", end="")


def _prompt_choice(prompt: str, allowed: set[str], default: str) -> str:
    raw_value = input(f"{prompt} ").strip().lower()
    if raw_value == "":
        return default
    if raw_value in allowed:
        return raw_value
    return default


def _resolve_exit_code(report: DeploymentReport) -> int:
    return 1 if report.has_blockers else 0


def _show_header(report: DeploymentReport) -> None:
    _clear_terminal()
    print(render_deployment_dashboard(report))
    print("")
    print("User Controls")
    print("  - If all checks are healthy, confirm to exit safely.")
    print("  - If checks fail, run auto-correction or retry.")


def _ensure_positive_refresh(value: int) -> int:
    if value > 0:
        return value
    return 15


def _apply_auto_corrections(
    env: dict[str, str], instrument_dir: Path, report: DeploymentReport
) -> tuple[dict[str, str], list[str]]:
    updated_env = dict(env)
    notes: list[str] = []
    _apply_profile_discovery(updated_env, notes)
    _apply_instrument_discovery(updated_env, instrument_dir, report, notes)
    if not notes:
        notes.append("No automatic correction candidates found; manual action required.")
    return updated_env, notes


def _apply_profile_discovery(env: dict[str, str], notes: list[str]) -> None:
    if env.get("ZERODHA_PROFILE_PATH", "").strip():
        return
    for candidate in _profile_candidates():
        if candidate.is_file():
            env["ZERODHA_PROFILE_PATH"] = candidate.as_posix()
            notes.append(f"Loaded Zerodha profile from {candidate.as_posix()}.")
            return


def _profile_candidates() -> tuple[Path, ...]:
    return (
        Path("zerodha_profile.json"),
        Path("data/zerodha_profile.json"),
        Path("config/zerodha_profile.json"),
    )


def _apply_instrument_discovery(
    env: dict[str, str], instrument_dir: Path, report: DeploymentReport, notes: list[str]
) -> None:
    for instrument in report.instruments:
        if instrument.is_healthy:
            continue
        _discover_exchange_snapshot(env, instrument.exchange, instrument_dir, notes)


def _discover_exchange_snapshot(
    env: dict[str, str], exchange: Exchange, instrument_dir: Path, notes: list[str]
) -> None:
    env_key = f"IATB_{exchange.value}_INSTRUMENT_FILE"
    if env.get(env_key, "").strip():
        return
    for candidate in _instrument_candidates(exchange, instrument_dir):
        if candidate.is_file():
            env[env_key] = candidate.as_posix()
            notes.append(f"Using fallback {exchange.value} snapshot at {candidate.as_posix()}.")
            return


def _instrument_candidates(exchange: Exchange, instrument_dir: Path) -> tuple[Path, ...]:
    exchange_name = exchange.value
    lower_name = exchange_name.lower()
    return (
        instrument_dir / f"{exchange_name}.json",
        instrument_dir / f"{exchange_name}.csv",
        instrument_dir / f"{lower_name}.json",
        instrument_dir / f"{lower_name}.csv",
        Path("cache/instruments") / f"{exchange_name}.json",
        Path("cache/instruments") / f"{exchange_name}.csv",
        Path("cache/instruments") / f"{lower_name}.json",
        Path("cache/instruments") / f"{lower_name}.csv",
    )


def _handle_blockers(
    env: dict[str, str], instrument_dir: Path, report: DeploymentReport, non_interactive: bool
) -> tuple[bool, dict[str, str]]:
    if non_interactive:
        return False, env
    print("")
    print("Blockers detected. Choose: [a]uto-correct, [r]etry, [e]xit")
    choice = _prompt_choice("Selection [a/r/e]:", {"a", "r", "e"}, "a")
    if choice == "e":
        return False, env
    if choice == "r":
        return True, env
    new_env, notes = _apply_auto_corrections(env, instrument_dir, report)
    for note in notes:
        print(f"  - {note}")
    return True, new_env


def _handle_healthy_status(report: DeploymentReport, non_interactive: bool) -> bool:
    if non_interactive:
        return False
    if report.deployment_mode == "LIVE_PAPER_TRADING":
        prompt = "All checks are healthy and paper trading is live. Exit now? [y/N]:"
    else:
        prompt = "Checks are healthy; deployment is in NSE-standby mode. Exit now? [y/N]:"
    choice = _prompt_choice(prompt, {"y", "n"}, "n")
    return choice == "n"


def _run_cycle(
    env: dict[str, str], instrument_dir: Path, non_interactive: bool
) -> tuple[bool, int, dict[str, str]]:
    report = build_deployment_report(datetime.now(UTC), env, instrument_dir)
    _show_header(report)
    if report.has_blockers:
        should_continue, updated_env = _handle_blockers(env, instrument_dir, report, non_interactive)
        return should_continue, _resolve_exit_code(report), updated_env
    should_continue = _handle_healthy_status(report, non_interactive)
    return should_continue, _resolve_exit_code(report), env


def main() -> int:
    args = _parse_args()
    refresh_seconds = _ensure_positive_refresh(args.refresh_seconds)
    env = dict(os.environ)
    max_cycles = args.max_cycles
    cycles = 0

    while True:
        should_continue, exit_code, env = _run_cycle(
            env, args.instrument_dir, args.non_interactive
        )
        cycles += 1
        if args.once or not should_continue:
            return exit_code
        if max_cycles > 0 and cycles >= max_cycles:
            return exit_code
        time.sleep(refresh_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
