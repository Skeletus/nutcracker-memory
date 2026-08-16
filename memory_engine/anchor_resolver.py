"""Resolve file anchors against the current repository contents.

This module is a deliberately simplified engineering implementation of the
structural-drift proposal in Section 3.5 of the curated scientific source. It
uses a one-key lookup from a file path to a content hash. It is not a graph and
does not model repository nodes, edges, or semantic symbol identity.
"""

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from memory_engine.episode import Anchor, AnchorState


class SymbolNotFoundError(FileNotFoundError):
    """Raised when the file backing an anchor no longer exists."""

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        super().__init__(f"Anchor file does not exist: {filepath}")


def compute_symbol_hash(filepath: str, symbol: str | None = None) -> str:
    """Return the SHA-256 digest of an anchor's complete file contents.

    ``symbol`` is accepted to preserve the future symbol-level API. Extracting
    and hashing only a function or class body is intentionally outside the MVP;
    the current implementation always hashes the complete file.

    A missing file raises ``SymbolNotFoundError`` rather than returning a value
    that could be confused with a valid digest. Callers that resolve drift can
    catch this explicit sentinel exception and translate it to ``MISSING``.
    """

    # Reserved for a future symbol-aware parser; the MVP hashes the whole file.
    _ = symbol
    digest = sha256()

    try:
        with Path(filepath).open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
    except FileNotFoundError as error:
        raise SymbolNotFoundError(filepath) from error

    return digest.hexdigest()


def resolve_anchor(
    symbol: str,
    stored_hash: str | None,
    current_hash: str | None,
) -> AnchorState:
    """Resolve one file anchor from its stored and current content hashes."""

    # The symbol is retained for future diagnostics and symbol-level matching.
    _ = symbol

    if current_hash is None:
        return AnchorState.MISSING
    if current_hash == stored_hash:
        return AnchorState.VALID

    # Hashes only establish that bytes changed. Rename and contradiction
    # detection require evidence unavailable to this file-level MVP.
    return AnchorState.CHANGED


def resolve_all_anchors(anchors: list[Anchor], repo_root: str) -> list[Anchor]:
    """Return copies of all anchors resolved against files under ``repo_root``.

    A missing baseline hash cannot match a current file and therefore resolves
    as ``CHANGED``. Original Pydantic model instances are never mutated.
    """

    verified_at = datetime.now(UTC)
    resolved: list[Anchor] = []

    for anchor in anchors:
        filepath = Path(repo_root) / anchor.symbol
        try:
            current_hash = compute_symbol_hash(str(filepath), anchor.symbol)
        except SymbolNotFoundError:
            current_hash = None

        state = resolve_anchor(anchor.symbol, anchor.content_hash, current_hash)
        resolved.append(
            anchor.model_copy(
                update={
                    "state": state,
                    "last_verified_at": verified_at,
                }
            )
        )

    return resolved
