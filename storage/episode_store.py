"""SQLite persistence for episodes and their queryable anchor projection.

The complete :class:`Episode` is stored as JSON in ``episodes``. Anchors are
also projected into a separate relational table because answering "which
episodes touch this symbol?" should be a direct indexed SQL query. Without
that table, every episode JSON document would need to be deserialized and
scanned. This is a relational lookup table, not a repository graph.

Public functions open and close one connection per operation. The API already
receives ``db_path`` rather than a live connection, and short-lived connections
avoid global lifecycle and thread-ownership problems in the MVP. If later
phases show connection setup to be material, a long-lived store object can be
introduced without changing the persisted schema.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from memory_engine.episode import Episode


_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS anchors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id TEXT NOT NULL REFERENCES episodes(id),
    symbol TEXT NOT NULL,
    content_hash TEXT,
    level TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_anchors_symbol ON anchors(symbol);

CREATE TABLE IF NOT EXISTS episode_embeddings (
    episode_id TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (episode_id) REFERENCES episodes(id)
);
"""


@contextmanager
def _connect(db_path: str) -> Iterator[sqlite3.Connection]:
    """Yield a configured connection and guarantee that it is closed."""

    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection
    finally:
        connection.close()


def init_db(db_path: str) -> None:
    """Create the episode schema if it does not already exist."""

    with _connect(db_path) as connection:
        with connection:
            connection.executescript(_SCHEMA)


def save_episode(db_path: str, episode: Episode) -> None:
    """Insert or atomically replace an episode and its anchor projection.

    ``ON CONFLICT`` handles both cases: a previously unseen id is inserted,
    while an existing id has its serialized data and timestamp updated. Anchor
    rows are deliberately deleted and reinserted in the same transaction to
    keep the projection simple and consistent with the episode JSON.
    """

    serialized = episode.model_dump_json()
    created_at = episode.provenance.created_at.isoformat()
    anchor_rows = [
        (
            episode.id,
            anchor.symbol,
            anchor.content_hash,
            anchor.level.value,
        )
        for anchor in episode.anchors
    ]

    with _connect(db_path) as connection:
        with connection:
            connection.execute(
                """
                INSERT INTO episodes (id, data, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    data = excluded.data,
                    created_at = excluded.created_at
                """,
                (episode.id, serialized, created_at),
            )
            connection.execute(
                "DELETE FROM anchors WHERE episode_id = ?",
                (episode.id,),
            )
            connection.executemany(
                """
                INSERT INTO anchors (episode_id, symbol, content_hash, level)
                VALUES (?, ?, ?, ?)
                """,
                anchor_rows,
            )


def get_episode(db_path: str, episode_id: str) -> Episode | None:
    """Return one deserialized episode, or ``None`` when its id is absent."""

    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT data FROM episodes WHERE id = ?",
            (episode_id,),
        ).fetchone()

    if row is None:
        return None
    return Episode.model_validate_json(row[0])


def find_episode_ids_for_symbol(db_path: str, symbol: str) -> list[str]:
    """Return distinct episode ids having an anchor for an exact symbol."""

    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT episode_id
            FROM anchors
            WHERE symbol = ?
            ORDER BY episode_id
            """,
            (symbol,),
        ).fetchall()

    return [row[0] for row in rows]
