from math import sqrt
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
    """Use a deterministic query/summary vector for fallback policy tests."""

    monkeypatch.setattr(core, "embed_text", lambda text: [1.0, 0.0])


def _context(tmp_path: Path) -> tuple[Path, str]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    db_path = str(tmp_path / "memory.db")
    init_db(db_path)
    return repo_root, db_path


def _write_files(repo_root: Path, symbols: list[str]) -> None:
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
    _write_files(repo_root, symbols)
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


def _recall(repo_root: Path, db_path: str, **kwargs: object) -> core.RecallResponse:
    return core.memory_recall(
        str(repo_root),
        db_path,
        "controlled query",
        **kwargs,
    )


def test_found_when_a_fully_valid_memory_exists(tmp_path: Path) -> None:
    repo_root, db_path = _context(tmp_path)
    _save_memory(repo_root, db_path, "Current memory", ["auth.py"])

    response = _recall(repo_root, db_path)

    assert response.status == core.RecallStatus.FOUND
    assert response.results[0].structurally_valid is True


def test_fallback_required_when_anchor_changed(tmp_path: Path) -> None:
    repo_root, db_path = _context(tmp_path)
    _save_memory(repo_root, db_path, "Changed memory", ["auth.py"])
    (repo_root / "auth.py").write_text("AUTH = 'changed'\n", encoding="utf-8")

    response = _recall(repo_root, db_path)

    assert response.status == core.RecallStatus.FALLBACK_REQUIRED
    assert len(response.results) > 0
    assert response.results[0].anchor_states[0].state == AnchorState.CHANGED


def test_fallback_required_when_anchor_missing(tmp_path: Path) -> None:
    repo_root, db_path = _context(tmp_path)
    _save_memory(repo_root, db_path, "Missing memory", ["auth.py"])
    (repo_root / "auth.py").unlink()

    response = _recall(repo_root, db_path)

    assert response.status == core.RecallStatus.FALLBACK_REQUIRED
    assert len(response.results) > 0
    assert response.results[0].anchor_states[0].state == AnchorState.MISSING


def test_fallback_required_when_only_memory_is_partially_valid(
    tmp_path: Path,
) -> None:
    repo_root, db_path = _context(tmp_path)
    _save_memory(
        repo_root,
        db_path,
        "Partially valid memory",
        ["stable.py", "changed.py"],
    )
    (repo_root / "changed.py").write_text("CHANGED = True\n", encoding="utf-8")

    response = _recall(repo_root, db_path)

    assert response.status == core.RecallStatus.FALLBACK_REQUIRED
    assert response.results[0].anchor_integrity == pytest.approx(0.5)
    assert response.results[0].structurally_valid is False


def test_no_match_when_no_episode_passes_semantic_filter(tmp_path: Path) -> None:
    repo_root, db_path = _context(tmp_path)
    episode = _save_memory(repo_root, db_path, "Unrelated memory", ["auth.py"])
    save_episode_embedding(db_path, episode.id, [0.0, 1.0], "test-model")

    response = _recall(repo_root, db_path, min_similarity=0.5)

    assert response.status == core.RecallStatus.NO_MATCH
    assert response.results == []


def test_no_match_for_empty_database(tmp_path: Path) -> None:
    repo_root, db_path = _context(tmp_path)

    response = _recall(repo_root, db_path)

    assert response.status == core.RecallStatus.NO_MATCH
    assert response.results == []


def test_found_when_any_semantic_candidate_is_fully_valid(tmp_path: Path) -> None:
    repo_root, db_path = _context(tmp_path)
    first = _save_memory(repo_root, db_path, "Drifted A", ["a.py"])
    second = _save_memory(repo_root, db_path, "Drifted B", ["b.py"])
    valid = _save_memory(repo_root, db_path, "Current C", ["c.py"])
    save_episode_embedding(db_path, first.id, [1.0, 0.0], "test-model")
    save_episode_embedding(db_path, second.id, [0.8, 0.6], "test-model")
    save_episode_embedding(db_path, valid.id, [0.7, sqrt(0.51)], "test-model")
    (repo_root / "a.py").write_text("DRIFTED = True\n", encoding="utf-8")
    (repo_root / "b.py").write_text("DRIFTED = True\n", encoding="utf-8")

    response = _recall(repo_root, db_path)

    assert response.status == core.RecallStatus.FOUND
    assert any(result.episode.id == valid.id for result in response.results)


