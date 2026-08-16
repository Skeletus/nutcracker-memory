"""Thin stdio MCP adapter for the Nutcracker memory engine.

The server exposes exactly two tools and delegates memory behavior to
``memory_engine.core``. Repository and database paths are process startup
configuration, never tool arguments. Standard output is reserved for MCP;
diagnostics use Python logging, which is configured on standard error.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from memory_engine.anchor_resolver import SymbolNotFoundError
from memory_engine.core import memory_recall as core_memory_recall
from memory_engine.core import memory_save as core_memory_save
from memory_engine.episode import AnchorLevel, AnchorRelation, EpisodeType
from storage.episode_store import init_db


LOGGER = logging.getLogger(__name__)
EnumT = TypeVar("EnumT", bound=Enum)


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """Validated process-level paths shared by both MCP tools."""

    repo_root: Path
    db_path: Path


class AnchorInput(BaseModel):
    """JSON-friendly anchor specification accepted by the save tool."""

    symbol: str
    level: str
    relation: str


def load_config(environment: Mapping[str, str] | None = None) -> ServerConfig:
    """Validate startup environment, create the DB directory, and init SQLite.

    A relative explicit database path is interpreted from the configured
    repository root so startup never depends on the process working directory.
    Existing databases are preserved because ``init_db`` is idempotent.
    """

    values = os.environ if environment is None else environment
    raw_repo_root = values.get("NUTCRACKER_REPO_ROOT", "").strip()
    if not raw_repo_root:
        raise ValueError("NUTCRACKER_REPO_ROOT is required")

    repo_root = Path(raw_repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        raise ValueError(
            f"NUTCRACKER_REPO_ROOT is not an existing directory: {repo_root}"
        )

    raw_db_path = values.get("NUTCRACKER_DB_PATH", "").strip()
    if raw_db_path:
        candidate = Path(raw_db_path).expanduser()
        db_path = candidate if candidate.is_absolute() else repo_root / candidate
    else:
        db_path = repo_root / ".nutcracker" / "memory.db"

    db_path = db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(str(db_path))
    return ServerConfig(repo_root=repo_root, db_path=db_path)


def _parse_enum(enum_type: type[EnumT], value: str, field_name: str) -> EnumT:
    """Convert one MCP string to an existing internal enum with a clear error."""

    try:
        return enum_type(value)
    except ValueError as error:
        allowed = ", ".join(member.value for member in enum_type)
        raise ValueError(
            f"Invalid {field_name} {value!r}; expected one of: {allowed}"
        ) from error


def _validate_anchor_path(repo_root: Path, symbol: str) -> None:
    """Reject absolute paths and any relative path escaping ``repo_root``.

    ``Path.resolve`` follows existing symlinks, so this check also rejects a
    repository-local symlink whose target is outside the configured tree.
    """

    candidate = Path(symbol)
    if candidate.is_absolute():
        raise ValueError("Anchor symbol must be a path relative to the repository")

    resolved = (repo_root / candidate).resolve()
    if not resolved.is_relative_to(repo_root):
        raise ValueError("Anchor symbol must remain within the configured repository")


def handle_memory_save(
    config: ServerConfig,
    summary: str,
    anchors: list[AnchorInput],
    type: str = EpisodeType.OBSERVATION.value,
    observations: list[str] | None = None,
    decision: str | None = None,
) -> dict[str, Any]:
    """Validate MCP input, delegate to core ``memory_save``, and compact output."""

    for anchor in anchors:
        _validate_anchor_path(config.repo_root, anchor.symbol)

    episode_type = _parse_enum(EpisodeType, type, "episode type")
    anchor_specs = [
        (
            anchor.symbol,
            _parse_enum(AnchorLevel, anchor.level, "anchor level"),
            _parse_enum(AnchorRelation, anchor.relation, "anchor relation"),
        )
        for anchor in anchors
    ]

    try:
        episode = core_memory_save(
            repo_root=str(config.repo_root),
            db_path=str(config.db_path),
            summary=summary,
            anchor_specs=anchor_specs,
            type=episode_type,
            observations=observations,
            decision=decision,
        )
    except SymbolNotFoundError as error:
        # Return only the repository-relative input, not a host absolute path.
        missing_symbol = next(
            (
                anchor.symbol
                for anchor in anchors
                if (config.repo_root / anchor.symbol).resolve()
                == Path(error.filepath).resolve()
            ),
            "requested anchor",
        )
        raise ValueError(f"Anchor file does not exist: {missing_symbol}") from None

    return {
        "status": "saved",
        "episode_id": episode.id,
        "summary": episode.summary,
        "anchors": [
            {
                "symbol": anchor.symbol,
                "state": anchor.state.value,
                "relation": anchor.relation.value,
                "level": anchor.level.value,
            }
            for anchor in episode.anchors
        ],
    }


def handle_memory_recall(
    config: ServerConfig,
    query: str,
    limit: int = 5,
    min_similarity: float = 0.0,
) -> dict[str, Any]:
    """Delegate to core ``memory_recall`` and return structured diagnostics."""

    response = core_memory_recall(
        repo_root=str(config.repo_root),
        db_path=str(config.db_path),
        query=query,
        limit=limit,
        min_similarity=min_similarity,
    )
    return {
        "status": response.status.value,
        "results": [
            {
                "episode_id": result.episode.id,
                "summary": result.episode.summary,
                "semantic_similarity": result.semantic_similarity,
                "anchor_integrity": result.anchor_integrity,
                "score": result.score,
                "structurally_valid": result.structurally_valid,
                "anchors": [
                    {
                        "symbol": anchor.symbol,
                        "state": anchor.state.value,
                    }
                    for anchor in result.anchor_states
                ],
            }
            for result in response.results
        ],
    }


_server_config: ServerConfig | None = None


def configure_server(environment: Mapping[str, str] | None = None) -> ServerConfig:
    """Load and retain startup configuration for decorated MCP tools."""

    global _server_config
    _server_config = load_config(environment)
    return _server_config


def _require_config() -> ServerConfig:
    if _server_config is None:
        raise RuntimeError("Nutcracker MCP server has not been configured")
    return _server_config


mcp = FastMCP(
    "nutcracker",
    instructions=(
        "Persistent episodic memory for the configured repository. "
        "Anchor symbols are repository-relative file paths."
    ),
    log_level="WARNING",
)


@mcp.tool(
    name="memory_save",
    description=(
        "Persist a durable repository episode after reaching a non-obvious "
        "architectural decision, resolving a substantive bug, rejecting an "
        "approach, or discovering a reusable convention. Call this proactively "
        "once the conclusion is supported, even when the user did not request "
        "persistence, and anchor it to the relevant files. Do not store routine "
        "edits, formatting or typo fixes, transient progress, or facts obvious "
        "from the current code."
    ),
    annotations=ToolAnnotations(
        title="Save Nutcracker memory",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    structured_output=True,
)
def memory_save_tool(
    summary: str,
    anchors: list[AnchorInput],
    type: str = EpisodeType.OBSERVATION.value,
    observations: list[str] | None = None,
    decision: str | None = None,
) -> dict[str, Any]:
    """Save an Episode using explicit repository-relative file anchors."""

    return handle_memory_save(
        _require_config(),
        summary=summary,
        anchors=anchors,
        type=type,
        observations=observations,
        decision=decision,
    )


@mcp.tool(
    name="memory_recall",
    description=(
        "Consult persistent repository history before analyzing or changing an "
        "area when prior architectural decisions, investigated bugs, failed "
        "approaches, or conventions could affect the task. Call this proactively "
        "even when the user did not ask for history. Do not call it for trivial, "
        "self-contained edits or when current code alone fully answers the task. "
        "Results report semantic relevance and current structural validity."
    ),
    annotations=ToolAnnotations(
        title="Recall Nutcracker memory",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    structured_output=True,
)
def memory_recall_tool(
    query: str,
    limit: int = 5,
    min_similarity: float = 0.0,
) -> dict[str, Any]:
    """Recall memories from the repository configured at server startup."""

    return handle_memory_recall(
        _require_config(),
        query=query,
        limit=limit,
        min_similarity=min_similarity,
    )


def main() -> None:
    """Validate configuration and run the MCP server over standard I/O."""

    logging.basicConfig(
        level=logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        configure_server()
    except (OSError, ValueError) as error:
        LOGGER.error("Nutcracker MCP startup failed: %s", error)
        raise SystemExit(2) from None

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
