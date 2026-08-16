"""Idempotent, cross-platform onboarding for one Nutcracker repository.

This module owns setup only. It never changes memory-engine algorithms; it
creates repository-local state and registers the existing stdio MCP adapter.
"""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from storage.episode_store import init_db


AGENTS_START = "<!-- nutcracker:start -->"
AGENTS_END = "<!-- nutcracker:end -->"
DEFAULT_DB_RELATIVE_PATH = Path(".nutcracker") / "memory.db"
CommandRunner = Callable[[Sequence[str], Path | None], subprocess.CompletedProcess[str]]
ProbeRunner = Callable[[Sequence[str], float], subprocess.CompletedProcess[str]]
# Fresh FastEmbed/MCP environments can take several seconds to import on slower
# machines. This remains bounded and never enters the stdio serving loop.
MCP_PROBE_TIMEOUT_SECONDS = 20.0
MAX_MCP_SLUG_LENGTH = 48


class CodexPreflightError(RuntimeError):
    """Raised before local setup when the required Codex CLI is unavailable."""


class MCPConflictError(RuntimeError):
    """Raised when a managed MCP name is already configured differently."""


class MCPRegistrationError(RuntimeError):
    """Raised after local setup when `codex mcp add` cannot register the server."""


@dataclass(frozen=True, slots=True)
class RepositoryRoot:
    """The root selected for setup and whether Git selected it."""

    path: Path
    is_git_repository: bool


@dataclass(frozen=True, slots=True)
class InitResult:
    """Useful details reported by the CLI and asserted by onboarding tests."""

    repo_root: Path
    db_path: Path
    mcp_name: str
    is_git_repository: bool
    gitignore_changed: bool
    agents_changed: bool
    mcp_changed: bool


@dataclass(frozen=True, slots=True)
class DoctorResult:
    """Individual checks performed without mutating repository configuration."""

    checks: tuple[tuple[str, bool, str], ...]

    @property
    def ready(self) -> bool:
        return all(ok for _, ok, _ in self.checks)


@dataclass(frozen=True, slots=True)
class MCPConfiguration:
    """The parsed MCP entry and its compatibility with one repository."""

    name: str
    entry: Mapping[str, object] | None
    matches: bool
    issues: tuple[str, ...]


