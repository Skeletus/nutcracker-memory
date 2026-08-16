from pathlib import Path

import pytest

import memory_engine.core as core
from memory_engine.episode import (
    AnchorLevel,
    AnchorRelation,
    AnchorState,
    Episode,
    EpisodeType,
)
from storage.episode_store import get_episode, init_db, save_episode
from storage.vector_store import save_episode_embedding


@pytest.fixture(autouse=True)
def _use_fake_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use a deterministic semantic vector while testing structural drift."""

    monkeypatch.setattr(core, "embed_text", lambda text: [1.0, 0.0])


def _context(tmp_path: Path) -> tuple[Path, str]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    db_path = str(tmp_path / "memory.db")
    init_db(db_path)
    return repo_root, db_path


def _write_files(repo_root: Path, *symbols: str) -> None:
    for index, symbol in enumerate(symbols, start=1):
        path = repo_root / symbol
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"VALUE = {index}\n", encoding="utf-8")


def _save_memory(
    repo_root: Path,
    db_path: str,
    summary: str,
    symbols: list[str],
) -> Episode:
    return core.memory_save(
        repo_root=str(repo_root),
        db_path=db_path,
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
    )


def _recall_episode(
    repo_root: Path,
    db_path: str,
    episode_id: str,
    min_similarity: float = 0.0,
) -> core.RecallResult:
    response = core.memory_recall(
        str(repo_root),
        db_path,
        "controlled query",
        limit=20,
        min_similarity=min_similarity,
    )
    return next(
        result
        for result in response.results
        if result.episode.id == episode_id
    )


def test_recall_reports_full_integrity_when_all_anchors_are_valid(
    tmp_path: Path,
) -> None:
    repo_root, db_path = _context(tmp_path)
    _write_files(repo_root, "one.py", "two.py")
    episode = _save_memory(repo_root, db_path, "All anchors survive", ["one.py", "two.py"])

    result = _recall_episode(repo_root, db_path, episode.id)

    assert result.anchor_integrity == pytest.approx(1.0)
    assert result.structurally_valid is True
    assert result.score == pytest.approx(result.semantic_similarity)
    assert all(anchor.state == AnchorState.VALID for anchor in result.anchor_states)


def test_recall_reports_half_integrity_when_one_anchor_changed(
    tmp_path: Path,
) -> None:
    repo_root, db_path = _context(tmp_path)
    _write_files(repo_root, "stable.py", "changed.py")
    episode = _save_memory(
        repo_root,
        db_path,
        "One anchor changes",
        ["stable.py", "changed.py"],
    )
    (repo_root / "changed.py").write_text("VALUE = 'changed'\n", encoding="utf-8")

    result = _recall_episode(repo_root, db_path, episode.id)

    assert [anchor.state for anchor in result.anchor_states] == [
        AnchorState.VALID,
        AnchorState.CHANGED,
    ]
    assert result.anchor_integrity == pytest.approx(0.5)
    assert result.structurally_valid is False
    assert result.score == pytest.approx(result.semantic_similarity * 0.5)


def test_recall_reports_half_integrity_when_one_anchor_is_missing(
    tmp_path: Path,
) -> None:
    repo_root, db_path = _context(tmp_path)
    _write_files(repo_root, "stable.py", "missing.py")
    episode = _save_memory(
        repo_root,
        db_path,
        "One anchor disappears",
        ["stable.py", "missing.py"],
    )
    (repo_root / "missing.py").unlink()

    result = _recall_episode(repo_root, db_path, episode.id)

    assert [anchor.state for anchor in result.anchor_states] == [
        AnchorState.VALID,
        AnchorState.MISSING,
    ]
    assert result.anchor_integrity == pytest.approx(0.5)


def test_recall_reports_zero_integrity_when_no_anchor_survives(
    tmp_path: Path,
) -> None:
    repo_root, db_path = _context(tmp_path)
    _write_files(repo_root, "changed.py", "missing.py")
    episode = _save_memory(
        repo_root,
        db_path,
        "No anchors survive",
        ["changed.py", "missing.py"],
    )
    (repo_root / "changed.py").write_text("CHANGED = True\n", encoding="utf-8")
    (repo_root / "missing.py").unlink()

    result = _recall_episode(repo_root, db_path, episode.id)

    assert result.anchor_integrity == pytest.approx(0.0)
    assert result.score == pytest.approx(0.0)
    assert result.structurally_valid is False


def test_semantic_similarity_is_unchanged_when_anchor_drifts(
    tmp_path: Path,
) -> None:
    repo_root, db_path = _context(tmp_path)
    _write_files(repo_root, "module.py")
    episode = _save_memory(repo_root, db_path, "Semantic content is stable", ["module.py"])
    before = _recall_episode(repo_root, db_path, episode.id)
    (repo_root / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    after = _recall_episode(repo_root, db_path, episode.id)

    assert after.semantic_similarity == pytest.approx(before.semantic_similarity)
    assert before.score > after.score


def test_drift_changes_ranking_by_final_score(tmp_path: Path) -> None:
    repo_root, db_path = _context(tmp_path)
    _write_files(repo_root, "drifted.py", "stable.py")
    drifted = _save_memory(repo_root, db_path, "High semantic match", ["drifted.py"])
    stable = _save_memory(repo_root, db_path, "Lower semantic match", ["stable.py"])
    save_episode_embedding(db_path, drifted.id, [0.9, 0.4358899], "test-model")
    save_episode_embedding(db_path, stable.id, [0.7, 0.7141428], "test-model")
    (repo_root / "drifted.py").write_text("DRIFTED = True\n", encoding="utf-8")

    response = core.memory_recall(str(repo_root), db_path, "controlled query")
    results = response.results

    assert results[0].episode.id == stable.id
    drifted_result = next(
        result for result in results if result.episode.id == drifted.id
    )
    assert drifted_result.semantic_similarity == pytest.approx(0.9, abs=1e-6)
    assert drifted_result.score == pytest.approx(0.0)


def test_partially_drifted_memory_remains_in_results(tmp_path: Path) -> None:
    repo_root, db_path = _context(tmp_path)
    _write_files(repo_root, "stable.py", "changed.py")
    episode = _save_memory(
        repo_root,
        db_path,
        "Partially drifted but retrievable",
        ["stable.py", "changed.py"],
    )
    (repo_root / "changed.py").write_text("CHANGED = True\n", encoding="utf-8")

    result = _recall_episode(repo_root, db_path, episode.id)

    assert result.anchor_integrity == pytest.approx(0.5)
    recalled_ids = {
        recalled.episode.id
        for recalled in core.memory_recall(
            str(repo_root),
            db_path,
            "controlled query",
        ).results
    }
    assert episode.id in recalled_ids


def test_episode_without_anchors_has_zero_integrity(tmp_path: Path) -> None:
    repo_root, db_path = _context(tmp_path)
    episode = Episode(type=EpisodeType.OBSERVATION, summary="Legacy unanchored memory")
    save_episode(db_path, episode)
    save_episode_embedding(db_path, episode.id, [1.0, 0.0], "test-model")

    result = _recall_episode(repo_root, db_path, episode.id)

    assert result.anchor_integrity == pytest.approx(0.0)
    assert result.structurally_valid is False
    assert result.score == pytest.approx(0.0)


def test_min_similarity_filters_semantic_signal_not_final_score(
    tmp_path: Path,
) -> None:
    repo_root, db_path = _context(tmp_path)
    symbols = [f"anchor_{index}.py" for index in range(10)]
    _write_files(repo_root, *symbols)
    episode = _save_memory(repo_root, db_path, "Low integrity semantic match", symbols)
    save_episode_embedding(db_path, episode.id, [0.8, 0.6], "test-model")
    for symbol in symbols[1:]:
        (repo_root / symbol).write_text("DRIFTED = True\n", encoding="utf-8")

    result = _recall_episode(
        repo_root,
        db_path,
        episode.id,
        min_similarity=0.7,
    )

    assert result.semantic_similarity == pytest.approx(0.8)
    assert result.anchor_integrity == pytest.approx(0.1)
    assert result.score == pytest.approx(0.08)


def test_recall_does_not_persist_current_drift_states(tmp_path: Path) -> None:
    repo_root, db_path = _context(tmp_path)
    _write_files(repo_root, "module.py")
    episode = _save_memory(repo_root, db_path, "Historical anchor state", ["module.py"])
    original_anchor = episode.anchors[0].model_copy(deep=True)
    (repo_root / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    result = _recall_episode(repo_root, db_path, episode.id)
    stored = get_episode(db_path, episode.id)

    assert result.anchor_states[0].state == AnchorState.CHANGED
    assert stored is not None
    assert stored.anchors[0] == original_anchor
    assert stored.anchors[0].state == AnchorState.VALID
