import sqlite3
import struct
from datetime import UTC, datetime
from pathlib import Path

import pytest

import memory_engine.core as core
from memory_engine.anchor_resolver import compute_symbol_hash
from memory_engine.episode import (
    Anchor,
    AnchorLevel,
    AnchorRelation,
    AnchorState,
    Episode,
    EpisodeType,
)
from storage.episode_store import init_db, save_episode
from storage.vector_store import (
    EMBEDDING_MODEL,
    get_episode_embedding,
    save_episode_embedding,
)


@pytest.fixture(autouse=True)
def _use_fake_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent unit tests from downloading or initializing the real model."""

    monkeypatch.setattr(core, "embed_text", lambda text: [1.0, 0.0])


def _initialized_context(tmp_path: Path) -> tuple[Path, str]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "anchor.py").write_text("VALUE = 1\n", encoding="utf-8")
    db_path = str(tmp_path / "memory.db")
    init_db(db_path)
    return repo_root, db_path


def _episode(summary: str, repo_root: Path) -> Episode:
    symbol = "anchor.py"
    content_hash = compute_symbol_hash(str(repo_root / symbol), symbol)
    return Episode(
        type=EpisodeType.OBSERVATION,
        summary=summary,
        anchors=[
            Anchor(
                symbol=symbol,
                content_hash=content_hash,
                level=AnchorLevel.LOCAL,
                relation=AnchorRelation.DEPENDENCY,
                state=AnchorState.VALID,
            )
        ],
    )


def _save_with_embedding(
    db_path: str,
    repo_root: Path,
    summary: str,
    embedding: list[float],
) -> Episode:
    episode = _episode(summary, repo_root)
    save_episode(db_path, episode)
    save_episode_embedding(db_path, episode.id, embedding, "controlled-test-model")
    return episode


def test_memory_save_persists_summary_embedding(tmp_path: Path) -> None:
    repo_root, db_path = _initialized_context(tmp_path)

    episode = core.memory_save(
        repo_root=str(repo_root),
        db_path=db_path,
        summary="Persist this summary embedding.",
        anchor_specs=[
            (
                "anchor.py",
                AnchorLevel.LOCAL,
                AnchorRelation.PRIMARY,
            )
        ],
    )

    embedding = get_episode_embedding(db_path, episode.id)
    assert embedding is not None
    assert len(embedding) > 0


def test_embedding_float32_round_trip(tmp_path: Path) -> None:
    repo_root, db_path = _initialized_context(tmp_path)
    episode = _episode("Known vector", repo_root)
    save_episode(db_path, episode)

    save_episode_embedding(
        db_path,
        episode.id,
        [0.1, 0.2, 0.3],
        EMBEDDING_MODEL,
    )

    restored = get_episode_embedding(db_path, episode.id)
    assert restored == pytest.approx([0.1, 0.2, 0.3], abs=1e-7)


def test_cosine_similarity_for_aligned_orthogonal_and_opposite_vectors() -> None:
    assert core.cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert core.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert core.cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_memory_recall_ranks_most_similar_episode_first(tmp_path: Path) -> None:
    repo_root, db_path = _initialized_context(tmp_path)
    best = _save_with_embedding(db_path, repo_root, "Best match", [1.0, 0.0])
    _save_with_embedding(db_path, repo_root, "Second match", [0.8, 0.6])
    _save_with_embedding(db_path, repo_root, "Weak match", [0.0, 1.0])

    response = core.memory_recall(str(repo_root), db_path, "controlled query")
    results = response.results

    assert results[0].episode.id == best.id
    assert results[0].semantic_similarity == pytest.approx(1.0)


def test_memory_recall_respects_limit(tmp_path: Path) -> None:
    repo_root, db_path = _initialized_context(tmp_path)
    _save_with_embedding(db_path, repo_root, "First", [1.0, 0.0])
    _save_with_embedding(db_path, repo_root, "Second", [0.8, 0.6])
    _save_with_embedding(db_path, repo_root, "Third", [0.6, 0.8])

    response = core.memory_recall(
        str(repo_root),
        db_path,
        "controlled query",
        limit=2,
    )

    assert len(response.results) == 2


def test_memory_recall_applies_min_similarity(tmp_path: Path) -> None:
    repo_root, db_path = _initialized_context(tmp_path)
    accepted = _save_with_embedding(
        db_path,
        repo_root,
        "Accepted",
        [0.8, 0.6],
    )
    _save_with_embedding(db_path, repo_root, "Rejected", [0.0, 1.0])

    response = core.memory_recall(
        str(repo_root),
        db_path,
        "controlled query",
        min_similarity=0.5,
    )

    assert [result.episode.id for result in response.results] == [accepted.id]


def test_memory_recall_rejects_blank_query(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-empty query"):
        core.memory_recall(str(tmp_path), str(tmp_path / "unused.db"), "   ")


def test_memory_recall_rejects_non_positive_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="limit greater than zero"):
        core.memory_recall(
            str(tmp_path),
            str(tmp_path / "unused.db"),
            "query",
            limit=0,
        )


@pytest.mark.parametrize("min_similarity", [-1.01, 1.01])
def test_memory_recall_rejects_similarity_outside_valid_range(
    tmp_path: Path,
    min_similarity: float,
) -> None:
    with pytest.raises(ValueError, match="between -1.0 and 1.0"):
        core.memory_recall(
            str(tmp_path),
            str(tmp_path / "unused.db"),
            "query",
            min_similarity=min_similarity,
        )


def test_memory_recall_returns_empty_list_for_db_without_embeddings(
    tmp_path: Path,
) -> None:
    repo_root, db_path = _initialized_context(tmp_path)

    assert core.memory_recall(str(repo_root), db_path, "query").results == []


def test_memory_recall_ignores_episode_without_embedding(tmp_path: Path) -> None:
    repo_root, db_path = _initialized_context(tmp_path)
    save_episode(db_path, _episode("Legacy episode without embedding", repo_root))
    embedded = _save_with_embedding(
        db_path,
        repo_root,
        "Embedded episode",
        [1.0, 0.0],
    )

    response = core.memory_recall(str(repo_root), db_path, "query")

    assert [result.episode.id for result in response.results] == [embedded.id]


def test_memory_recall_ignores_orphaned_embedding(tmp_path: Path) -> None:
    repo_root, db_path = _initialized_context(tmp_path)
    orphan_blob = struct.pack("<2f", 1.0, 0.0)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO episode_embeddings (
                episode_id,
                embedding,
                model,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                "E-orphan",
                orphan_blob,
                "controlled-test-model",
                datetime.now(UTC).isoformat(),
            ),
        )

    assert core.memory_recall(str(repo_root), db_path, "query").results == []
