#!/usr/bin/env python3
"""CI runner — single source of truth for all CI checks.

Usage:
    uv run scripts/ci.py           # Run all checks
    uv run scripts/ci.py --fix     # Auto-fix formatting issues first
    uv run scripts/ci.py --verbose # Show output even on success
"""

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass


DEFAULT_STEP_TIMEOUT_SECONDS = 300
DEFAULT_TIMEOUT_SECONDS = 120

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"
BOLD = "\033[1m"

FAILURE_OUTPUT_LINES = 50


@dataclass
class Step:
    """A CI step to execute."""

    name: str
    command: str
    fix_command: str | None = None


STEPS: list[Step] = [
    Step(
        name="Lint",
        command="uv run ruff check .",
        fix_command="uv run ruff check . --fix",
    ),
    Step(
        name="Format check",
        command="uv run ruff format --check .",
        fix_command="uv run ruff format .",
    ),
    Step(
        name="Type check",
        command="uv run ty check .",
    ),
    Step(
        name="Markdown format check",
        command="uv run python scripts/check_markdown.py",
        fix_command="uv run python scripts/check_markdown.py --fix",
    ),
    Step(
        name="Tests",
        command="uv run pytest -v",
    ),
    Step(
        name="Worktree clean check",
        command="git status --porcelain",
    ),
]


def use_color() -> bool:
    """Check if stdout supports color output."""
    return sys.stdout.isatty()


def colorize(text: str, color: str) -> str:
    """Apply ANSI color if stdout is a TTY."""
    if use_color():
        return f"{color}{text}{RESET}"
    return text


def run_step(
    step: Step,
    fix_mode: bool,
    verbose: bool,
    step_timeout: int,
    deadline: float | None = None,
) -> tuple[bool, str]:
    """Run a single CI step.

    Args:
        step: The step to run.
        fix_mode: If True and step has fix_command, run that instead.
        verbose: If True, always return full output.
        step_timeout: Timeout in seconds for the step (0 = no timeout).
        deadline: Monotonic clock deadline for overall CI run.

    Returns:
        Tuple of (success, output_to_display).
    """
    if fix_mode and step.fix_command:
        command = step.fix_command
    else:
        command = step.command

    effective_timeout: float | None = None
    if step_timeout > 0:
        effective_timeout = float(step_timeout)
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            remaining = 0.1
        if effective_timeout is None:
            effective_timeout = remaining
        else:
            effective_timeout = min(effective_timeout, remaining)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"Step timed out after {step_timeout} seconds."

    output = result.stdout + result.stderr

    if step.name == "Worktree clean check":
        if result.stdout.strip():
            return False, f"Uncommitted changes:\n{result.stdout}"
        return True, ""

    if result.returncode == 0:
        return True, output if verbose else ""

    lines = output.strip().split("\n")
    if len(lines) > FAILURE_OUTPUT_LINES:
        truncated = lines[-FAILURE_OUTPUT_LINES:]
        return False, "\n".join(truncated)
    return False, output


def run_ci(
    fix_mode: bool = False,
    verbose: bool = False,
    step_timeout: int = DEFAULT_STEP_TIMEOUT_SECONDS,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> int:
    """Run CI checks.

    Args:
        fix_mode: If True, run fix commands where available.
        verbose: If True, show output even on success.
        step_timeout: Timeout in seconds per step (0 = no timeout).
        timeout: Overall timeout in seconds (0 = no timeout).

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    start_time = time.monotonic()
    deadline: float | None = None
    if timeout > 0:
        deadline = start_time + timeout

    failed_steps: list[tuple[Step, str]] = []
    passed_count = 0
    timed_out = False

    for step in STEPS:
        if deadline is not None:
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout:
                timed_out = True
                break

        success, output = run_step(
            step, fix_mode, verbose, step_timeout, deadline
        )

        if success:
            print(colorize(f"✓ {step.name}", GREEN))
            passed_count += 1
            if verbose and output:
                print(output)
        else:
            print(colorize(f"✗ {step.name}", RED))
            failed_steps.append((step, output))
            if deadline is not None and time.monotonic() >= deadline:
                timed_out = True
                break

    if timed_out:
        elapsed = time.monotonic() - start_time
        print()
        print(colorize("✗ TIMEOUT", RED + BOLD))
        print(
            f"CI exceeded {timeout}s (elapsed: {elapsed:.0f}s). "
            "Investigate hanging steps."
        )
        return 1

    for step, output in failed_steps:
        print()
        print(colorize(f"{step.name} failed:", RED + BOLD))
        cmd = (
            step.fix_command if fix_mode and step.fix_command else step.command
        )
        print(f"Command: {cmd}")
        print("─" * 60)
        if output:
            print(output)
        print("─" * 60)

    total = len(STEPS)
    failed = len(failed_steps)
    elapsed = time.monotonic() - start_time
    print()
    if failed == 0:
        print(
            colorize(
                f"All {total} checks passed ({elapsed:.0f}s)", GREEN + BOLD
            )
        )
        return 0
    else:
        print(
            colorize(f"Summary: {failed} of {total} checks failed", RED + BOLD)
        )
        return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run CI checks locally",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Run fix commands for auto-fixable steps",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show output even on success",
    )
    parser.add_argument(
        "--step-timeout",
        type=int,
        default=DEFAULT_STEP_TIMEOUT_SECONDS,
        help=(
            "Timeout per step "
            f"(default: {DEFAULT_STEP_TIMEOUT_SECONDS}, 0 = none)"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Overall timeout (default: {DEFAULT_TIMEOUT_SECONDS}, 0 = none)",
    )

    args = parser.parse_args()

    return run_ci(
        fix_mode=args.fix,
        verbose=args.verbose,
        step_timeout=args.step_timeout,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    sys.exit(main())
