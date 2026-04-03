#!/usr/bin/env python
"""
Fallback secret scanner used when gitleaks action path is unavailable in CI.
"""

import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
MAX_FILE_SIZE_BYTES = 1_000_000
EXCLUDED_DIR_NAMES = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", "htmlcov"}
EXCLUDED_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".ico", ".exe", ".dll"}

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (RSA|EC|DSA|OPENSSH|PGP) PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"(?i)\b(api[_-]?key|token|secret|password|passwd)\b\s*[:=]\s*[\"']([^\"']+)[\"']"
    ),
]

PLACEHOLDER_MARKERS = {"example", "dummy", "sample", "placeholder", "changeme", "test", "xxxx"}


def _should_scan(path: Path) -> bool:
    if not path.is_file():
        return False
    if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if path.stat().st_size > MAX_FILE_SIZE_BYTES:
        return False
    return True


def _looks_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def _is_high_entropy_candidate(value: str) -> bool:
    if len(value) < 20 or any(char.isspace() for char in value):
        return False
    has_alpha = any(char.isalpha() for char in value)
    has_digit = any(char.isdigit() for char in value)
    return has_alpha and has_digit


def _scan_file(path: Path) -> list[str]:
    findings: list[str] = []
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return findings

    relative = path.relative_to(ROOT_DIR)
    for line_no, line in enumerate(content.splitlines(), start=1):
        for pattern in SECRET_PATTERNS:
            match = pattern.search(line)
            if match is None:
                continue
            if match.lastindex and match.lastindex >= 2:
                candidate = match.group(2)
                if _looks_placeholder(candidate):
                    continue
                if not _is_high_entropy_candidate(candidate):
                    continue
            findings.append(f"{relative}:{line_no}: {line.strip()}")
    return findings


def main() -> int:
    """Run fallback scan and return process exit code."""
    all_findings: list[str] = []
    for path in ROOT_DIR.rglob("*"):
        if not _should_scan(path):
            continue
        all_findings.extend(_scan_file(path))

    if not all_findings:
        print("Fallback secret scan passed: no high-confidence secrets detected.")
        return 0

    print("Fallback secret scan detected potential secrets:")
    for finding in all_findings:
        print(f"  {finding}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
