import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

import memory_engine.core as core
from mcp_server.server import (
    AnchorInput,
    ServerConfig,
    handle_memory_recall,
    handle_memory_save,
    load_config,
    mcp,
)
from storage.vector_store import save_episode_embedding


@pytest.fixture(autouse=True)
def _use_fake_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep adapter tests deterministic and independent of model downloads."""

    monkeypatch.setattr(core, "embed_text", lambda text: [1.0, 0.0])


def _config(tmp_path: Path) -> ServerConfig:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    return load_config({"NUTCRACKER_REPO_ROOT": str(repo_root)})


def _anchor(symbol: str = "auth.py", relation: str = "primary") -> AnchorInput:
    return AnchorInput(symbol=symbol, level="structural", relation=relation)


def _save(config: ServerConfig, symbol: str = "auth.py") -> dict[str, object]:
    (config.repo_root / symbol).write_text("AUTH = True\n", encoding="utf-8")
    return handle_memory_save(
        config,
        summary="Refresh token rotation belongs to the authentication session layer.",
        anchors=[_anchor(symbol)],
    )


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
            "from the current code."
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
            "level": "structural",
        }
    ]
    assert _episode_count(config) == 1


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


def test_memory_save_adapter_rejects_invalid_enum_without_persisting(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    (config.repo_root / "auth.py").write_text("AUTH = True\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid anchor relation 'banana'"):
        handle_memory_save(
            config,
            summary="Invalid input",
            anchors=[_anchor(relation="banana")],
        )

    assert _episode_count(config) == 0


def test_memory_save_adapter_rejects_missing_anchor_without_partial_episode(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)

    with pytest.raises(ValueError, match="does_not_exist.py"):
        handle_memory_save(
            config,
            summary="Missing input",
            anchors=[_anchor("does_not_exist.py")],
        )

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

    with pytest.raises(ValueError, match="within the configured repository"):
        handle_memory_save(
            config,
            summary="Traversal attempt",
            anchors=[_anchor("../secret.txt")],
        )

    assert _episode_count(config) == 0
