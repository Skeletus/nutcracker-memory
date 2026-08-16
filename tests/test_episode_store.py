import sqlite3
from pathlib import Path

from memory_engine.episode import (
    Anchor,
    AnchorLevel,
    AnchorRelation,
    Episode,
    EpisodeType,
)
from storage.episode_store import (
    find_episode_ids_for_symbol,
    get_episode,
    init_db,
    save_episode,
)


def _anchor(
    symbol: str,
    level: AnchorLevel,
    relation: AnchorRelation,
) -> Anchor:
    return Anchor(
        symbol=symbol,
        content_hash=f"hash:{symbol}",
        level=level,
        relation=relation,
    )


def _episode(summary: str = "Persist an episode") -> Episode:
    return Episode(
        type=EpisodeType.DECISION,
        summary=summary,
        anchors=[
            _anchor(
                "src/package.py",
                AnchorLevel.STRUCTURAL,
                AnchorRelation.PRIMARY,
            ),
            _anchor(
                "src/service.py",
                AnchorLevel.REGIONAL,
                AnchorRelation.MODIFIED,
            ),
            _anchor(
                "tests/test_service.py",
                AnchorLevel.VALIDATION,
                AnchorRelation.VALIDATION,
            ),
        ],
    )


def test_init_db_is_idempotent_and_creates_both_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"

    init_db(str(db_path))
    init_db(str(db_path))

    with sqlite3.connect(db_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"episodes", "anchors"}.issubset(table_names)


def test_save_and_get_episode_round_trip_preserves_episode(tmp_path: Path) -> None:
    db_path = str(tmp_path / "memory.db")
    init_db(db_path)
    original = _episode()

    save_episode(db_path, original)
    restored = get_episode(db_path, original.id)

    assert restored is not None
    assert restored.id == original.id
    assert restored.summary == original.summary
    assert len(restored.anchors) == len(original.anchors)
    assert restored.anchors == original.anchors


def test_get_episode_returns_none_for_unknown_id(tmp_path: Path) -> None:
    db_path = str(tmp_path / "memory.db")
    init_db(db_path)

    assert get_episode(db_path, "E-does-not-exist") is None


def test_save_episode_persists_one_row_per_anchor(tmp_path: Path) -> None:
    db_path = str(tmp_path / "memory.db")
    init_db(db_path)
    episode = _episode()

    save_episode(db_path, episode)

    with sqlite3.connect(db_path) as connection:
        anchor_count = connection.execute(
            "SELECT COUNT(*) FROM anchors WHERE episode_id = ?",
            (episode.id,),
        ).fetchone()[0]
    assert anchor_count == 3


def test_find_episode_ids_for_symbol_returns_all_matching_episodes(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "memory.db")
    init_db(db_path)
    first = _episode("First decision")
    second = _episode("Second decision")
    save_episode(db_path, first)
    save_episode(db_path, second)

    episode_ids = find_episode_ids_for_symbol(db_path, "src/package.py")

    assert episode_ids == sorted([first.id, second.id])


def test_find_episode_ids_for_symbol_returns_empty_list_when_absent(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "memory.db")
    init_db(db_path)
    save_episode(db_path, _episode())

    assert find_episode_ids_for_symbol(db_path, "src/unknown.py") == []


def test_save_episode_upsert_replaces_data_and_anchor_rows(tmp_path: Path) -> None:
    db_path = str(tmp_path / "memory.db")
    init_db(db_path)
    original = _episode("Original summary")
    save_episode(db_path, original)
    updated = original.model_copy(
        update={
            "summary": "Updated summary",
            "anchors": original.anchors[:2],
        }
    )

    save_episode(db_path, updated)
    restored = get_episode(db_path, original.id)

    assert restored is not None
    assert restored.summary == "Updated summary"
    assert restored.anchors == original.anchors[:2]
    with sqlite3.connect(db_path) as connection:
        anchor_count = connection.execute(
            "SELECT COUNT(*) FROM anchors WHERE episode_id = ?",
            (original.id,),
        ).fetchone()[0]
    assert anchor_count == 2
