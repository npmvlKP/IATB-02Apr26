#!/usr/bin/env python
"""
IATB Local Development - Git Sync Script.

Sequential, interactive workflow to verify and push local changes
to the connected remote git repository.

Run from project root:
    poetry run python scripts/git_sync.py

Modes:
    --auto         Skip confirmations, push automatically (use after gates pass)
    --dry-run      Show what would happen without making changes
    --skip-gates   Skip quality gate checks (not recommended)
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PASS = 0
FAIL = 1
WARN = 2


def _run(cmd: list[str], timeout: int = 120) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return 1, "Command timed out"
    except FileNotFoundError:
        return 1, f"Command not found: {cmd[0]}"
    except Exception as exc:
        return 1, str(exc)


def _confirm(prompt: str) -> bool:
    try:
        return input(f"\n  {prompt} [y/N]: ").strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        return False


def _section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def _info(msg: str) -> None:
    print(f"  [INFO] {msg}")


def _warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def _step(n: int, total: int, desc: str) -> None:
    print(f"\n  --- Step {n}/{total}: {desc} ---")


def get_branch() -> str:
    rc, out = _run(["git", "branch", "--show-current"])
    return out.strip() if rc == 0 else "unknown"


def get_remote_url() -> str:
    rc, out = _run(["git", "remote", "get-url", "origin"])
    return out.strip() if rc == 0 else "unknown"


def get_commit_hash() -> str:
    rc, out = _run(["git", "rev-parse", "HEAD"])
    return out.strip()[:12] if rc == 0 else "unknown"


def get_changed_files() -> tuple[list[str], list[str], list[str]]:
    rc, out = _run(["git", "status", "--porcelain"])
    staged: list[str] = []
    modified: list[str] = []
    untracked: list[str] = []
    if rc != 0:
        return staged, modified, untracked
    for line in out.splitlines():
        if not line.strip():
            continue
        status = line[:2]
        path = line[3:].strip()
        if status.startswith("??"):
            untracked.append(path)
        elif status[0] != " ":
            staged.append(path)
        elif status[1] != " ":
            modified.append(path)
    return staged, modified, untracked


def check_remote_connectivity() -> bool:
    rc, _ = _run(["git", "ls-remote", "--heads", "origin"], timeout=30)
    if rc == 0:
        _ok("Remote 'origin' reachable")
        return True
    _fail("Cannot reach remote 'origin' - check network / SSH key")
    return False


def check_branch_tracking() -> bool:
    rc, out = _run(["git", "status", "-b", "--porcelain"])
    if rc != 0:
        return False
    if "## No commits yet" in out:
        _info("No commits yet - first push will set tracking")
        return True
    if "ahead" in out or "behind" in out:
        match = re.search(r"\[(.+)\]", out)
        if match:
            _info(f"Branch status: {match.group(1)}")
        return True
    _ok("Branch up to date with remote")
    return True


def run_quality_gates() -> bool:
    _section("QUALITY GATES (G1-G5)")
    gates = [
        ("G1 Lint", ["poetry", "run", "ruff", "check", "src/", "tests/"]),
        ("G2 Format", ["poetry", "run", "ruff", "format", "--check", "src/", "tests/"]),
        ("G3 Types", ["poetry", "run", "mypy", "src/", "--strict"]),
        ("G4 Security", ["poetry", "run", "bandit", "-r", "src/", "-q"]),
        ("G5 Secrets", ["gitleaks", "detect", "--source", ".", "--no-banner"]),
    ]
    all_ok = True
    for name, cmd in gates:
        rc, out = _run(cmd, timeout=120)
        if rc == 0:
            _ok(f"{name} passed")
        else:
            _fail(f"{name} FAILED")
            for line in out.splitlines()[:5]:
                print(f"        {line}")
            all_ok = False
    return all_ok


def run_tests() -> bool:
    _section("TEST SUITE (G6)")
    _info("Running: poetry run pytest --cov=src/iatb --cov-fail-under=90 -x -q")
    rc, out = _run(
        ["poetry", "run", "pytest", "--cov=src/iatb", "--cov-fail-under=90", "-x", "-q"],
        timeout=600,
    )
    if rc == 0:
        for line in out.splitlines():
            if "passed" in line.lower():
                _ok(line)
                break
        else:
            _ok("All tests passed")
        return True
    _fail("Tests failed")
    for line in out.splitlines()[-10:]:
        print(f"        {line}")
    return False


def auto_format() -> bool:
    _info("Running: poetry run ruff format src/ tests/")
    rc, _ = _run(["poetry", "run", "ruff", "format", "src/", "tests/"])
    if rc == 0:
        _ok("Auto-formatted with ruff")
        return True
    _warn("Ruff format had issues")
    return False


def suggest_commit_message() -> str:
    staged, modified, untracked = get_changed_files()
    all_files = staged + modified + untracked

    has_src = any(f.startswith("src/") for f in all_files)
    has_tests = any(f.startswith("tests/") for f in all_files)
    has_scripts = any(f.startswith("scripts/") for f in all_files)
    has_config = any(f.startswith("config/") for f in all_files)

    if has_scripts and has_src:
        scope = "scripts"
    elif has_tests and has_src:
        scope = "tests"
    elif has_config:
        scope = "config"
    elif has_src:
        scope = "core"
    else:
        scope = "chore"

    if "audit_logger" in str(all_files):
        desc = "add audit logger module for paper trading persistence"
    elif "paper_runtime" in str(all_files):
        desc = "fix paper runtime signal handling and imports"
    elif "streamlit_app" in str(all_files):
        desc = "fix streamlit dashboard imports and entry point"
    elif "dashboard" in str(all_files):
        desc = "fix dashboard script entry point"
    elif has_tests:
        desc = "add tests for paper trading components"
    else:
        desc = "update local development configuration"

    return f"{scope}: {desc}"


def do_dry_run() -> int:
    _section("DRY RUN - What would happen")
    branch = get_branch()
    remote = get_remote_url()
    commit = get_commit_hash()
    staged, modified, untracked = get_changed_files()

    _info(f"Branch      : {branch}")
    _info(f"Remote      : {remote}")
    _info(f"HEAD commit : {commit}")
    print()
    if staged:
        _info(f"Staged files ({len(staged)}):")
        for f in staged:
            print(f"        {f}")
    if modified:
        _info(f"Modified files ({len(modified)}):")
        for f in modified:
            print(f"        {f}")
    if untracked:
        _info(f"Untracked files ({len(untracked)}):")
        for f in untracked:
            print(f"        {f}")
    if not staged and not modified and not untracked:
        _warn("No changes detected - nothing to sync")
        return 0

    msg = suggest_commit_message()
    print()
    _info(f"Suggested commit: {msg}")
    _info(f"Push target: origin/{branch}")
    return 0


def do_sync(auto: bool = False) -> int:
    _section("IATB LOCAL DEVELOPMENT -> REMOTE GIT SYNC")
    _info(f"Project : {ROOT}")
    _info(f"Time    : {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    total_steps = 8 if not auto else 7
    step = 0

    # Step 1: Pre-flight
    step += 1
    _step(step, total_steps, "Pre-flight checks")
    branch = get_branch()
    remote = get_remote_url()
    commit = get_commit_hash()
    _info(f"Branch       : {branch}")
    _info(f"Remote       : {remote}")
    _info(f"Current HEAD : {commit}")

    if not auto and not _confirm("Proceed with these settings?"):
        return 130

    # Step 2: Check working tree
    step += 1
    _step(step, total_steps, "Check working tree state")
    staged, modified, untracked = get_changed_files()

    if not staged and not modified and not untracked:
        _warn("Working tree is clean - nothing to sync")
        return 0

    all_changes = staged + modified + untracked
    _info(f"Changes: {len(staged)} staged, {len(modified)} modified, {len(untracked)} untracked")
    for f in all_changes:
        print(f"        {f}")

    if not auto and not _confirm("Stage all changes for commit?"):
        return 130

    # Step 3: Auto-format
    step += 1
    _step(step, total_steps, "Auto-format code (ruff)")
    auto_format()

    # Step 4: Quality gates
    step += 1
    _step(step, total_steps, "Run quality gates (G1-G5)")
    gates_ok = run_quality_gates()
    if not gates_ok:
        if auto:
            _fail("Quality gates failed - aborting auto-sync")
            return 1
        if not _confirm("Some gates FAILED. Continue anyway?"):
            return 1

    # Step 5: Tests
    step += 1
    _step(step, total_steps, "Run test suite (G6)")
    tests_ok = run_tests()
    if not tests_ok:
        if auto:
            _fail("Tests failed - aborting auto-sync")
            return 1
        if not _confirm("Tests FAILED. Continue anyway?"):
            return 1

    # Step 6: Stage and commit
    step += 1
    _step(step, total_steps, "Stage and commit changes")
    rc, _ = _run(["git", "add", "-A"])
    if rc != 0:
        _fail("git add failed")
        return 1
    _ok("All changes staged")

    suggested_msg = suggest_commit_message()
    if auto:
        commit_msg = suggested_msg
    else:
        _info(f"Suggested message: {suggested_msg}")
        user_msg = input("\n  Enter commit message (Enter to use suggestion): ").strip()
        commit_msg = user_msg if user_msg else suggested_msg

    if not commit_msg:
        _fail("Empty commit message - aborting")
        return 1

    rc, out = _run(["git", "commit", "-m", commit_msg])
    if rc != 0:
        _fail(f"git commit failed: {out}")
        return 1
    new_commit = get_commit_hash()
    _ok(f"Committed: {new_commit} - {commit_msg}")

    # Step 7: Push
    step += 1
    _step(step, total_steps, "Push to remote")
    if not check_remote_connectivity():
        return 1

    push_target = f"origin/{branch}"
    _info(f"Pushing to: {push_target}")

    if not auto and not _confirm(f"Push to {push_target}?"):
        return 130

    rc, out = _run(["git", "push", "-u", "origin", branch])
    if rc != 0:
        _fail(f"git push failed: {out}")
        return 1
    _ok(f"Pushed to {push_target}")

    # Step 8: Verify
    step += 1
    _step(step, total_steps, "Post-push verification")
    check_branch_tracking()

    rc, out = _run(["git", "log", "-1", "--oneline"])
    if rc == 0:
        _ok(f"Latest commit: {out.strip()}")

    rc, out = _run(["git", "status", "--porcelain"])
    if rc == 0 and not out.strip():
        _ok("Working tree clean")
    else:
        _warn("Working tree has remaining changes")

    # Final summary
    _section("SYNC COMPLETE")
    _ok(f"Branch   : {branch}")
    _ok(f"Commit   : {new_commit}")
    _ok(f"Remote   : {push_target}")
    _ok(f"Message  : {commit_msg}")
    print()
    _info("Verify on GitHub: https://github.com/npmvlKP/IATB-02Apr26")
    return 0


def main() -> int:
    args = set(sys.argv[1:])
    if "--dry-run" in args:
        return do_dry_run()

    auto = "--auto" in args
    skip_gates = "--skip-gates" in args

    if skip_gates:
        _warn("--skip-gates: Skipping quality gate validation (not recommended)")
        return do_sync(auto=auto)

    return do_sync(auto=auto)


if __name__ == "__main__":
    sys.exit(main())
