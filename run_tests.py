"""Cross-platform test entry point.

The repo root is a ComfyUI custom-node package (it has an ``__init__.py`` with
relative imports), so running pytest from the repo root makes pytest try to
import that entry point as a package node. Run the suite from ``tests/``
instead (any CWD) to keep the repo root out of pytest's package tree.

Usage:  python run_tests.py [pytest args...]
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

TESTS_DIR = pathlib.Path(__file__).resolve().parent / "tests"


def main() -> int:
    try:
        import pytest  # noqa: F401
    except ImportError:
        print(
            "pytest is not installed. Install it in the ComfyUI Python, e.g.\n"
            "  python -m pip install pytest",
            file=sys.stderr,
        )
        return 2
    cmd = [sys.executable, "-m", "pytest", *sys.argv[1:]]
    return int(subprocess.call(cmd, cwd=str(TESTS_DIR)))


if __name__ == "__main__":
    raise SystemExit(main())
