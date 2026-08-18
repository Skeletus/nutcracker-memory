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
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from memory_engine.anchor_resolver import SymbolNotFoundError
from memory_engine.core import memory_recall as core_memory_recall
from memory_engine.core import memory_save as core_memory_save
from memory_engine.episode import AnchorLevel, AnchorRelation, EpisodeType
from storage.episode_store import init_db


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """Validated process-level paths shared by both MCP tools."""

    repo_root: Path
    db_path: Path


EPISODE_TYPE_ALIASES = {
    "architectural_decision": EpisodeType.DECISION.value,
    "architecture_decision": EpisodeType.DECISION.value,
    "bugfix": EpisodeType.BUG_FIX.value,
    "fix": EpisodeType.BUG_FIX.value,
    "failed_attempt": EpisodeType.FAILED_APPROACH.value,
    "note": EpisodeType.OBSERVATION.value,
}


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


def _invalid_anchor_path(path: str) -> ValueError:
    """Return an actionable public error for an invalid whole-file anchor."""

    return ValueError(
        f'Invalid anchor path: "{path}".\n\n'
        "The path must reference an existing file relative to the repository "
        "root. Nutcracker MVP tracks anchors at whole-file level, not individual "
        "code symbols. If you mean a class or function, anchor the file containing it."
    )


def _validate_anchor_path(repo_root: Path, path: str) -> None:
    """Reject absolute paths and any relative path escaping ``repo_root``.

    ``Path.resolve`` follows existing symlinks, so this check also rejects a
    repository-local symlink whose target is outside the configured tree.
    """

    candidate = Path(path)
    if candidate.is_absolute():
        raise _invalid_anchor_path(path)

    resolved = (repo_root / candidate).resolve()
    if not resolved.is_relative_to(repo_root):
        raise _invalid_anchor_path(path)
    if not resolved.is_file():
        raise _invalid_anchor_path(path)


def _normalize_episode_type(requested_type: str) -> tuple[EpisodeType, bool]:
    """Return a canonical EpisodeType and whether an unknown value fell back."""

    normalized = requested_type.strip().lower()
    canonical = EPISODE_TYPE_ALIASES.get(normalized, normalized)
    try:
        return EpisodeType(canonical), False
    except ValueError:
        return EpisodeType.OBSERVATION, True


def _normalize_related_paths(
    primary_path: str,
    related_paths: list[str],
) -> list[str]:
    """Remove primary and duplicate related paths while preserving first order."""

    seen = {primary_path}
    normalized: list[str] = []
    for path in related_paths:
        if path not in seen:
            seen.add(path)
            normalized.append(path)
    return normalized


def _build_anchor_specs(
    primary_path: str,
    related_paths: list[str],
) -> list[tuple[str, AnchorLevel, AnchorRelation]]:
    """Translate the MCP-only shape to the engine's unchanged anchor tuples."""

    # LOCAL is a placeholder, not an inferred hierarchy; level does not yet
    # affect recall or scoring and can be inferred more meaningfully later.
    # DEPENDENCY is the neutral related-anchor default, not an inferred code
    # dependency; relation likewise does not yet affect recall or scoring.
    return [
        (
            primary_path,
            AnchorLevel.LOCAL,
            AnchorRelation.PRIMARY,
        ),
        *[
            (
                path,
                AnchorLevel.LOCAL,
                AnchorRelation.DEPENDENCY,
            )
            for path in related_paths
        ],
    ]