def _run_command(
    arguments: Sequence[str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(arguments),
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_probe(arguments: Sequence[str], timeout: float) -> subprocess.CompletedProcess[str]:
    """Run a bounded interpreter probe without starting the stdio server loop."""

    return subprocess.run(
        list(arguments),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def detect_repo_root(
    cwd: Path | None = None,
    *,
    runner: CommandRunner = _run_command,
) -> RepositoryRoot:
    """Find the Git root, or deliberately use the current directory without Git.

    Nutcracker's current file anchors do not require Git. Falling back to the
    current directory keeps the CLI useful for a new project before its first
    commit while making the weaker repository boundary explicit in CLI output.
    """

    working_directory = (cwd or Path.cwd()).expanduser().resolve()
    try:
        completed = runner(["git", "rev-parse", "--show-toplevel"], working_directory)
    except OSError:
        # Git is optional for the current file-anchor MVP. The fallback remains
        # explicit in the CLI output so the user understands the boundary used.
        return RepositoryRoot(working_directory, False)
    if completed.returncode == 0 and completed.stdout.strip():
        return RepositoryRoot(Path(completed.stdout.strip()).resolve(), True)
    return RepositoryRoot(working_directory, False)


def mcp_server_name(repo_root: Path) -> str:
    """Create a readable, stable name unique to an absolute local repository.

    The basename keeps `codex mcp list` understandable; a short SHA-256 digest
    of the resolved path avoids collisions between repositories with the same
    basename. One MCP registration intentionally serves one repository.
    """

    root = repo_root.expanduser().resolve()
    slug = re.sub(r"[^a-z0-9]+", "-", root.name.lower()).strip("-") or "repository"
    slug = slug[:MAX_MCP_SLUG_LENGTH].rstrip("-") or "repository"
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:8]
    return f"nutcracker-{slug}-{digest}"


def _agents_template() -> str:
    """Read the versioned policy resource shared by init and doctor."""

    return (
        importlib.resources.files("nutcracker_cli")
        .joinpath("templates/nutcracker_agents.md")
        .read_text(encoding="utf-8")
        .strip()
    )


def _template_block(newline: str) -> str:
    policy = (
        newline.join(_agents_template().splitlines())
    )
    return f"{AGENTS_START}{newline}{newline}{policy}{newline}{newline}{AGENTS_END}{newline}"


def _read_text(path: Path) -> str:
    """Read text without normalizing CRLF, so edits preserve file style."""

    with path.open("r", encoding="utf-8", newline="") as file:
        return file.read()


def _line_ending(content: str) -> str:
    if "\r\n" in content:
        return "\r\n"
    if "\n" in content:
        return "\n"
    return os.linesep


def _atomic_write(path: Path, content: str) -> None:
    """Replace one text file atomically within its existing parent directory."""

    temporary = path.with_name(f".{path.name}.nutcracker-tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as file:
            file.write(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def ensure_gitignore(repo_root: Path) -> bool:
    """Add the repository-local database directory exactly once."""

    path = repo_root / ".gitignore"
    existing = _read_text(path) if path.exists() else ""
    newline = _line_ending(existing)
    lines = existing.splitlines()
    if ".nutcracker/" in lines:
        return False
    suffix = "" if not existing or existing.endswith(("\n", "\r")) else newline
    _atomic_write(path, f"{existing}{suffix}.nutcracker/{newline}")
    return True


def install_agents_policy(repo_root: Path) -> bool:
    """Create or replace only Nutcracker's marker-delimited AGENTS.md block."""

    path = repo_root / "AGENTS.md"
    existing = _read_text(path) if path.exists() else ""
    newline = _line_ending(existing)
    starts = [match.start() for match in re.finditer(re.escape(AGENTS_START), existing)]
    ends = [match.start() for match in re.finditer(re.escape(AGENTS_END), existing)]
    if len(starts) != len(ends):
        raise ValueError("AGENTS.md has unmatched Nutcracker policy markers")
    if len(starts) > 1:
        raise ValueError("AGENTS.md has more than one Nutcracker policy block")

    block = _template_block(newline)
    if not starts:
        separator = "" if not existing or existing.endswith(("\n", "\r")) else newline
        updated = f"{existing}{separator}{block}"
    else:
        start = starts[0]
        end_marker = existing.find(AGENTS_END, start)
        if end_marker == -1:
            raise ValueError("AGENTS.md has an invalid Nutcracker policy block")
        end = end_marker + len(AGENTS_END)
        suffix = existing[end:]
        if suffix and not suffix.startswith(("\n", "\r")):
            suffix = f"{newline}{suffix}"
        updated = f"{existing[:start]}{block.rstrip()}" f"{suffix}"

    if updated == existing:
        return False
    _atomic_write(path, updated)
    return True


def _codex_config_path() -> Path:
    """Return Codex's documented default config location, honoring CODEX_HOME."""

    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return codex_home / "config.toml"


def _read_codex_config(path: Path | None = None) -> Mapping[str, object]:
    config_path = path or _codex_config_path()
    if not config_path.exists():
        return {}
    try:
        return tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"Cannot read Codex configuration: {config_path}") from error


def _mcp_entry(config: Mapping[str, object], name: str) -> Mapping[str, object] | None:
    servers = config.get("mcp_servers")
    if not isinstance(servers, Mapping):
        return None
    entry = servers.get(name)
    return entry if isinstance(entry, Mapping) else None


def _configured_db_path(environment: Mapping[str, object], repo_root: Path) -> Path | None:
    raw = environment.get("NUTCRACKER_DB_PATH")
    if raw is None or not str(raw).strip():
        return None
    candidate = Path(str(raw)).expanduser()
    return (candidate if candidate.is_absolute() else repo_root / candidate).resolve()


def inspect_mcp_configuration(
    entry: Mapping[str, object] | None,
    repo_root: Path,
    python_executable: str,
) -> MCPConfiguration:
    """Explain whether an existing MCP record is safe for this installation."""

    name = mcp_server_name(repo_root)
    if entry is None:
        return MCPConfiguration(name, None, False, ("registration is missing",))
    environment = entry.get("env")
    if not isinstance(environment, Mapping):
        return MCPConfiguration(name, entry, False, ("environment is missing",))

    issues: list[str] = []
    configured_root = environment.get("NUTCRACKER_REPO_ROOT")
    try:
        root_matches = Path(str(configured_root)).expanduser().resolve() == repo_root.resolve()
    except (OSError, ValueError):
        root_matches = False
    if not root_matches:
        issues.append(f"repo_root is {configured_root!r}, expected {str(repo_root.resolve())!r}")
    if entry.get("enabled") is False:
        issues.append("registration is disabled")
    if str(entry.get("command", "")) != python_executable:
        issues.append(
            f"command is {entry.get('command')!r}, expected {python_executable!r}"
        )
    if entry.get("args") != ["-m", "mcp_server.server"]:
        issues.append(
            f"args are {entry.get('args')!r}, expected ['-m', 'mcp_server.server']"
        )
    configured_db = _configured_db_path(environment, repo_root)
    expected_db = (repo_root / DEFAULT_DB_RELATIVE_PATH).resolve()
    if configured_db is not None and configured_db != expected_db:
        issues.append(f"database is {str(configured_db)!r}, expected {str(expected_db)!r}")
    return MCPConfiguration(name, entry, not issues, tuple(issues))


def _format_mcp_conflict(configuration: MCPConfiguration) -> str:
    details = "; ".join(configuration.issues)
    return (
        "Existing MCP registration differs from Nutcracker's expected configuration. "
        f"Name: {configuration.name}. Details: {details}. "
        f"Review it, then run `codex mcp remove {configuration.name}` and retry `nutcracker init`."
    )


def _resolve_codex(codex_executable: str = "codex") -> str:
    resolved = shutil.which(codex_executable)
    if resolved is None:
        raise CodexPreflightError("Codex CLI not available on PATH. No project files were changed.")
    return resolved


def preflight_codex(
    *,
    runner: CommandRunner = _run_command,
    codex_executable: str = "codex",
) -> str:
    """Confirm Codex and its MCP command exist before writing project files."""

    selected_codex = _resolve_codex(codex_executable)
    try:
        version = runner([selected_codex, "--version"], None)
        mcp_help = runner([selected_codex, "mcp", "--help"], None)
    except OSError as error:
        raise CodexPreflightError(
            "Codex CLI could not be executed. No project files were changed."
        ) from error
    if version.returncode != 0 or mcp_help.returncode != 0:
        raise CodexPreflightError(
            "Codex CLI or its MCP commands are unavailable. No project files were changed."
        )
    return selected_codex


def build_mcp_add_command(
    repo_root: Path,
    *,
    name: str | None = None,
    python_executable: str | None = None,
    codex_executable: str = "codex",
) -> list[str]:
    """Build the official CLI registration command without platform shell syntax."""

    resolved_root = repo_root.expanduser().resolve()
    selected_name = name or mcp_server_name(resolved_root)
    selected_python = python_executable or sys.executable
    return [
        codex_executable,
        "mcp",
        "add",
        selected_name,
        "--env",
        f"NUTCRACKER_REPO_ROOT={resolved_root}",
        "--",
        selected_python,
        "-m",
        "mcp_server.server",
    ]


def ensure_mcp_registration(
    repo_root: Path,
    *,
    runner: CommandRunner = _run_command,
    python_executable: str | None = None,
    codex_executable: str = "codex",
    config_path: Path | None = None,
) -> bool:
    """Register the installed stdio server once using Codex's public CLI.

    A missing registration is added and a matching registration is left intact.
    A registration with the expected name but different configuration raises
    ``MCPConflictError``; the user must resolve that conflict manually before
    retrying setup.
    """

    selected_python = python_executable or sys.executable
    selected_codex = _resolve_codex(codex_executable)
    name = mcp_server_name(repo_root)
    entry = _mcp_entry(_read_codex_config(config_path), name)
    configuration = inspect_mcp_configuration(entry, repo_root, selected_python)
    if entry is not None and not configuration.matches:
        raise MCPConflictError(_format_mcp_conflict(configuration))
    if configuration.matches:
        return False

    added = runner(
        build_mcp_add_command(
            repo_root,
            name=name,
            python_executable=selected_python,
            codex_executable=selected_codex,
        ),
        None,
    )
    if added.returncode != 0:
        raise MCPRegistrationError(added.stderr.strip() or "Could not register Nutcracker MCP")
    return True


def initialize_repository(
    cwd: Path | None = None,
    *,
    runner: CommandRunner = _run_command,
    python_executable: str | None = None,
    codex_executable: str = "codex",
    config_path: Path | None = None,
) -> InitResult:
    """Create all repository-local setup state and register one MCP server."""

    detected = detect_repo_root(cwd, runner=runner)
    repo_root = detected.path
    selected_python = python_executable or sys.executable
    selected_codex = preflight_codex(runner=runner, codex_executable=codex_executable)
    existing = _mcp_entry(_read_codex_config(config_path), mcp_server_name(repo_root))
    configuration = inspect_mcp_configuration(existing, repo_root, selected_python)
    if existing is not None and not configuration.matches:
        raise MCPConflictError(_format_mcp_conflict(configuration))
    memory_directory = repo_root / ".nutcracker"
    memory_directory.mkdir(parents=True, exist_ok=True)
    db_path = memory_directory / "memory.db"
    init_db(str(db_path))
    gitignore_changed = ensure_gitignore(repo_root)
    agents_changed = install_agents_policy(repo_root)
    mcp_changed = ensure_mcp_registration(
        repo_root,
        runner=runner,
        python_executable=selected_python,
        codex_executable=selected_codex,
        config_path=config_path,
    )
    return InitResult(
        repo_root=repo_root,
        db_path=db_path,
        mcp_name=mcp_server_name(repo_root),
        is_git_repository=detected.is_git_repository,
        gitignore_changed=gitignore_changed,
        agents_changed=agents_changed,
        mcp_changed=mcp_changed,
    )


def _database_check(db_path: Path) -> tuple[bool, str]:
    if not db_path.is_file():
        return False, f"Database is missing: {db_path}"
    try:
        with sqlite3.connect(db_path) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
    except sqlite3.Error as error:
        return False, f"SQLite cannot open database: {error}"
    required = {"episodes", "anchors", "episode_embeddings"}
    if not required <= tables:
        return False, "SQLite schema is incomplete; run nutcracker init"
    return True, str(db_path)


def _agents_policy_check(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, "AGENTS.md is missing"
    content = _read_text(path)
    starts = [match.start() for match in re.finditer(re.escape(AGENTS_START), content)]
    ends = [match.start() for match in re.finditer(re.escape(AGENTS_END), content)]
    if len(starts) != len(ends) or len(starts) != 1:
        return False, "AGENTS.md does not contain one complete Nutcracker policy block"
    end = content.find(AGENTS_END, starts[0])
    if end == -1:
        return False, "AGENTS.md has inconsistent Nutcracker policy markers"
    managed = content[starts[0] + len(AGENTS_START) : end]
    expected = _agents_template()
    # The template is package data with LF, while target repositories can use
    # CRLF. Content must match, but newline convention is intentionally neutral.
    managed = managed.replace("\r\n", "\n").replace("\r", "\n").strip()
    expected = expected.replace("\r\n", "\n").replace("\r", "\n").strip()
    if managed != expected:
        return False, "Nutcracker policy is outdated or modified; run nutcracker init"
    return True, str(path)


def _server_tools_check(
    command: str,
    *,
    probe_runner: ProbeRunner = _run_probe,
) -> tuple[bool, str]:
    """Probe the configured Python, import server tools, and exit promptly.

    This deliberately avoids ``mcp.run()``: it proves the registered
    interpreter can import Nutcracker and expose both tools, but does not
    perform a live stdio handshake or download embeddings.
    """

    probe = (
        "import asyncio,json; from mcp_server.server import mcp; "
        "print(json.dumps([tool.name for tool in asyncio.run(mcp.list_tools())]))"
    )
    try:
        completed = probe_runner([command, "-c", probe], MCP_PROBE_TIMEOUT_SECONDS)
    except FileNotFoundError:
        return False, f"MCP interpreter does not exist: {command}"
    except subprocess.TimeoutExpired:
        return False, "MCP server probe timed out"
    except OSError as error:
        return False, f"MCP server probe could not start: {error}"
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        return False, f"MCP server probe failed: {detail or 'non-zero exit'}"
    try:
        names = set(json.loads(completed.stdout))
    except (TypeError, json.JSONDecodeError):
        return False, "MCP server probe returned invalid tool data"
    required = {"memory_save", "memory_recall"}
    if required <= names:
        return True, "memory_save, memory_recall"
    return False, "MCP server is missing expected memory tools"


def run_doctor(
    cwd: Path | None = None,
    *,
    config_path: Path | None = None,
    probe_runner: ProbeRunner = _run_probe,
) -> DoctorResult:
    """Inspect one repository's local setup without creating memories or config."""

    detected = detect_repo_root(cwd)
    repo_root = detected.path
    db_path = repo_root / DEFAULT_DB_RELATIVE_PATH
    name = mcp_server_name(repo_root)
    codex = shutil.which("codex")
    entry: Mapping[str, object] | None = None
    configuration: MCPConfiguration | None = None
    config_error: str | None = None
    try:
        entry = _mcp_entry(_read_codex_config(config_path), name)
        if codex is not None:
            configuration = inspect_mcp_configuration(entry, repo_root, sys.executable)
    except ValueError as error:
        config_error = str(error)

    checks: list[tuple[str, bool, str]] = [
        ("Repository", True, str(repo_root)),
        ("Local memory directory", (repo_root / ".nutcracker").is_dir(), str(repo_root / ".nutcracker")),
        ("SQLite", *_database_check(db_path)),
        ("AGENTS.md policy", *_agents_policy_check(repo_root / "AGENTS.md")),
        ("Codex CLI", codex is not None, codex or "codex was not found on PATH"),
    ]
    if config_error:
        checks.append(("MCP registration", False, config_error))
    else:
        registration_ok = configuration is not None and configuration.matches
        registration_detail = (
            name
            if registration_ok
            else "; ".join(configuration.issues)
            if configuration is not None
            else f"{name} is not registered"
        )
        checks.append(
            (
                "MCP registration",
                registration_ok,
                registration_detail,
            )
        )
    if configuration is not None and configuration.matches:
        checks.append(("MCP server process and tools", *_server_tools_check(
            str(entry["command"]), probe_runner=probe_runner
        )))
    else:
        checks.append(("MCP server process and tools", False, "MCP registration is not valid"))
    return DoctorResult(tuple(checks))