def test_status_is_calculated_before_limit(tmp_path: Path) -> None:
    repo_root, db_path = _context(tmp_path)
    a_symbols = [f"a_{index}.py" for index in range(10)]
    b_symbols = [f"b_{index}.py" for index in range(5)]
    first = _save_memory(repo_root, db_path, "Score 0.90 drifted", a_symbols)
    second = _save_memory(repo_root, db_path, "Score 0.80 drifted", b_symbols)
    trusted = _save_memory(repo_root, db_path, "Score 0.70 valid", ["trusted.py"])
    (repo_root / a_symbols[-1]).write_text("DRIFTED = True\n", encoding="utf-8")
    (repo_root / b_symbols[-1]).write_text("DRIFTED = True\n", encoding="utf-8")
    save_episode_embedding(db_path, trusted.id, [0.7, sqrt(0.51)], "test-model")

    response = _recall(repo_root, db_path, limit=2)

    assert response.status == core.RecallStatus.FOUND
    assert [result.episode.id for result in response.results] == [
        first.id,
        second.id,
    ]
    assert trusted.id not in {result.episode.id for result in response.results}


def test_drifted_results_remain_available_during_fallback(tmp_path: Path) -> None:
    repo_root, db_path = _context(tmp_path)
    episode = _save_memory(
        repo_root,
        db_path,
        "Diagnostic drifted memory",
        ["stable.py", "changed.py"],
    )
    (repo_root / "changed.py").write_text("CHANGED = True\n", encoding="utf-8")

    response = _recall(repo_root, db_path)

    assert response.status == core.RecallStatus.FALLBACK_REQUIRED
    assert len(response.results) == 1
    assert response.results[0].episode.id == episode.id


def test_fallback_does_not_modify_persisted_episode(tmp_path: Path) -> None:
    repo_root, db_path = _context(tmp_path)
    episode = _save_memory(repo_root, db_path, "Historical memory", ["auth.py"])
    original_anchor = episode.anchors[0].model_copy(deep=True)
    (repo_root / "auth.py").write_text("AUTH = 'changed'\n", encoding="utf-8")

    response = _recall(repo_root, db_path)
    stored = get_episode(db_path, episode.id)

    assert response.status == core.RecallStatus.FALLBACK_REQUIRED
    assert stored is not None
    assert stored.anchors[0] == original_anchor
    assert stored.anchors[0].state == AnchorState.VALID


def test_min_similarity_remains_semantic_when_score_is_zero(
    tmp_path: Path,
) -> None:
    repo_root, db_path = _context(tmp_path)
    episode = _save_memory(repo_root, db_path, "Semantic but drifted", ["auth.py"])
    save_episode_embedding(db_path, episode.id, [0.85, sqrt(0.2775)], "test-model")
    (repo_root / "auth.py").write_text("DRIFTED = True\n", encoding="utf-8")

    response = _recall(repo_root, db_path, min_similarity=0.8)

    assert response.status == core.RecallStatus.FALLBACK_REQUIRED
    assert len(response.results) == 1
    assert response.results[0].semantic_similarity == pytest.approx(0.85)
    assert response.results[0].score == pytest.approx(0.0)


def test_unanchored_semantic_episode_requires_fallback(tmp_path: Path) -> None:
    repo_root, db_path = _context(tmp_path)
    episode = Episode(type=EpisodeType.OBSERVATION, summary="Unanchored legacy memory")
    save_episode(db_path, episode)
    save_episode_embedding(db_path, episode.id, [1.0, 0.0], "test-model")

    response = _recall(repo_root, db_path)

    assert response.status == core.RecallStatus.FALLBACK_REQUIRED
    assert len(response.results) == 1
    assert response.results[0].episode.id == episode.id
    assert response.results[0].anchor_integrity == pytest.approx(0.0)