def handle_memory_save(
    config: ServerConfig,
    summary: str,
    primary_path: str,
    related_paths: list[str] | None = None,
    type: str = EpisodeType.OBSERVATION.value,
    observations: list[str] | None = None,
    decision: str | None = None,
) -> dict[str, Any]:
    """Validate MCP input, delegate to core ``memory_save``, and compact output."""

    related = _normalize_related_paths(primary_path, related_paths or [])
    public_paths = [primary_path, *related]
    for path in public_paths:
        _validate_anchor_path(config.repo_root, path)

    episode_type, type_fallback = _normalize_episode_type(type)
    anchor_specs = _build_anchor_specs(primary_path, related)

    try:
        episode = core_memory_save(
            repo_root=str(config.repo_root),
            db_path=str(config.db_path),
            summary=summary,
            anchor_specs=anchor_specs,
            type=episode_type,
            observations=list(observations or []),
            decision=decision,
        )
    except SymbolNotFoundError as error:
        # Return only the repository-relative input, not a host absolute path.
        missing_symbol = next(
            (
                path
                for path in public_paths
                if (config.repo_root / path).resolve()
                == Path(error.filepath).resolve()
            ),
            "requested anchor",
        )
        raise _invalid_anchor_path(missing_symbol) from None

    return {
        "status": "saved",
        "episode_id": episode.id,
        "summary": episode.summary,
        "requested_type": type,
        "stored_type": episode.type.value,
        "type_fallback": type_fallback,
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


def _compact_save_content(result: Mapping[str, Any]) -> str:
    """Return the small human-facing summary while retaining structured data."""

    return (
        "Nutcracker · Memory saved\n"
        f"Episode {result['episode_id']} · {len(result['anchors'])} anchors"
    )


def _compact_recall_content(result: Mapping[str, Any]) -> str:
    """Return a bounded human summary for the recall status and best result."""

    status = result["status"]
    memories = result["results"]
    if status == "no_match":
        return "Nutcracker · No relevant memory\nNO_MATCH"

    best = memories[0]
    integrity = f"{best['anchor_integrity']:.0%}"
    if status == "found":
        return (
            "Nutcracker · Memory recalled\n"
            f"FOUND · integrity {integrity}\n"
            f"{len(memories)} memories · best score {best['score']:.2f}"
        )

    anchors = best["anchors"]
    visible = anchors[:3]
    anchor_lines = [f"{anchor['symbol']} · {anchor['state'].upper()}" for anchor in visible]
    if len(anchors) > len(visible):
        anchor_lines.append(f"+{len(anchors) - len(visible)} more")
    return (
        "Nutcracker · Memory may be stale\n"
        f"FALLBACK_REQUIRED · integrity {integrity}\n\n"
        + "\n".join(anchor_lines)
    )


def _tool_result(text: str, structured: dict[str, Any]) -> CallToolResult:
    """Build official MCP content plus structured content without stdio prints."""

    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=structured,
    )


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
        "Anchors are repository-relative paths to whole files."
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
        "from the current code. Anchors must be repository-relative paths to "
        "existing whole files."
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
    summary: Annotated[
        str,
        Field(description="Concise durable technical conclusion to remember."),
    ],
    primary_path: Annotated[
        str,
        Field(
            description=(
                "Repository-relative path to the primary existing file supporting "
                "this memory. Nutcracker MVP anchors at whole-file level."
            )
        ),
    ],
    related_paths: Annotated[
        list[str] | None,
        Field(
            description=(
                "Optional repository-relative paths to additional existing files "
                "supporting this memory. Nutcracker MVP anchors at whole-file level."
            )
        ),
    ] = None,
    type: Annotated[
        str,
        Field(
            description=(
                "Optional episode category. Common aliases are normalized and "
                "unknown values safely fall back to observation."
            )
        ),
    ] = EpisodeType.OBSERVATION.value,
    observations: Annotated[
        list[str] | None,
        Field(description="Optional supporting facts behind the conclusion."),
    ] = None,
    decision: str | None = None,
) -> CallToolResult:
    """Save an Episode using explicit repository-relative file anchors."""

    result = handle_memory_save(
        _require_config(),
        summary=summary,
        primary_path=primary_path,
        related_paths=related_paths,
        type=type,
        observations=observations,
        decision=decision,
    )
    return _tool_result(_compact_save_content(result), result)


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
) -> CallToolResult:
    """Recall memories from the repository configured at server startup."""

    result = handle_memory_recall(
        _require_config(),
        query=query,
        limit=limit,
        min_similarity=min_similarity,
    )
    return _tool_result(_compact_recall_content(result), result)


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
