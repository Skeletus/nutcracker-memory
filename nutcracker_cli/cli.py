"""The small public Nutcracker command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path

from nutcracker_cli.onboarding import (
    CodexPreflightError,
    MCPConflictError,
    MCPRegistrationError,
    initialize_repository,
    run_doctor,
    use_repository,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nutcracker", description="Nutcracker Memory setup")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="Initialize Nutcracker in the current repository")
    subparsers.add_parser("use", help="Select this repository for the next Codex session")
    subparsers.add_parser("doctor", help="Check Nutcracker setup in the current repository")
    return parser


def _run_init() -> int:
    result = initialize_repository(Path.cwd())
    print(f"Initializing Nutcracker for:\n  {result.repo_root}")
    if not result.is_git_repository:
        print("Warning: Git root was not found; using the current directory as the repository root.")
    # ASCII keeps the first-run command usable in Windows consoles configured
    # with legacy code pages as well as on UTF-8 Unix terminals.
    print("[OK] Created .nutcracker/ and initialized memory database")
    print("[OK] Added .nutcracker/ to .gitignore" if result.gitignore_changed else "[OK] .gitignore already configured")
    print("[OK] Installed Nutcracker policy in AGENTS.md" if result.agents_changed else "[OK] Nutcracker policy already current")
    print(
        f"[OK] {'Activated' if result.mcp_changed else 'Verified'} Codex MCP: {result.mcp_name}"
    )
    print("\nNutcracker is ready.\n\nRun:\n  nutcracker doctor")
    return 0


def _run_doctor() -> int:
    result = run_doctor(Path.cwd())
    print("Nutcracker doctor\n")
    for check in result.checks:
        prefix = {"ok": "[OK]", "warn": "[WARN]", "error": "[ERROR]"}[check.status]
        print(f"{prefix} {check.name}: {check.detail}")
    print("\nReady." if result.ready else "\nNot ready. Run `nutcracker init` or address the errors above.")
    return 0 if result.ready else 1


def _run_use() -> int:
    result = use_repository(Path.cwd())
    if result.mcp_changed:
        print(f"Nutcracker · Active repository\n{result.repo_root}")
    else:
        print(f"Nutcracker · Repository already active\n{result.repo_root.name}")
    print("Start a new Codex session to use this repository's memory.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the public CLI and return a portable process status."""

    arguments = _parser().parse_args(argv)
    if arguments.command in {"init", "use"}:
        try:
            return _run_init() if arguments.command == "init" else _run_use()
        except CodexPreflightError as error:
            print(f"[ERROR] {error}")
            return 1
        except MCPConflictError as error:
            if arguments.command == "init":
                print("[ERROR] Local Nutcracker setup completed, but MCP activation needs attention.")
            print(f"[ERROR] {error}")
            return 1
        except MCPRegistrationError as error:
            print("[ERROR] Local Nutcracker setup completed, but MCP registration failed.")
            print(f"{error}\nFix Codex and run `nutcracker init` again.")
            return 1
        except (OSError, RuntimeError, ValueError) as error:
            print(f"[ERROR] Nutcracker init failed: {error}")
            return 1
    return _run_doctor()


if __name__ == "__main__":
    raise SystemExit(main())
