"""Demonstrate semantic recall before and after deterministic file drift."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from memory_engine.core import RecallResponse, memory_recall, memory_save
from memory_engine.episode import AnchorLevel, AnchorRelation, EpisodeType
from storage.episode_store import init_db


def _print_results(title: str, response: RecallResponse) -> None:
    print(title)
    print(f"STATUS: {response.status.value.upper()}")
    print()
    for position, result in enumerate(response.results, start=1):
        print(
            f"{position}. score={result.score:.4f} "
            f"semantic={result.semantic_similarity:.4f} "
            f"integrity={result.anchor_integrity:.2f} "
            f"valid={result.structurally_valid}"
        )
        print(f"   {result.episode.summary}")
        print("   anchors:")
        for anchor in result.anchor_states:
            print(f"     {anchor.symbol:<12} {anchor.state.value.upper()}")
    print()


def main() -> None:
    """Show that file drift changes integrity and score, not semantics."""

    with TemporaryDirectory(prefix="nutcracker-drift-") as temporary_directory:
        repo_root = Path(temporary_directory)
        (repo_root / "auth.py").write_text("AUTH = True\n", encoding="utf-8")
        (repo_root / "session.py").write_text("SESSION = True\n", encoding="utf-8")
        (repo_root / "database.py").write_text("DATABASE = 'sqlite'\n", encoding="utf-8")
        db_path = repo_root / "memory.db"
        init_db(str(db_path))

        memories = [
            (
                "Refresh token expiration was caused by session persistence "
                "rather than JWT generation.",
                ["auth.py", "session.py"],
            ),
            (
                "SQLite was selected as the persistence layer for the "
                "Nutcracker MVP.",
                ["database.py"],
            ),
            (
                "Authentication uses the session repository to rotate refresh tokens.",
                ["auth.py"],
            ),
        ]
        for summary, symbols in memories:
            memory_save(
                repo_root=str(repo_root),
                db_path=str(db_path),
                summary=summary,
                anchor_specs=[
                    (
                        symbol,
                        AnchorLevel.LOCAL,
                        (
                            AnchorRelation.PRIMARY
                            if index == 0
                            else AnchorRelation.DEPENDENCY
                        ),
                    )
                    for index, symbol in enumerate(symbols)
                ],
                type=EpisodeType.OBSERVATION,
            )

        query = "authentication session and refresh token bug"
        before = memory_recall(str(repo_root), str(db_path), query, limit=3)
        _print_results("BEFORE DRIFT", before)

        (repo_root / "session.py").write_text(
            "SESSION = 'modified after memory creation'\n",
            encoding="utf-8",
        )
        after = memory_recall(str(repo_root), str(db_path), query, limit=3)
        _print_results("AFTER MODIFYING session.py", after)


if __name__ == "__main__":
    main()
