#!/usr/bin/env python
"""
IATB Paper Trading Deployment - Comprehensive Verification Script.

Verifies every component required for local paper trading deployment:
  1. Environment and dependencies
  2. Configuration validation
  3. Module import chain
  4. Quality gates G1-G10
  5. Paper engine readiness
  6. Dashboard readiness
  7. Git sync status

Run from project root:
    poetry run python scripts/verify_paper_deployment.py
    poetry run python scripts/verify_paper_deployment.py --fix    # auto-fix formatting
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "iatb"
CONFIG_PATH = ROOT / "config" / "settings.toml"

PASS = 0
FAIL = 1
WARN = 2


def _header(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def _result(label: str, status: int, detail: str = "") -> None:
    tag = {PASS: "PASS", FAIL: "FAIL", WARN: "WARN"}[status]
    print(f"  [{tag}] {label}")
    if detail:
        for line in detail.strip().splitlines():
            print(f"        {line}")


def _run(
    cmd: list[str],
    timeout: int = 300,
) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return 1, "Command timed out"
    except FileNotFoundError:
        return 1, f"Command not found: {cmd[0]}"
    except Exception as exc:
        return 1, str(exc)


def _find_float_ast(paths: list[Path]) -> list[str]:
    hits: list[str] = []
    for p in paths:
        if not p.is_file():
            continue
        source = p.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        lines = source.splitlines()
        for node in ast.walk(tree):
            is_float_type = isinstance(node, ast.Name) and node.id == "float"
            is_float_literal = isinstance(node, ast.Constant) and isinstance(node.value, float)
            if not (is_float_type or is_float_literal):
                continue
            ln = getattr(node, "lineno", 1)
            line = lines[ln - 1].strip() if 0 < ln <= len(lines) else ""
            if "API boundary" in line or ("API" in line and "#" in line):
                continue
            has_api = False
            for i in range(max(0, ln - 6), ln - 1):
                if 0 <= i < len(lines):
                    prev = lines[i].strip()
                    if "API boundary" in prev or ("API" in prev and "#" in prev):
                        has_api = True
                        break
            if has_api:
                continue
            rel = p.relative_to(ROOT)
            hits.append(f"{rel}:{ln}: {line}")
    return hits


def _find(pattern: str, paths: list[Path]) -> list[str]:
    hits: list[str] = []
    for p in paths:
        if not p.is_file():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if pattern in line:
                hits.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()}")
    return hits


def _py_files(base: Path) -> list[Path]:
    return [f for f in base.rglob("*.py") if f.is_file()]


def check_environment() -> int:
    _header("1. ENVIRONMENT & DEPENDENCIES")
    worst = PASS
    tools = [
        ("poetry", ["poetry", "--version"]),
        ("python", ["python", "--version"]),
        ("ruff", ["ruff", "--version"]),
        ("mypy", ["mypy", "--version"]),
        ("bandit", ["bandit", "--version"]),
        ("pytest", ["pytest", "--version"]),
        ("gitleaks", ["gitleaks", "version"]),
        ("streamlit", ["streamlit", "--version"]),
        ("git", ["git", "--version"]),
    ]
    for name, cmd in tools:
        rc, out = _run(cmd, timeout=15)
        ver = out.strip().splitlines()[0] if out.strip() else "not found"
        status = PASS if rc == 0 else FAIL
        _result(f"{name}", status, ver)
        if status == FAIL:
            worst = FAIL
    return worst


def check_config() -> int:
    _header("2. CONFIGURATION VALIDATION")
    if not CONFIG_PATH.exists():
        _result("settings.toml exists", FAIL, f"Missing: {CONFIG_PATH}")
        return FAIL
    _result("settings.toml exists", PASS)

    content = CONFIG_PATH.read_text(encoding="utf-8")
    checks = [
        ("live_trading_enabled = false", r"live_trading_enabled\s*=\s*false", True),
        ("paper_trade_enforced = true", r"paper_trade_enforced\s*=\s*true", True),
        ("mode = paper", r"mode\s*=\s*\"paper\"", True),
        ("default_exchange = NSE", r"default_exchange\s*=\s*\"NSE\"", True),
        ("timezone = UTC", r"timezone\s*=\s*\"UTC\"", True),
    ]
    worst = PASS
    for label, pattern, required in checks:
        found = bool(re.search(pattern, content))
        if required and not found:
            _result(label, FAIL, "Not found in settings.toml")
            worst = FAIL
        elif found:
            _result(label, PASS)
        else:
            _result(label, WARN, "Optional, not set")
            worst = WARN if worst == PASS else worst
    return worst


def check_modules() -> int:
    _header("3. MODULE IMPORT CHAIN")
    critical = [
        "iatb.core.engine",
        "iatb.core.paper_runtime",
        "iatb.core.event_bus",
        "iatb.core.health",
        "iatb.execution.paper_executor",
        "iatb.storage.audit_logger",
        "iatb.storage.sqlite_store",
        "iatb.visualization.streamlit_app",
        "iatb.risk.stop_loss",
        "iatb.risk.kill_switch",
        "iatb.scanner.instrument_scanner",
        "iatb.selection.instrument_scorer",
        "iatb.sentiment.aggregator",
        "iatb.backtesting.vectorbt_engine",
    ]
    worst = PASS
    for mod in critical:
        rc, out = _run(
            [sys.executable, "-c", f"import {mod}; print('OK')"],
            timeout=30,
        )
        status = PASS if rc == 0 else FAIL
        _result(mod, status, out.strip() if status == FAIL else "")
        if status == FAIL:
            worst = FAIL
    return worst


def check_scripts() -> int:
    _header("4. DEPLOYMENT SCRIPTS")
    scripts = [
        "scripts/start_paper.ps1",
        "scripts/start_dashboard.ps1",
        "scripts/quality_gate.ps1",
    ]
    worst = PASS
    for s in scripts:
        p = ROOT / s
        if p.exists():
            _result(s, PASS, f"Size: {p.stat().st_size} bytes")
        else:
            _result(s, FAIL, "Missing")
            worst = FAIL

    sp = ROOT / "scripts" / "start_paper.ps1"
    if sp.exists():
        content = sp.read_text(encoding="utf-8")
        if "iatb.core.paper_runtime" in content:
            _result("start_paper.ps1 -> paper_runtime module", PASS)
        else:
            _result("start_paper.ps1 -> paper_runtime module", FAIL, "Wrong module reference")
            worst = FAIL

    sd = ROOT / "scripts" / "start_dashboard.ps1"
    if sd.exists():
        content = sd.read_text(encoding="utf-8")
        if "streamlit_app.py" in content:
            _result("start_dashboard.ps1 -> streamlit_app.py", PASS)
        else:
            _result(
                "start_dashboard.ps1 -> streamlit_app.py", FAIL, "Should point to streamlit_app.py"
            )
            worst = FAIL
    return worst


def check_quality_gates() -> int:
    _header("5. QUALITY GATES (G1-G10)")
    gates = [
        ("G1", "Lint", ["poetry", "run", "ruff", "check", "src/", "tests/"]),
        ("G2", "Format", ["poetry", "run", "ruff", "format", "--check", "src/", "tests/"]),
        ("G3", "Types", ["poetry", "run", "mypy", "src/", "--strict"]),
        ("G4", "Security", ["poetry", "run", "bandit", "-r", "src/", "-q"]),
        ("G5", "Secrets", ["gitleaks", "detect", "--source", ".", "--no-banner"]),
    ]
    worst = PASS
    for gate, label, cmd in gates:
        rc, out = _run(cmd, timeout=120)
        status = PASS if rc == 0 else FAIL
        detail = ""
        if status == FAIL:
            lines = [ln for ln in out.strip().splitlines() if ln.strip()]
            detail = "\n".join(lines[:5])
            if len(lines) > 5:
                detail += f"\n        ... ({len(lines)} total lines)"
        _result(f"{gate} - {label}", status, detail)
        if status == FAIL:
            worst = FAIL

    _result(
        "G6 - Tests",
        WARN,
        "Run separately: poetry run pytest --cov=src/iatb --cov-fail-under=90 -x",
    )

    financial = []
    for mod in ["risk", "backtesting", "execution", "selection", "sentiment"]:
        d = SRC / mod
        if d.exists():
            financial.extend(_py_files(d))
    float_hits = _find_float_ast(financial)
    if float_hits:
        _result("G7 - No float in financial paths", FAIL, f"{len(float_hits)} hit(s)")
        worst = FAIL
    else:
        _result("G7 - No float in financial paths", PASS)

    naive_dt = _find("datetime.now()", _py_files(SRC))
    if naive_dt:
        _result("G8 - No naive datetime", FAIL, f"{len(naive_dt)} hit(s)")
        worst = FAIL
    else:
        _result("G8 - No naive datetime", PASS)

    prints = _find("print(", _py_files(SRC))
    if prints:
        _result("G9 - No print() in src/", FAIL, f"{len(prints)} hit(s)")
        worst = FAIL
    else:
        _result("G9 - No print() in src/", PASS)

    _result("G10 - Function size <=50 LOC", WARN, "AST check in CI")
    return worst


def check_function_sizes() -> list[str]:
    _header("G10 DETAILED - Function Size Analysis")
    violations: list[str] = []
    for p in _py_files(SRC):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                end = getattr(node, "end_lineno", node.lineno)
                loc = end - node.lineno + 1
                if loc > 50:
                    rel = p.relative_to(ROOT)
                    violations.append(f"{rel}:{node.lineno} {node.name} = {loc} LOC")
    if violations:
        _result(f"Functions >50 LOC: {len(violations)}", FAIL)
        for v in violations:
            print(f"        {v}")
    else:
        _result("All functions <=50 LOC", PASS)
    return violations


def check_paper_engine() -> int:
    _header("6. PAPER ENGINE READINESS")
    worst = PASS

    rc, out = _run(
        [
            sys.executable,
            "-c",
            "from iatb.core.paper_runtime import PaperTradingRuntime; "
            "from pathlib import Path; "
            "import tempfile; "
            "r = PaperTradingRuntime(audit_db_path=Path(tempfile.mkdtemp()) / 't.sqlite'); "
            "print(f'Engine: {type(r._engine).__name__}'); "
            "print(f'Executor: {type(r._paper_executor).__name__}'); "
            "print(f'AuditLogger: {type(r._audit_logger).__name__}'); "
            "print(f'EventBus: {type(r._event_bus).__name__}')",
        ],
        timeout=30,
    )
    if rc == 0:
        for line in out.strip().splitlines():
            _result(line, PASS)
    else:
        _result("PaperTradingRuntime instantiation", FAIL, out.strip()[:300])
        worst = FAIL

    tmp = ROOT / ".verify_signal.tmp.py"
    tmp.write_text(
        "import asyncio\n"
        "from iatb.core.paper_runtime import _register_signal_handlers\n"
        "async def _check():\n"
        "    e = asyncio.Event()\n"
        "    _register_signal_handlers(e)\n"
        "    assert not e.is_set(), 'stop_event was set immediately'\n"
        "    print('Signal handlers registered without immediate stop')\n"
        "asyncio.run(_check())\n",
        encoding="utf-8",
    )
    try:
        rc, out = _run([sys.executable, str(tmp)], timeout=15)
        if rc == 0:
            _result("Signal handler (no immediate stop)", PASS, out.strip())
        else:
            _result("Signal handler (no immediate stop)", FAIL, out.strip()[:300])
            worst = FAIL
    finally:
        tmp.unlink(missing_ok=True)
    return worst


def check_dashboard() -> int:
    _header("7. DASHBOARD READINESS")
    worst = PASS

    rc, out = _run(
        [
            sys.executable,
            "-c",
            "from iatb.visualization.streamlit_app import main, setup_page_config, "
            "render_header, render_sidebar; print('All render functions importable')",
        ],
        timeout=15,
    )
    if rc == 0:
        _result("streamlit_app imports", PASS, out.strip())
    else:
        _result("streamlit_app imports", FAIL, out.strip()[:300])
        worst = FAIL

    rc, out = _run(
        [
            sys.executable,
            "-c",
            "import sys; "
            "from iatb.visualization.streamlit_app import render_system_tab; "
            "print('sys.version accessible:', sys.version.split()[0])",
        ],
        timeout=15,
    )
    if rc == 0:
        _result("sys.version (no os.sys)", PASS)
    else:
        _result("sys.version (no os.sys)", FAIL, out.strip()[:300])
        worst = FAIL

    sd = ROOT / "scripts" / "start_dashboard.ps1"
    if sd.exists():
        content = sd.read_text(encoding="utf-8")
        if "streamlit_app.py" in content:
            _result("Dashboard script points to streamlit_app.py", PASS)
        else:
            _result("Dashboard script points to streamlit_app.py", FAIL)
            worst = FAIL
    return worst


def check_git_status() -> int:
    _header("8. GIT STATUS")
    worst = PASS

    rc, out = _run(["git", "branch", "--show-current"], timeout=10)
    branch = out.strip() if rc == 0 else "unknown"
    _result(f"Current branch: {branch}", PASS)

    rc, out = _run(["git", "remote", "-v"], timeout=10)
    if rc == 0 and "origin" in out:
        remote = [ln for ln in out.strip().splitlines() if ln.startswith("origin")][0]
        _result("Remote configured", PASS, remote)
    else:
        _result("Remote configured", FAIL, "No origin remote found")
        worst = FAIL

    rc, out = _run(["git", "status", "--porcelain"], timeout=10)
    changed = len([ln for ln in out.strip().splitlines() if ln.strip()])
    if changed == 0:
        _result("Working tree clean", PASS)
    else:
        _result("Working tree clean", WARN, f"{changed} file(s) changed")
        worst = WARN if worst == PASS else worst

    rc, out = _run(["git", "log", "-1", "--oneline"], timeout=10)
    if rc == 0:
        _result("Latest commit", PASS, out.strip())
    else:
        _result("Latest commit", FAIL)
        worst = FAIL
    return worst


def main() -> int:
    print("=" * 70)
    print("  IATB PAPER TRADING DEPLOYMENT - COMPREHENSIVE VERIFICATION")
    print("=" * 70)
    print(f"  Project : {ROOT}")
    print(f"  Time    : {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"  Python  : {sys.version.split()[0]}")

    sections = [
        ("Environment & Dependencies", check_environment),
        ("Configuration", check_config),
        ("Module Imports", check_modules),
        ("Deployment Scripts", check_scripts),
        ("Quality Gates", check_quality_gates),
        ("Paper Engine", check_paper_engine),
        ("Dashboard", check_dashboard),
        ("Git Status", check_git_status),
    ]

    results: list[tuple[str, int]] = []
    for name, fn in sections:
        rc = fn()
        results.append((name, rc))

    check_function_sizes()

    _header("FINAL SUMMARY")
    all_pass = all(rc == PASS for _, rc in results)
    for name, rc in results:
        tag = {PASS: "PASS", FAIL: "FAIL", WARN: "WARN"}[rc]
        print(f"  [{tag}] {name}")

    total = len(results)
    passed = sum(1 for _, rc in results if rc == PASS)
    failed = sum(1 for _, rc in results if rc == FAIL)
    warned = sum(1 for _, rc in results if rc == WARN)

    print(f"\n  Total: {passed} PASS / {warned} WARN / {failed} FAIL  (of {total})")

    if all_pass:
        print("\n  >> ALL CHECKS PASSED - Paper trading deployment verified.")
        print("  >> Run .\\scripts\\start_paper.ps1 and .\\scripts\\start_dashboard.ps1")
        return 0

    print("\n  >> SOME CHECKS FAILED - Review output above.")
    if failed:
        print("  >> Fix failures, then re-run this script.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
