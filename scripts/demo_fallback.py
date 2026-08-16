"""Demonstrate FOUND, FALLBACK_REQUIRED, and NO_MATCH recall outcomes."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from memory_engine.core import RecallResponse, memory_recall, memory_save
from memory_engine.episode import AnchorLevel, AnchorRelation, EpisodeType
from storage.episode_store import init_db


def _print_response(title: str, response: RecallResponse) -> None:
    print(title)
    print(f"STATUS: {response.status.value.upper()}")
    for result in response.results:
        print(
            f"semantic={result.semantic_similarity:.4f} "
            f"integrity={result.anchor_integrity:.2f} "
            f"score={result.score:.4f} "
            f"valid={result.structurally_valid}"
        )
        print(f"  {result.episode.summary}")
        for anchor in result.anchor_states:
            print(f"  {anchor.symbol} {anchor.state.value.upper()}")
    print()


def main() -> None:
    """Run the three normal high-level recall outcomes with FastEmbed."""

    with TemporaryDirectory(prefix="nutcracker-fallback-") as temporary_directory:
        repo_root = Path(temporary_directory)
        auth_path = repo_root / "auth.py"
        auth_path.write_text("AUTH = True\n", encoding="utf-8")
        db_path = repo_root / "memory.db"
        init_db(str(db_path))

        memory_save(
            repo_root=str(repo_root),
            db_path=str(db_path),
            summary=(
                "Refresh token rotation is handled by the authentication "
                "session layer."
            ),
            anchor_specs=[
                (
                    "auth.py",
                    AnchorLevel.LOCAL,
                    AnchorRelation.PRIMARY,
                )
            ],
            type=EpisodeType.DECISION,
        )

        related_query = "authentication refresh token session"
        current = memory_recall(str(repo_root), str(db_path), related_query)
        _print_response("SCENARIO A — CURRENT MEMORY", current)

        auth_path.write_text("AUTH = 'changed after memory'\n", encoding="utf-8")
        drifted = memory_recall(str(repo_root), str(db_path), related_query)
        _print_response("SCENARIO B — AFTER STRUCTURAL DRIFT", drifted)

        unrelated = memory_recall(
            str(repo_root),
            str(db_path),
            "frontend CSS animation rendering",
            min_similarity=0.70,
        )
        _print_response("SCENARIO C — UNRELATED QUERY", unrelated)


if __name__ == "__main__":
    main()
