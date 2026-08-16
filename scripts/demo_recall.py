"""Demonstrate real FastEmbed summary ranking with a deterministic demo DB."""

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from memory_engine.core import memory_recall, memory_save
from memory_engine.episode import AnchorLevel, AnchorRelation, EpisodeType
from storage.episode_store import init_db


def main() -> None:
    """Encode three episodes and rank them for an authentication query."""

    data_directory = REPO_ROOT / ".nutcracker"
    data_directory.mkdir(exist_ok=True)
    db_path = data_directory / "demo_recall.db"
    db_path.unlink(missing_ok=True)
    init_db(str(db_path))

    summaries = [
        (
            "Refresh token expiration was caused by session persistence "
            "rather than JWT generation."
        ),
        "SQLite was selected as the persistence layer for the Nutcracker MVP.",
        (
            "EpisodeState was separated from historical episode content to "
            "track structural validity independently."
        ),
    ]
    for summary in summaries:
        memory_save(
            repo_root=str(REPO_ROOT),
            db_path=str(db_path),
            summary=summary,
            anchor_specs=[
                (
                    "memory_engine/episode.py",
                    AnchorLevel.STRUCTURAL,
                    AnchorRelation.PRIMARY,
                )
            ],
            type=EpisodeType.DECISION,
        )

    query = "authentication session and refresh token bug"
    response = memory_recall(
        repo_root=str(REPO_ROOT),
        db_path=str(db_path),
        query=query,
        limit=3,
    )

    print(f"Query: {query}")
    print(f"Status: {response.status.value}")
    print()
    for position, result in enumerate(response.results, start=1):
        print(
            f"{position}. {result.semantic_similarity:.4f}  "
            f"{result.episode.summary}"
        )


if __name__ == "__main__":
    main()
