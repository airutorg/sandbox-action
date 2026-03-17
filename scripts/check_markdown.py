#!/usr/bin/env python3
"""Wrapper for mdformat that fails on code block formatting errors.

mdformat with mdformat-ruff prints warnings when Python code blocks fail to
format but exits with code 0. This wrapper checks for those warnings and
exits with code 1 if any are found.

Usage:
    uv run python scripts/check_markdown.py [--fix] [paths...]
"""

import subprocess
import sys


def main() -> int:
    """Run mdformat and fail if code block formatting errors occur."""
    fix_mode = "--fix" in sys.argv
    args = [arg for arg in sys.argv[1:] if arg != "--fix"]

    cmd = ["uv", "run", "mdformat"]
    if not fix_mode:
        cmd.append("--check")
    cmd.extend(args if args else ["."])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    output = result.stdout + result.stderr
    has_format_errors = (
        "Failed formatting content of a python code block" in output
        or "error: Failed to parse" in output
    )

    if result.returncode != 0:
        return result.returncode
    if has_format_errors:
        print(
            "\nERROR: Code block formatting failures detected",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
