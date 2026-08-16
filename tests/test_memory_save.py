import sqlite3
from pathlib import Path

import pytest

from memory_engine.anchor_resolver import SymbolNotFoundError
from memory_engine.core import memory_save
from memory_engine.episode import (
    AnchorLevel,
    AnchorRelation,
    AnchorState,
    EpisodeType,
)
from storage.episode_store import get_episode, init_db


@pytest.fixture(autouse=True)
def _use_fake_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep Phase 4 tests focused on save orchestration, not model loading."""

    monkeypatch.setattr(
        "memory_engine.core.embed_text",
        lambda text: [float(len(text)), 1.0],
    )


def _initialized_paths(tmp_path: Path) -> tuple[Path, str]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    db_path = str(tmp_path / "memory.db")
    init_db(db_path)
    return repo_root, db_path


def _episode_count(db_path: str) -> int:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT COUNT(*) FROM episodes").fetchone()
    assert row is not None
    return row[0]


def test_memory_save_with_multiple_valid_anchors(tmp_path: Path) -> None:
    repo_root, db_path = _initialized_paths(tmp_path)
    (repo_root / "module_a.py").write_text("VALUE_A = 1\n", encoding="utf-8")
    (repo_root / "module_b.py").write_text("VALUE_B = 2\n", encoding="utf-8")

    episode = memory_save(
        repo_root=str(repo_root),
        db_path=db_path,
        summary="Record the relationship between two modules.",
        anchor_specs=[
            (
                "module_a.py",
                AnchorLevel.STRUCTURAL,
                AnchorRelation.PRIMARY,
            ),
            (
                "module_b.py",
                AnchorLevel.LOCAL,
                AnchorRelation.DEPENDENCY,
            ),
        ],
    )

    assert len(episode.anchors) == 2
    assert all(anchor.state == AnchorState.VALID for anchor in episode.anchors)
    assert all(anchor.content_hash for anchor in episode.anchors)
    assert all(anchor.last_verified_at is not None for anchor in episode.anchors)
    assert sum(
        anchor.relation == AnchorRelation.PRIMARY for anchor in episode.anchors
    ) <= 1


def test_memory_save_round_trip_through_sqlite(tmp_path: Path) -> None:
    repo_root, db_path = _initialized_paths(tmp_path)
    (repo_root / "module.py").write_text("ENABLED = True\n", encoding="utf-8")

    episode = memory_save(
        repo_root=str(repo_root),
        db_path=db_path,
        summary="Persist a verified module observation.",
        anchor_specs=[
            (
                "module.py",
                AnchorLevel.REGIONAL,
                AnchorRelation.MODIFIED,
            )
        ],
        observations=["The module is enabled."],
    )

    loaded = get_episode(db_path, episode.id)

    assert loaded == episode


def test_memory_save_propagates_missing_anchor_without_persisting(
    tmp_path: Path,
) -> None:
    repo_root, db_path = _initialized_paths(tmp_path)

    with pytest.raises(SymbolNotFoundError):
        memory_save(
            repo_root=str(repo_root),
            db_path=db_path,
            summary="This memory must not be persisted.",
            anchor_specs=[
                (
                    "does_not_exist.py",
                    AnchorLevel.LOCAL,
                    AnchorRelation.PRIMARY,
                )
            ],
        )

    assert _episode_count(db_path) == 0


def test_memory_save_rejects_multiple_primary_anchors(tmp_path: Path) -> None:
    repo_root, db_path = _initialized_paths(tmp_path)
    (repo_root / "first.py").write_text("FIRST = 1\n", encoding="utf-8")
    (repo_root / "second.py").write_text("SECOND = 2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="at most one PRIMARY"):
        memory_save(
            repo_root=str(repo_root),
            db_path=db_path,
            summary="Ambiguous primary anchors.",
            anchor_specs=[
                (
                    "first.py",
                    AnchorLevel.STRUCTURAL,
                    AnchorRelation.PRIMARY,
                ),
                (
                    "second.py",
                    AnchorLevel.REGIONAL,
                    AnchorRelation.PRIMARY,
                ),
            ],
        )

    assert _episode_count(db_path) == 0


def test_memory_save_rejects_empty_anchor_specs(tmp_path: Path) -> None:
    repo_root, db_path = _initialized_paths(tmp_path)

    with pytest.raises(ValueError, match="requires at least one anchor"):
        memory_save(
            repo_root=str(repo_root),
            db_path=db_path,
            summary="An unanchored memory is invalid for this MVP flow.",
            anchor_specs=[],
        )

    assert _episode_count(db_path) == 0


def test_memory_save_allows_zero_primary_anchors(tmp_path: Path) -> None:
    repo_root, db_path = _initialized_paths(tmp_path)
    (repo_root / "module.py").write_text("VALUE = 1\n", encoding="utf-8")

    episode = memory_save(
        repo_root=str(repo_root),
        db_path=db_path,
        summary="A valid memory without a designated primary anchor.",
        anchor_specs=[
            (
                "module.py",
                AnchorLevel.LOCAL,
                AnchorRelation.DEPENDENCY,
            )
        ],
        type=EpisodeType.OBSERVATION,
    )

    assert episode.primary_anchor() is None
    assert get_episode(db_path, episode.id) == episode
