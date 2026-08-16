"""FastEmbed encoding and SQLite persistence for episode summary vectors.

Vectors are serialized as little-endian IEEE 754 float32 values in a SQLite
BLOB. This compact representation is deterministic, reconstructs the original
stored float32 values exactly, and requires no external vector database.
"""

import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

from fastembed import TextEmbedding

from storage.episode_store import _connect


EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


@dataclass(frozen=True, slots=True)
class StoredEpisodeEmbedding:
    """One persisted episode vector and its encoding metadata."""

    episode_id: str
    embedding: list[float]
    model: str
    created_at: str


@lru_cache(maxsize=1)
def _embedding_model() -> TextEmbedding:
    """Initialize the FastEmbed model lazily and reuse it within the process."""

    return TextEmbedding(model_name=EMBEDDING_MODEL)


def embed_text(text: str) -> list[float]:
    """Generate one text embedding using the cached FastEmbed model."""

    vector = next(iter(_embedding_model().embed([text])))
    return [float(value) for value in vector]


def _serialize_embedding(embedding: list[float]) -> bytes:
    """Serialize numeric values as a little-endian float32 BLOB."""

    return struct.pack(f"<{len(embedding)}f", *embedding)


def _deserialize_embedding(blob: bytes) -> list[float]:
    """Reconstruct float32 values from a validated SQLite BLOB."""

    if len(blob) % 4 != 0:
        raise ValueError("Stored embedding BLOB length is not divisible by 4")
    dimension = len(blob) // 4
    return list(struct.unpack(f"<{dimension}f", blob))


def save_episode_embedding(
    db_path: str,
    episode_id: str,
    embedding: list[float],
    model: str,
) -> None:
    """Persist or replace the embedding associated with an episode."""

    blob = _serialize_embedding(embedding)
    created_at = datetime.now(UTC).isoformat()

    with _connect(db_path) as connection:
        with connection:
            connection.execute(
                """
                INSERT INTO episode_embeddings (
                    episode_id,
                    embedding,
                    model,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(episode_id) DO UPDATE SET
                    embedding = excluded.embedding,
                    model = excluded.model,
                    created_at = excluded.created_at
                """,
                (episode_id, blob, model, created_at),
            )


def get_episode_embedding(db_path: str, episode_id: str) -> list[float] | None:
    """Return one persisted episode embedding, or ``None`` when absent."""

    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT embedding
            FROM episode_embeddings
            WHERE episode_id = ?
            """,
            (episode_id,),
        ).fetchone()

    if row is None:
        return None
    return _deserialize_embedding(row[0])


def get_all_episode_embeddings(db_path: str) -> list[StoredEpisodeEmbedding]:
    """Return all persisted vectors needed for in-process semantic ranking."""

    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT episode_id, embedding, model, created_at
            FROM episode_embeddings
            ORDER BY episode_id
            """
        ).fetchall()

    return [
        StoredEpisodeEmbedding(
            episode_id=row[0],
            embedding=_deserialize_embedding(row[1]),
            model=row[2],
            created_at=row[3],
        )
        for row in rows
    ]
