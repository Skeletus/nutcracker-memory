"""Episode creation and semantic recall adjusted by current anchor integrity.

This MVP orchestration accepts repository-relative file paths, verifies their
current contents, constructs a structurally anchored episode, and persists its
summary embedding. Recall keeps semantic similarity as its relevance signal and
multiplies it by equal-weight, file-level anchor survival. No graph, temporal,
memory-strength, or relationship weighting is applied.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from memory_engine.anchor_resolver import compute_symbol_hash, resolve_all_anchors
from memory_engine.episode import (
    Anchor,
    AnchorLevel,
    AnchorRelation,
    AnchorState,
    Episode,
    EpisodeType,
)
from storage.episode_store import get_episode, save_episode
from storage.vector_store import (
    EMBEDDING_MODEL,
    embed_text,
    get_all_episode_embeddings,
    save_episode_embedding,
)


@dataclass(frozen=True, slots=True)
class RecallResult:
    """Current semantic and structural interpretation of a stored episode."""

    episode: Episode
    semantic_similarity: float
    anchor_integrity: float
    score: float
    structurally_valid: bool
    anchor_states: list[Anchor]

    @property
    def similarity(self) -> float:
        """Preserve the Phase-5 name as a semantic-similarity alias."""

        return self.semantic_similarity


class RecallStatus(str, Enum):
    """High-level outcome of semantic retrieval plus structural evaluation."""

    FOUND = "found"
    FALLBACK_REQUIRED = "fallback_required"
    NO_MATCH = "no_match"


@dataclass(frozen=True, slots=True)
class RecallResponse:
    """Recall candidates together with an explicit trust/fallback signal."""

    status: RecallStatus
    results: list[RecallResult]


def memory_save(
    repo_root: str,
    db_path: str,
    summary: str,
    anchor_specs: list[tuple[str, AnchorLevel, AnchorRelation]],
    type: EpisodeType = EpisodeType.OBSERVATION,
    observations: list[str] | None = None,
    decision: str | None = None,
) -> Episode:
    """Build, validate, and persist a new episode with explicit file anchors.

    In this MVP, each ``symbol`` in ``anchor_specs`` is exclusively a file path
    relative to ``repo_root``. All files are resolved before the episode is
    constructed or persisted, so a missing file propagates
    ``SymbolNotFoundError`` without leaving a partial database record.
    """

    if not anchor_specs:
        raise ValueError("memory_save requires at least one anchor")

    primary_count = sum(
        relation == AnchorRelation.PRIMARY
        for _, _, relation in anchor_specs
    )
    if primary_count > 1:
        raise ValueError("memory_save accepts at most one PRIMARY anchor")

    root = Path(repo_root).resolve()
    verified_at = datetime.now(UTC)
    anchors: list[Anchor] = []

    for symbol, level, relation in anchor_specs:
        filepath = root / symbol
        content_hash = compute_symbol_hash(str(filepath), symbol)
        anchors.append(
            Anchor(
                symbol=symbol,
                content_hash=content_hash,
                level=level,
                relation=relation,
                state=AnchorState.VALID,
                last_verified_at=verified_at,
            )
        )

    episode = Episode(
        type=type,
        summary=summary,
        anchors=anchors,
        observations=list(observations) if observations is not None else [],
        decision=decision,
    )
    save_episode(db_path, episode)

    # Episode persistence and embedding persistence are separate MVP steps. If
    # encoding fails, the exception propagates and the Episode may temporarily
    # remain stored without an embedding; automatic repair is a later concern.
    embedding = embed_text(episode.summary)
    save_episode_embedding(db_path, episode.id, embedding, EMBEDDING_MODEL)
    return episode


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return cosine similarity for equal-length normalized or raw vectors."""

    if len(a) != len(b):
        raise ValueError("cosine similarity requires vectors of equal length")
    if not a:
        return 0.0

    dot_product = sum(left * right for left, right in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(value * value for value in a))
    norm_b = math.sqrt(sum(value * value for value in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    similarity = dot_product / (norm_a * norm_b)
    return max(-1.0, min(1.0, similarity))


def memory_recall(
    repo_root: str,
    db_path: str,
    query: str,
    limit: int = 5,
    min_similarity: float = 0.0,
) -> RecallResponse:
    """Rank semantically relevant episodes by current anchor integrity.

    ``min_similarity`` filters semantic similarity before drift resolution.
    Resolved anchor copies describe the current repository without mutating the
    historical Episode. Episodes without embeddings cannot participate.
    """

    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("memory_recall requires a non-empty query")
    if limit <= 0:
        raise ValueError("memory_recall requires limit greater than zero")
    if not -1.0 <= min_similarity <= 1.0:
        raise ValueError("min_similarity must be between -1.0 and 1.0")

    query_embedding = embed_text(normalized_query)
    results: list[RecallResult] = []

    for stored in get_all_episode_embeddings(db_path):
        episode = get_episode(db_path, stored.episode_id)
        if episode is None:
            continue

        semantic_similarity = cosine_similarity(query_embedding, stored.embedding)
        if semantic_similarity < min_similarity:
            continue

        anchor_states = resolve_all_anchors(episode.anchors, repo_root)
        total_anchors = len(anchor_states)
        valid_anchors = sum(
            anchor.state == AnchorState.VALID for anchor in anchor_states
        )
        anchor_integrity = (
            valid_anchors / total_anchors if total_anchors > 0 else 0.0
        )
        structurally_valid = total_anchors > 0 and valid_anchors == total_anchors
        score = semantic_similarity * anchor_integrity
        results.append(
            RecallResult(
                episode=episode,
                semantic_similarity=semantic_similarity,
                anchor_integrity=anchor_integrity,
                score=score,
                structurally_valid=structurally_valid,
                anchor_states=anchor_states,
            )
        )

    if not results:
        status = RecallStatus.NO_MATCH
    elif any(result.structurally_valid for result in results):
        status = RecallStatus.FOUND
    else:
        status = RecallStatus.FALLBACK_REQUIRED

    results.sort(
        key=lambda result: (
            -result.score,
            -result.semantic_similarity,
            result.episode.id,
        )
    )
    return RecallResponse(status=status, results=results[:limit])
