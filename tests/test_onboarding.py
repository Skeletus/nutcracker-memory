from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import sys
import json
import os
from pathlib import Path

import pytest

from nutcracker_cli.onboarding import (
    AGENTS_END,
    AGENTS_START,
    CodexPreflightError,
    MCPConflictError,
    MCPRegistrationError,
    _read_codex_config,
    build_mcp_add_command,
    detect_repo_root,
    ensure_gitignore,
    inspect_mcp_configuration,
    initialize_repository,
    install_agents_policy,
    mcp_server_name,
    run_doctor,
)


def _completed(
    arguments: list[str],
    stdout: str = "",
    returncode: int = 0,
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(arguments, returncode, stdout=stdout, stderr=stderr)


def _git_runner(arguments: list[str], cwd: Path | None) -> subprocess.CompletedProcess[str]:
    assert arguments == ["git", "rev-parse", "--show-toplevel"]
    assert cwd is not None
    return _completed(arguments, f"{cwd}\n")


def _no_git_runner(arguments: list[str], cwd: Path | None) -> subprocess.CompletedProcess[str]:
    return _completed(arguments, returncode=1)


def _successful_runner(calls: list[list[str]]):
    def runner(arguments: list[str], cwd: Path | None) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        if arguments[:3] == ["git", "rev-parse", "--show-toplevel"]:
            assert cwd is not None
            return _completed(arguments, f"{cwd}\n")
        return _completed(arguments)

    return runner


def _successful_probe(arguments: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    assert arguments[1] == "-c"
    assert timeout > 0
    return _completed(arguments, json.dumps(["memory_save", "memory_recall"]))


@pytest.fixture
def codex_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make simulated onboarding tests independent from the host PATH."""

    monkeypatch.setattr(
        "nutcracker_cli.onboarding.shutil.which",
        lambda executable: "/test/bin/codex",
    )


def _write_mcp_config(
    path: Path,
    repo: Path,
    *,
    command: str = "python-for-test",
    args: str = '["-m", "mcp_server.server"]',
    environment_lines: list[str] | None = None,
    enabled: str | None = None,
) -> None:
    name = mcp_server_name(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"[mcp_servers.{name}]", f"command = {json.dumps(command)}", f"args = {args}"]
    if enabled is not None:
        lines.append(f"enabled = {enabled}")
    lines.append(f"[mcp_servers.{name}.env]")
    lines.append(f"NUTCRACKER_REPO_ROOT = {json.dumps(repo.resolve().as_posix())}")
    lines.extend(environment_lines or [])
    path.write_text("\n".join(lines), encoding="utf-8")


def test_detect_repo_root_uses_git_root(tmp_path: Path) -> None:
    detected = detect_repo_root(tmp_path, runner=_git_runner)

    assert detected.path == tmp_path.resolve()
    assert detected.is_git_repository is True


def test_detect_repo_root_falls_back_to_cwd_without_git(tmp_path: Path) -> None:
    detected = detect_repo_root(tmp_path, runner=_no_git_runner)

    assert detected.path == tmp_path.resolve()
    assert detected.is_git_repository is False


def test_detect_repo_root_falls_back_when_git_is_not_installed(tmp_path: Path) -> None:
    def unavailable_git(arguments: list[str], cwd: Path | None) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("git")

    detected = detect_repo_root(tmp_path, runner=unavailable_git)

    assert detected.path == tmp_path.resolve()
    assert detected.is_git_repository is False


def test_init_creates_local_database_and_gitignore_once(
    tmp_path: Path,
    codex_available: None,
) -> None:
    calls: list[list[str]] = []
    config_path = tmp_path / "codex" / "config.toml"

    result = initialize_repository(
        tmp_path,
        runner=_successful_runner(calls),
        python_executable="python-for-test",
        config_path=config_path,
    )

    assert result.db_path == tmp_path / ".nutcracker" / "memory.db"
    assert result.db_path.is_file()
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == ".nutcracker/\n"
    with sqlite3.connect(result.db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"episodes", "anchors", "episode_embeddings"} <= tables
    assert calls[-1][1:4] == ["mcp", "add", result.mcp_name]

    assert ensure_gitignore(tmp_path) is False
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8").count(".nutcracker/") == 1


def test_agents_policy_is_created_and_preserves_existing_content(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text("# Existing project instruction\nKeep this text.\n", encoding="utf-8")

    assert install_agents_policy(tmp_path) is True
    content = path.read_text(encoding="utf-8")

    assert "# Existing project instruction" in content
    assert content.count(AGENTS_START) == 1
    assert content.count(AGENTS_END) == 1
    assert install_agents_policy(tmp_path) is False


@pytest.mark.parametrize("line_ending", ["\n", "\r\n"])
def test_agents_policy_preserves_existing_newline_style(tmp_path: Path, line_ending: str) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_bytes(f"before{line_ending}".encode("utf-8"))

    install_agents_policy(tmp_path)

    content = path.read_bytes().decode("utf-8")
    assert line_ending in content
    assert "\r\n" not in content if line_ending == "\n" else True


def test_gitignore_preserves_crlf_and_adds_missing_final_newline(tmp_path: Path) -> None:
    path = tmp_path / ".gitignore"
    path.write_bytes(b"existing-rule")

    assert ensure_gitignore(tmp_path) is True

    assert path.read_bytes() == b"existing-rule\r\n.nutcracker/\r\n" if os.linesep == "\r\n" else b"existing-rule\n.nutcracker/\n"


def test_gitignore_preserves_existing_crlf(tmp_path: Path) -> None:
    path = tmp_path / ".gitignore"
    path.write_bytes(b"existing-rule\r\n")

    ensure_gitignore(tmp_path)

    assert path.read_bytes() == b"existing-rule\r\n.nutcracker/\r\n"


def test_agents_policy_replaces_only_managed_block(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text(
        f"before\n{AGENTS_START}\nold policy\n{AGENTS_END}\nafter\n",
        encoding="utf-8",
    )

    assert install_agents_policy(tmp_path) is True
    content = path.read_text(encoding="utf-8")

    assert "before" in content
    assert "after" in content
    assert "old policy" not in content
    assert content.count(AGENTS_START) == content.count(AGENTS_END) == 1


def test_agents_policy_fails_without_destroying_malformed_file(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    original = f"safe user text\n{AGENTS_START}\n"
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="unmatched"):
        install_agents_policy(tmp_path)

    assert path.read_text(encoding="utf-8") == original


def test_init_is_idempotent_when_mcp_registration_matches(
    tmp_path: Path,
    codex_available: None,
) -> None:
    calls: list[list[str]] = []
    config_path = tmp_path / "codex" / "config.toml"
    _write_mcp_config(config_path, tmp_path)

    result = initialize_repository(
        tmp_path,
        runner=_successful_runner(calls),
        python_executable="python-for-test",
        config_path=config_path,
    )

    assert result.mcp_changed is False
    assert not any(call[1:3] == ["mcp", "add"] for call in calls)
    assert initialize_repository(
        tmp_path,
        runner=_successful_runner([]),
        python_executable="python-for-test",
        config_path=config_path,
    ).agents_changed is False


def test_init_works_with_paths_containing_spaces(
    tmp_path: Path,
    codex_available: None,
) -> None:
    repo = tmp_path / "My Project With Spaces"
    repo.mkdir()
    calls: list[list[str]] = []

    result = initialize_repository(
        repo,
        runner=_successful_runner(calls),
        python_executable="/a path/python",
        config_path=tmp_path / "config.toml",
    )

    command = calls[-1]
    assert f"NUTCRACKER_REPO_ROOT={repo.resolve()}" in command
    assert "/a path/python" in command
    assert result.db_path.is_file()


def test_mcp_command_generation_is_shell_and_platform_independent(tmp_path: Path) -> None:
    command = build_mcp_add_command(
        tmp_path / "project with spaces",
        python_executable="/opt/Nutcracker Python/bin/python",
        codex_executable="codex",
    )

    assert command[:4] == ["codex", "mcp", "add", mcp_server_name(tmp_path / "project with spaces")]
    assert command[-2:] == ["-m", "mcp_server.server"]
    assert all("powershell" not in item.lower() and "shell=True" not in item for item in command)


def test_mcp_names_are_deterministic_and_distinguish_same_basenames(tmp_path: Path) -> None:
    first = tmp_path / "one" / "project"
    second = tmp_path / "two" / "project"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    assert mcp_server_name(first) == mcp_server_name(first)
    assert mcp_server_name(first) != mcp_server_name(second)


def test_mcp_name_limits_an_extremely_long_slug(tmp_path: Path) -> None:
    repo = tmp_path / ("project-" * 100)

    name = mcp_server_name(repo)

    assert len(name) <= len("nutcracker-") + 48 + 1 + 8
    expected_hash = hashlib.sha256(str(repo.resolve()).encode("utf-8")).hexdigest()[:8]
    assert name.endswith(f"-{expected_hash}")


def _configured_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".nutcracker").mkdir()
    database = repo / ".nutcracker" / "memory.db"
    from storage.episode_store import init_db

    init_db(str(database))
    install_agents_policy(repo)
    return repo, database


def test_doctor_reports_valid_configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _ = _configured_repo(tmp_path)
    config_path = tmp_path / "codex" / "config.toml"
    _write_mcp_config(config_path, repo, command=sys.executable)
    monkeypatch.setattr("nutcracker_cli.onboarding.shutil.which", lambda name: "/usr/bin/codex")
    monkeypatch.setattr("nutcracker_cli.onboarding.detect_repo_root", lambda cwd: detect_repo_root(repo, runner=_git_runner))

    result = run_doctor(repo, config_path=config_path, probe_runner=_successful_probe)

    assert result.ready is True
    assert all(ok for _, ok, _ in result.checks)


def test_doctor_reports_missing_mcp_registration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _ = _configured_repo(tmp_path)
    monkeypatch.setattr("nutcracker_cli.onboarding.shutil.which", lambda name: "/usr/bin/codex")
    monkeypatch.setattr("nutcracker_cli.onboarding.detect_repo_root", lambda cwd: detect_repo_root(repo, runner=_git_runner))

    result = run_doctor(repo, config_path=tmp_path / "absent.toml")

    registration = next(check for check in result.checks if check[0] == "MCP registration")
    assert registration[1] is False
    assert result.ready is False


@pytest.mark.parametrize(
    "managed_content",
    ["", "old policy", "This is not the packaged Nutcracker policy."],
)
def test_doctor_rejects_empty_or_outdated_agents_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    managed_content: str,
) -> None:
    repo, _ = _configured_repo(tmp_path)
    (repo / "AGENTS.md").write_text(
        f"{AGENTS_START}\n{managed_content}\n{AGENTS_END}\n", encoding="utf-8"
    )
    monkeypatch.setattr("nutcracker_cli.onboarding.shutil.which", lambda name: "/usr/bin/codex")
    monkeypatch.setattr("nutcracker_cli.onboarding.detect_repo_root", lambda cwd: detect_repo_root(repo, runner=_git_runner))

    result = run_doctor(repo, config_path=tmp_path / "absent.toml")

    policy = next(check for check in result.checks if check[0] == "AGENTS.md policy")
    assert policy[1] is False
    assert "outdated" in policy[2]


def test_doctor_rejects_inconsistent_agents_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _ = _configured_repo(tmp_path)
    (repo / "AGENTS.md").write_text(f"{AGENTS_START}\n", encoding="utf-8")
    monkeypatch.setattr("nutcracker_cli.onboarding.shutil.which", lambda name: "/usr/bin/codex")
    monkeypatch.setattr("nutcracker_cli.onboarding.detect_repo_root", lambda cwd: detect_repo_root(repo, runner=_git_runner))

    result = run_doctor(repo, config_path=tmp_path / "absent.toml")

    policy = next(check for check in result.checks if check[0] == "AGENTS.md policy")
    assert policy[1] is False


def test_doctor_rejects_disabled_mcp_and_external_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _ = _configured_repo(tmp_path)
    config_path = tmp_path / "codex" / "config.toml"
    _write_mcp_config(
        config_path,
        repo,
        command=sys.executable,
        enabled="false",
        environment_lines=[f"NUTCRACKER_DB_PATH = {json.dumps(str(tmp_path / 'outside.db'))}"],
    )
    monkeypatch.setattr("nutcracker_cli.onboarding.shutil.which", lambda name: "/usr/bin/codex")
    monkeypatch.setattr("nutcracker_cli.onboarding.detect_repo_root", lambda cwd: detect_repo_root(repo, runner=_git_runner))

    result = run_doctor(repo, config_path=config_path, probe_runner=_successful_probe)

    registration = next(check for check in result.checks if check[0] == "MCP registration")
    assert registration[1] is False
    assert "disabled" in registration[2]
    assert "database" in registration[2]


@pytest.mark.parametrize(
    ("probe_runner", "expected"),
    [
        (_successful_probe, True),
        (lambda arguments, timeout: (_ for _ in ()).throw(FileNotFoundError()), False),
        (lambda arguments, timeout: _completed(arguments, stderr="broken", returncode=1), False),
        (lambda arguments, timeout: (_ for _ in ()).throw(subprocess.TimeoutExpired(arguments, timeout)), False),
    ],
)
def test_doctor_probes_registered_mcp_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    probe_runner,
    expected: bool,
) -> None:
    repo, _ = _configured_repo(tmp_path)
    config_path = tmp_path / "codex" / "config.toml"
    _write_mcp_config(config_path, repo, command=sys.executable)
    monkeypatch.setattr("nutcracker_cli.onboarding.shutil.which", lambda name: "/usr/bin/codex")
    monkeypatch.setattr("nutcracker_cli.onboarding.detect_repo_root", lambda cwd: detect_repo_root(repo, runner=_git_runner))

    result = run_doctor(repo, config_path=config_path, probe_runner=probe_runner)

    process = next(check for check in result.checks if check[0] == "MCP server process and tools")
    assert process[1] is expected


def test_init_aborts_on_conflicting_mcp_without_mutating_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "codex" / "config.toml"
    _write_mcp_config(config_path, tmp_path, command="different-python")
    monkeypatch.setattr("nutcracker_cli.onboarding.shutil.which", lambda name: "/usr/bin/codex")
    calls: list[list[str]] = []

    with pytest.raises(MCPConflictError, match="Existing MCP registration differs"):
        initialize_repository(
            tmp_path,
            runner=_successful_runner(calls),
            python_executable="python-for-test",
            config_path=config_path,
        )

    assert not (tmp_path / ".nutcracker").exists()
    assert not (tmp_path / ".gitignore").exists()
    assert not (tmp_path / "AGENTS.md").exists()
    assert not any(call[1:3] in (["mcp", "add"], ["mcp", "remove"]) for call in calls)


def test_init_preflight_failure_does_not_modify_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nutcracker_cli.onboarding.shutil.which", lambda name: None)

    with pytest.raises(CodexPreflightError, match="No project files were changed"):
        initialize_repository(tmp_path, runner=_successful_runner([]), config_path=tmp_path / "config.toml")

    assert not (tmp_path / ".nutcracker").exists()
    assert not (tmp_path / ".gitignore").exists()
    assert not (tmp_path / "AGENTS.md").exists()


@pytest.mark.parametrize("failed_command", [["/usr/bin/codex", "--version"], ["/usr/bin/codex", "mcp", "--help"]])
def test_init_preflight_command_failure_does_not_modify_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_command: list[str],
) -> None:
    def failing_preflight(arguments: list[str], cwd: Path | None) -> subprocess.CompletedProcess[str]:
        if arguments == failed_command:
            return _completed(arguments, returncode=1)
        if arguments[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return _completed(arguments, f"{cwd}\n")
        return _completed(arguments)

    monkeypatch.setattr("nutcracker_cli.onboarding.shutil.which", lambda name: "/usr/bin/codex")
    with pytest.raises(CodexPreflightError, match="No project files were changed"):
        initialize_repository(tmp_path, runner=failing_preflight, config_path=tmp_path / "config.toml")

    assert not (tmp_path / ".nutcracker").exists()
    assert not (tmp_path / ".gitignore").exists()
    assert not (tmp_path / "AGENTS.md").exists()


def test_init_reports_registration_failure_after_preserving_local_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def failing_add(arguments: list[str], cwd: Path | None) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        if arguments[1:3] == ["mcp", "add"]:
            return _completed(arguments, stderr="permission denied", returncode=1)
        if arguments[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return _completed(arguments, f"{cwd}\n")
        return _completed(arguments)

    monkeypatch.setattr("nutcracker_cli.onboarding.shutil.which", lambda name: "/usr/bin/codex")
    with pytest.raises(MCPRegistrationError, match="permission denied"):
        initialize_repository(
            tmp_path,
            runner=failing_add,
            python_executable="python-for-test",
            config_path=tmp_path / "config.toml",
        )

    assert (tmp_path / ".nutcracker" / "memory.db").is_file()
    assert ".nutcracker/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert AGENTS_START in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert any(command[1:3] == ["mcp", "add"] for command in calls)


def test_read_codex_config_rejects_invalid_toml(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("this is not = [valid", encoding="utf-8")

    with pytest.raises(ValueError, match="Cannot read Codex configuration"):
        _read_codex_config(config)
