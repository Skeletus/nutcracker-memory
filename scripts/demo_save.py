"""Save and reload one real Nutcracker Memory episode from SQLite."""

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

# Direct execution sets sys.path to scripts/, so add the repository root before
# importing the project packages. This keeps `python scripts/demo_save.py`
# usable without requiring the project to be installed as a wheel.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from memory_engine.core import memory_save
from memory_engine.episode import AnchorLevel, AnchorRelation, EpisodeType
from storage.episode_store import get_episode, init_db


def main() -> None:
    """Persist a representative architectural decision and print a summary."""

    data_directory = REPO_ROOT / ".nutcracker"
    data_directory.mkdir(exist_ok=True)
    db_path = data_directory / "memory.db"
    init_db(str(db_path))

    episode = memory_save(
        repo_root=str(REPO_ROOT),
        db_path=str(db_path),
        summary=(
            "EpisodeState was separated from Episode content so the structural "
            "validity of a memory can change independently from the episode's "
            "historical content."
        ),
        anchor_specs=[
            (
                "memory_engine/episode.py",
                AnchorLevel.STRUCTURAL,
                AnchorRelation.PRIMARY,
            )
        ],
        type=EpisodeType.DECISION,
        decision="Keep EpisodeState as a separate model.",
    )
    reloaded = get_episode(str(db_path), episode.id)
    primary = episode.primary_anchor()

    print(f"Saved episode: {episode.id}")
    print(f"Anchors: {len(episode.anchors)}")
    print(f"Primary: {primary.symbol if primary is not None else 'none'}")
    print(f"Reloaded from SQLite: {'yes' if reloaded == episode else 'no'}")
    print(f"Database path: {db_path}")


if __name__ == "__main__":
    main()
