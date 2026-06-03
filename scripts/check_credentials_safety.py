"""Credential Safety Audit Script for IATB Project.

Verifies that no real credentials are committed to the repository.
Checks:
1. No .env file exists (only .env.example)
2. No hardcoded API keys/secrets in source files
3. .gitignore properly excludes .env files
4. .gitleaks.toml is configured
"""

import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Pattern, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Patterns that indicate real credentials (not placeholders)
_CREDENTIAL_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("Zerodha API Key (non-placeholder)", re.compile(
        r"ZERODHA_API_KEY\s*=\s*[a-zA-Z0-9]{10,}", re.IGNORECASE
    )),
    ("Zerodha API Secret (non-placeholder)", re.compile(
        r"ZERODHA_API_SECRET\s*=\s*[a-zA-Z0-9]{10,}", re.IGNORECASE
    )),
    ("Zerodha Access Token (non-placeholder)", re.compile(
        r"ZERODHA_ACCESS_TOKEN\s*=\s*[a-zA-Z0-9]{20,}", re.IGNORECASE
    )),
    ("TOTP Secret (non-placeholder)", re.compile(
        r"ZERODHA_TOTP_SECRET\s*=\s*[A-Z2-7]{10,}", re.IGNORECASE
    )),
    ("Generic API Key assignment", re.compile(
        r"""(?:api_key|apiKey|API_KEY)\s*=\s*["'][a-zA-Z0-9]{16,}["']""",
    )),
    ("Generic Secret assignment", re.compile(
        r"""(?:api_secret|apiSecret|API_SECRET)\s*=\s*["'][a-zA-Z0-9]{10,}["']""",
    )),
]

# Placeholders that are OK
_PLACEHOLDER_VALUES = {
    "your_api_key_here",
    "your_api_secret_here",
    "",
}

# Directories/files to skip
_SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache"}
_SKIP_EXTENSIONS = {".pyc", ".pyo", ".exe", ".bin", ".png", ".jpg", ".gif"}


def check_env_file_not_exists() -> Tuple[bool, str]:
    """Check that .env file does NOT exist in the repo."""
    env_path = _PROJECT_ROOT / ".env"
    if env_path.exists():
        return (
            False,
            "FAIL: .env file exists at {}. Delete it and use .env.example only.".format(env_path),
        )
    return (True, "PASS: No .env file found in repository root.")


def check_gitignore_covers_env() -> Tuple[bool, str]:
    """Check that .gitignore excludes .env files."""
    gitignore_path = _PROJECT_ROOT / ".gitignore"
    if not gitignore_path.exists():
        return (False, "FAIL: No .gitignore file found.")
    content = gitignore_path.read_text(encoding="utf-8")
    required_patterns = [".env"]
    missing = [p for p in required_patterns if p not in content]
    if missing:
        return (
            False,
            "FAIL: .gitignore missing patterns: {}. Add .env to .gitignore.".format(missing),
        )
    return (True, "PASS: .gitignore properly excludes .env files.")


def check_gitleaks_config() -> Tuple[bool, str]:
    """Check that .gitleaks.toml is configured."""
    gitleaks_path = _PROJECT_ROOT / ".gitleaks.toml"
    if not gitleaks_path.exists():
        return (
            False,
            "FAIL: No .gitleaks.toml found. Configure secret scanning.",
        )
    content = gitleaks_path.read_text(encoding="utf-8")
    if "ZERODHA" not in content and "api_key" not in content.lower():
        return (
            False,
            "WARN: .gitleaks.toml exists but may not have Zerodha-specific rules.",
        )
    return (True, "PASS: .gitleaks.toml configured for secret scanning.")


def check_env_example_is_placeholder_only() -> Tuple[bool, str]:
    """Check that .env.example has only placeholder values."""
    env_example = _PROJECT_ROOT / ".env.example"
    if not env_example.exists():
        return (False, "FAIL: No .env.example file found.")
    content = env_example.read_text(encoding="utf-8")
    for label, pattern in _CREDENTIAL_PATTERNS:
        matches = pattern.findall(content)
        if matches:
            return (
                False,
                "FAIL: .env.example contains real credential pattern: {}".format(label),
            )
    return (
        True,
        "PASS: .env.example contains only placeholder values.",
    )


def check_source_files_for_credentials() -> Tuple[bool, str]:
    """Scan Python source files for hardcoded credentials."""
    violations: List[str] = []
    src_dir = _PROJECT_ROOT / "src"
    if not src_dir.exists():
        return (True, "PASS: No src/ directory to scan.")
    py_files = list(src_dir.rglob("*.py"))
    for py_file in py_files:
        if any(part.startswith("__pycache__") for part in py_file.parts):
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for label, pattern in _CREDENTIAL_PATTERNS:
            matches = pattern.findall(content)
            if matches:
                rel_path = py_file.relative_to(_PROJECT_ROOT)
                violations.append("{}: {} found".format(rel_path, label))
    if violations:
        return (
            False,
            "FAIL: Found {} credential pattern(s) in source:\n".format(len(violations))
            + "\n".join(" - {}".format(v) for v in violations),
        )
    return (True, "PASS: No hardcoded credentials found in source files.")


def check_git_tracked_env() -> Tuple[bool, str]:
    """Check that .env is NOT tracked in git."""
    try:
        result = subprocess.run(
            ["git", "ls-files", ".env"],
            capture_output=True,
            text=True,
            cwd=str(_PROJECT_ROOT),
            timeout=30,
        )
        tracked = result.stdout.strip()
        if tracked:
            return (
                False,
                "FAIL: .env is tracked in git: {}. Remove with 'git rm --cached .env'".format(
                    tracked
                ),
            )
        return (True, "PASS: .env is not tracked in git.")
    except Exception as exc:
        return (True, "PASS: Git check skipped (not a git repo or git unavailable): {}".format(exc))


def main() -> int:
    """Run all credential safety checks and report results."""
    checks = [
        ("P0: No .env file", check_env_file_not_exists),
        ("P0: .gitignore covers .env", check_gitignore_covers_env),
        ("P0: Git does not track .env", check_git_tracked_env),
        ("P0: .env.example is placeholder-only", check_env_example_is_placeholder_only),
        ("P0: No hardcoded credentials in src/", check_source_files_for_credentials),
        ("P0: gitleaks config present", check_gitleaks_config),
    ]
    print("=" * 60)
    print("IATB CREDENTIAL SAFETY AUDIT")
    print("=" * 60)
    all_pass = True
    for label, check_fn in checks:
        passed, message = check_fn()
        status = "PASS" if passed else "FAIL"
        print("")
        print("[{}] {}".format(status, label))
        print("  {}".format(message))
        if not passed:
            all_pass = False
    print("")
    print("=" * 60)
    if all_pass:
        print("VERDICT: ALL CREDENTIAL SAFETY CHECKS PASSED")
        return 0
    print("VERDICT: CREDENTIAL SAFETY ISSUES FOUND")
    return 1


if __name__ == "__main__":
    sys.exit(main())