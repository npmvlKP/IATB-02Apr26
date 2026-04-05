#!/usr/bin/env python
"""
Legacy dashboard entrypoint.

This wrapper preserves `scripts/dashboard.py` usage while forwarding execution
to the unified deployment script.
"""

from __future__ import annotations

import runpy
from pathlib import Path


def main() -> int:
    script_path = Path(__file__).with_name("deploy_paper_trade.py")
    runpy.run_path(script_path.as_posix(), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
