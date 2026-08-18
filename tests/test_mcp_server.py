import asyncio
import inspect
import json
import sqlite3
from pathlib import Path

import pytest

import memory_engine.core as core
import mcp_server.server as server_module
from memory_engine.episode import AnchorLevel, AnchorRelation, EpisodeType
from mcp_server.server import (
    ServerConfig,
    configure_server,
    handle_memory_recall,
    handle_memory_save,
    load_config,
    mcp,
    memory_recall_tool,
    memory_save_tool,
)
from storage.episode_store import get_episode
from storage.vector_store import save_episode_embedding


@pytest.fixture(autouse=True)
def _use_fake_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep adapter tests deterministic and independent of model downloads."""

    monkeypatch.setattr(core, "embed_text", lambda text: [1.0, 0.0])


def _config(tmp_path: Path) -> ServerConfig:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    return load_config({"NUTCRACKER_REPO_ROOT": str(repo_root)})


def _save(config: ServerConfig, path: str = "auth.py") -> dict[str, object]:
    (config.repo_root / path).write_text("AUTH = True\n", encoding="utf-8")
    return handle_memory_save(
        config,
        summary="Refresh token rotation belongs to the authentication session layer.",
        primary_path=path,
    )


def _write_files(config: ServerConfig, *paths: str) -> None:
    for relative in paths:
        target = config.repo_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {relative}\n", encoding="utf-8")


def _memory_save_schema() -> dict[str, object]:
    tools = asyncio.run(mcp.list_tools())
    return next(tool.inputSchema for tool in tools if tool.name == "memory_save")


def _episode_count(config: ServerConfig) -> int:
    with sqlite3.connect(config.db_path) as connection:
        return connection.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]


def test_valid_startup_configuration_initializes_default_database(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    config = load_config({"NUTCRACKER_REPO_ROOT": str(repo_root)})

    assert config.repo_root == repo_root.resolve()
    assert config.db_path == (repo_root / ".nutcracker" / "memory.db").resolve()
    assert config.db_path.is_file()
    with sqlite3.connect(config.db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"episodes", "anchors", "episode_embeddings"} <= tables


def test_startup_configuration_rejects_nonexistent_repository(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "does-not-exist"

    with pytest.raises(ValueError, match="not an existing directory"):
        load_config({"NUTCRACKER_REPO_ROOT": str(missing)})


def test_server_registers_exactly_two_expected_tools() -> None:
    tools = asyncio.run(mcp.list_tools())

    assert [tool.name for tool in tools] == ["memory_save", "memory_recall"]
    assert {tool.name: tool.description for tool in tools} == {
        "memory_save": (
            "Persist a durable repository episode after reaching a non-obvious "
            "architectural decision, resolving a substantive bug, rejecting an "
            "approach, or discovering a reusable convention. Call this proactively "
            "once the conclusion is supported, even when the user did not request "
            "persistence, and anchor it to the relevant files. Do not store routine "
            "edits, formatting or typo fixes, transient progress, or facts obvious "
            "from the current code. Anchors must be repository-relative paths to "
            "existing whole files."
        ),
        "memory_recall": (
            "Consult persistent repository history before analyzing or changing an "
            "area when prior architectural decisions, investigated bugs, failed "
            "approaches, or conventions could affect the task. Call this proactively "
            "even when the user did not ask for history. Do not call it for trivial, "
            "self-contained edits or when current code alone fully answers the task. "
            "Results report semantic relevance and current structural validity."
        ),
    }


def test_memory_save_adapter_persists_episode(tmp_path: Path) -> None:
    config = _config(tmp_path)

    result = _save(config)

    assert result["status"] == "saved"
    assert result["anchors"] == [
        {
            "symbol": "auth.py",
            "state": "valid",
            "relation": "primary",
            "level": "local",
        }
    ]
    assert _episode_count(config) == 1


def test_memory_save_tool_returns_compact_text_and_structured_content(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.repo_root / "auth.py").write_text("AUTH = True\n", encoding="utf-8")
    configure_server({"NUTCRACKER_REPO_ROOT": str(config.repo_root)})

    result = memory_save_tool(
        summary="Refresh token rotation belongs to the authentication session layer.",
        primary_path="auth.py",
    )

    assert result.structuredContent is not None
    assert result.structuredContent["status"] == "saved"
    assert result.content[0].text.startswith("Nutcracker · Memory saved\nEpisode E")
    assert "anchors" in result.content[0].text


def test_memory_recall_adapter_returns_found(tmp_path: Path) -> None:
    config = _config(tmp_path)
    saved = _save(config)

    response = handle_memory_recall(config, "authentication refresh token session")

    assert response["status"] == "found"
    assert response["results"][0]["episode_id"] == saved["episode_id"]
    assert response["results"][0]["structurally_valid"] is True


def test_memory_recall_adapter_returns_fallback_required_after_drift(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    saved = _save(config)
    (config.repo_root / "auth.py").write_text("AUTH = False\n", encoding="utf-8")

    response = handle_memory_recall(config, "authentication refresh token session")

    assert response["status"] == "fallback_required"
    assert response["results"][0]["episode_id"] == saved["episode_id"]
    assert response["results"][0]["anchors"] == [
        {"symbol": "auth.py", "state": "changed"}
    ]


def test_memory_recall_adapter_returns_no_match(tmp_path: Path) -> None:
    config = _config(tmp_path)
    saved = _save(config)
    save_episode_embedding(
        str(config.db_path),
        saved["episode_id"],
        [0.0, 1.0],
        "controlled-test-model",
    )

    response = handle_memory_recall(
        config,
        "unrelated query",
        min_similarity=0.5,
    )

    assert response == {"status": "no_match", "results": []}


@pytest.mark.parametrize(
    ("drift", "query", "expected"),
    [
        (False, "authentication refresh token session", "Nutcracker · Memory recalled\nFOUND · integrity 100%"),
        (True, "authentication refresh token session", "Nutcracker · Memory may be stale\nFALLBACK_REQUIRED · integrity 0%\n\nauth.py · CHANGED"),
        (False, "unrelated query", "Nutcracker · No relevant memory\nNO_MATCH"),
    ],
)
def test_memory_recall_tool_returns_compact_text_with_structured_content(
    tmp_path: Path,
    drift: bool,
    query: str,
    expected: str,
) -> None:
    config = _config(tmp_path)
    saved = _save(config)
    if drift:
        (config.repo_root / "auth.py").write_text("AUTH = False\n", encoding="utf-8")
    if query == "unrelated query":
        save_episode_embedding(str(config.db_path), saved["episode_id"], [0.0, 1.0], "controlled-test-model")
    configure_server({"NUTCRACKER_REPO_ROOT": str(config.repo_root)})

    result = memory_recall_tool(query=query, min_similarity=0.5 if query == "unrelated query" else 0.0)

    assert result.structuredContent is not None
    assert result.content[0].text.startswith(expected)


def test_memory_save_real_schema_is_flat_and_path_only() -> None:
    schema = _memory_save_schema()
    properties = schema["properties"]
    related = properties["related_paths"]
    related_array = next(
        branch for branch in related["anyOf"] if branch.get("type") == "array"
    )

    assert properties["primary_path"]["type"] == "string"
    assert "primary_path" in schema["required"]
    assert "repository-relative path" in properties["primary_path"]["description"].lower()
    assert "whole-file level" in properties["primary_path"]["description"].lower()
    assert related_array["items"] == {"type": "string"}
    assert "related_paths" not in schema["required"]
    assert "repository-relative paths" in properties["related_paths"]["description"].lower()
    assert "primary_anchor" not in properties
    assert "related_anchors" not in properties
    assert "level" not in properties
    assert "relation" not in properties
    assert "symbol" not in properties


def test_memory_save_adapter_rejects_missing_anchor_without_partial_episode(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)

    with pytest.raises(ValueError) as error:
        handle_memory_save(
            config,
            summary="Missing input",
            primary_path="AppContext",
        )

    message = str(error.value)
    assert 'Invalid anchor path: "AppContext".' in message
    assert "existing file relative to the repository root" in message
    assert "whole-file level, not individual code symbols" in message
    assert _episode_count(config) == 0


def test_tool_responses_never_expose_embeddings(tmp_path: Path) -> None:
    config = _config(tmp_path)
    saved = _save(config)
    recalled = handle_memory_recall(config, "authentication session")

    assert "embedding" not in json.dumps(saved).lower()
    assert "embedding" not in json.dumps(recalled).lower()


def test_memory_save_adapter_rejects_path_traversal_even_when_target_exists(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    outside = tmp_path / "secret.txt"
    outside.write_text("not repository memory\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid anchor path"):
        handle_memory_save(
            config,
            summary="Traversal attempt",
            primary_path="../secret.txt",
        )

    assert _episode_count(config) == 0


def test_server_does_not_print_directly_to_protocol_stdout() -> None:
    assert "print(" not in inspect.getsource(server_module)


def test_save_and_recall_translate_new_api_to_unchanged_episode(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_files(config, "auth.py", "sessions.py", "test_auth.py")

    saved = handle_memory_save(
        config,
        summary="Authentication responsibilities stay separated.",
        primary_path="auth.py",
        related_paths=["sessions.py", "test_auth.py"],
        type="decision",
    )
    persisted = get_episode(str(config.db_path), saved["episode_id"])
    recalled = handle_memory_recall(config, "authentication responsibilities")

    assert persisted is not None
    assert [anchor.symbol for anchor in persisted.anchors] == [
        "auth.py",
        "sessions.py",
        "test_auth.py",
    ]
    assert [anchor.relation for anchor in persisted.anchors] == [
        AnchorRelation.PRIMARY,
        AnchorRelation.DEPENDENCY,
        AnchorRelation.DEPENDENCY,
    ]
    assert recalled["status"] == "found"
    assert recalled["results"][0]["episode_id"] == saved["episode_id"]


def test_first_flask_attempt_succeeds_with_architectural_decision_alias(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    paths = ("src/flask/ctx.py", "src/flask/app.py", "src/flask/globals.py")
    _write_files(config, *paths)
    configure_server({"NUTCRACKER_REPO_ROOT": str(config.repo_root)})

    result = memory_save_tool(
        summary=(
            "Flask maintains a semantic boundary between application and "
            "request context."
        ),
        primary_path=paths[0],
        related_paths=list(paths[1:]),
        type="architectural_decision",
    )
    persisted = get_episode(
        str(config.db_path),
        result.structuredContent["episode_id"],
    )

    assert persisted is not None
    assert persisted.type == EpisodeType.DECISION
    assert result.structuredContent["stored_type"] == "decision"
    assert result.structuredContent["type_fallback"] is False


def test_memory_save_omitted_type_defaults_to_observation(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_files(config, "note.py")

    saved = handle_memory_save(config, summary="A durable note.", primary_path="note.py")
    persisted = get_episode(str(config.db_path), saved["episode_id"])

    assert persisted is not None
    assert persisted.type == EpisodeType.OBSERVATION


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        ("architectural_decision", EpisodeType.DECISION),
        ("bugfix", EpisodeType.BUG_FIX),
        ("failed_attempt", EpisodeType.FAILED_APPROACH),
        ("note", EpisodeType.OBSERVATION),
    ],
)
def test_memory_save_normalizes_known_type_aliases(
    tmp_path: Path,
    requested: str,
    expected: EpisodeType,
) -> None:
    config = _config(tmp_path)
    _write_files(config, "memory.py")

    saved = handle_memory_save(
        config,
        summary=f"Episode for {requested}.",
        primary_path="memory.py",
        type=f"  {requested.upper()}  ",
    )
    persisted = get_episode(str(config.db_path), saved["episode_id"])

    assert persisted is not None
    assert persisted.type == expected
    assert saved["type_fallback"] is False


def test_unknown_type_falls_back_with_structured_diagnostics(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_files(config, "memory.py")
    configure_server({"NUTCRACKER_REPO_ROOT": str(config.repo_root)})

    result = memory_save_tool(
        summary="Unknown caller vocabulary must not block persistence.",
        primary_path="memory.py",
        type="random_garbage",
    )
    persisted = get_episode(
        str(config.db_path),
        result.structuredContent["episode_id"],
    )

    assert persisted is not None
    assert persisted.type == EpisodeType.OBSERVATION
    assert result.structuredContent["requested_type"] == "random_garbage"
    assert result.structuredContent["stored_type"] == "observation"
    assert result.structuredContent["type_fallback"] is True
    assert "Memory saved\nEpisode E" in result.content[0].text


def test_adapter_assigns_internal_anchor_defaults(tmp_path: Path) -> None:
    config = _config(tmp_path)
    paths = ("src/flask/ctx.py", "src/flask/app.py", "src/flask/globals.py")
    _write_files(config, *paths)

    saved = handle_memory_save(
        config,
        summary="File anchors use adapter defaults.",
        primary_path=paths[0],
        related_paths=list(paths[1:]),
    )
    persisted = get_episode(str(config.db_path), saved["episode_id"])

    assert persisted is not None
    assert [anchor.level for anchor in persisted.anchors] == [AnchorLevel.LOCAL] * 3
    assert [anchor.relation for anchor in persisted.anchors] == [
        AnchorRelation.PRIMARY,
        AnchorRelation.DEPENDENCY,
        AnchorRelation.DEPENDENCY,
    ]


def test_related_paths_are_deduplicated_in_first_seen_order(tmp_path: Path) -> None:
    config = _config(tmp_path)
    paths = ("src/flask/ctx.py", "src/flask/app.py", "src/flask/globals.py")
    _write_files(config, *paths)

    saved = handle_memory_save(
        config,
        summary="Duplicate paths collapse.",
        primary_path=paths[0],
        related_paths=[paths[1], paths[1], paths[2]],
    )
    persisted = get_episode(str(config.db_path), saved["episode_id"])

    assert persisted is not None
    assert [anchor.symbol for anchor in persisted.anchors] == list(paths)


def test_primary_path_is_removed_from_related_paths(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_files(config, "src/flask/ctx.py", "src/flask/app.py")

    saved = handle_memory_save(
        config,
        summary="Primary remains unique.",
        primary_path="src/flask/ctx.py",
        related_paths=["src/flask/ctx.py", "src/flask/app.py"],
    )
    persisted = get_episode(str(config.db_path), saved["episode_id"])

    assert persisted is not None
    assert [(anchor.symbol, anchor.relation) for anchor in persisted.anchors] == [
        ("src/flask/ctx.py", AnchorRelation.PRIMARY),
        ("src/flask/app.py", AnchorRelation.DEPENDENCY),
    ]


def test_missing_related_path_uses_actionable_whole_file_error(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_files(config, "src/flask/ctx.py")

    with pytest.raises(ValueError) as error:
        handle_memory_save(
            config,
            summary="Missing related path.",
            primary_path="src/flask/ctx.py",
            related_paths=["AppContext"],
        )

    assert 'Invalid anchor path: "AppContext".' in str(error.value)
    assert "whole-file level, not individual code symbols" in str(error.value)


def test_historical_persisted_episode_is_recalled_by_new_mcp_tool(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.repo_root / "legacy.py").write_text("LEGACY = True\n", encoding="utf-8")
    historical = core.memory_save(
        repo_root=str(config.repo_root),
        db_path=str(config.db_path),
        summary="Historical episode using the unchanged persisted representation.",
        anchor_specs=[
            (
                "legacy.py",
                AnchorLevel.STRUCTURAL,
                AnchorRelation.PRIMARY,
            )
        ],
        type=EpisodeType.OBSERVATION,
    )
    configure_server({"NUTCRACKER_REPO_ROOT": str(config.repo_root)})

    result = memory_recall_tool(query="historical persisted representation")

    assert result.structuredContent is not None
    assert result.structuredContent["status"] == "found"
    assert result.structuredContent["results"][0]["episode_id"] == historical.id
