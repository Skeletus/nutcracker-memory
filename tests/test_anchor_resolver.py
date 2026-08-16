from pathlib import Path

import pytest

from memory_engine.anchor_resolver import (
    SymbolNotFoundError,
    compute_symbol_hash,
    resolve_all_anchors,
    resolve_anchor,
)
from memory_engine.episode import (
    Anchor,
    AnchorLevel,
    AnchorRelation,
    AnchorState,
)


def test_compute_symbol_hash_tracks_complete_file_content(tmp_path: Path) -> None:
    filepath = tmp_path / "module.py"
    filepath.write_text("VALUE = 1\n", encoding="utf-8")

    first_hash = compute_symbol_hash(str(filepath))
    unchanged_hash = compute_symbol_hash(str(filepath))
    filepath.write_text("VALUE = 2\n", encoding="utf-8")
    changed_hash = compute_symbol_hash(str(filepath))

    assert unchanged_hash == first_hash
    assert changed_hash != first_hash


def test_compute_symbol_hash_raises_clear_error_for_missing_file(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing.py"

    with pytest.raises(SymbolNotFoundError, match="Anchor file does not exist"):
        compute_symbol_hash(str(missing_path))


def test_resolve_anchor_returns_valid_for_matching_hashes() -> None:
    assert resolve_anchor("module.py", "same", "same") == AnchorState.VALID


def test_resolve_anchor_returns_missing_when_current_hash_is_none() -> None:
    assert resolve_anchor("module.py", "stored", None) == AnchorState.MISSING


def test_resolve_anchor_returns_changed_for_different_hashes() -> None:
    assert (
        resolve_anchor("module.py", "stored", "changed")
        == AnchorState.CHANGED
    )


def test_resolve_all_anchors_updates_only_copies_and_detects_changed_file(
    tmp_path: Path,
) -> None:
    paths = [tmp_path / "one.py", tmp_path / "two.py", tmp_path / "three.py"]
    for index, path in enumerate(paths, start=1):
        path.write_text(f"VALUE = {index}\n", encoding="utf-8")

    anchors = [
        Anchor(
            symbol=path.name,
            content_hash=compute_symbol_hash(str(path)),
            level=level,
            relation=relation,
        )
        for path, level, relation in zip(
            paths,
            (AnchorLevel.STRUCTURAL, AnchorLevel.REGIONAL, AnchorLevel.LOCAL),
            (
                AnchorRelation.PRIMARY,
                AnchorRelation.MODIFIED,
                AnchorRelation.DEPENDENCY,
            ),
            strict=True,
        )
    ]
    paths[1].write_text("VALUE = 'changed'\n", encoding="utf-8")

    resolved = resolve_all_anchors(anchors, str(tmp_path))

    assert [anchor.state for anchor in resolved] == [
        AnchorState.VALID,
        AnchorState.CHANGED,
        AnchorState.VALID,
    ]
    for original, updated in zip(anchors, resolved, strict=True):
        assert updated is not original
        assert original.state == AnchorState.UNVERIFIED
        assert original.last_verified_at is None
        assert updated.last_verified_at is not None
