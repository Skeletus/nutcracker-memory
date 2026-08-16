"""Pydantic models for persistent, structurally anchored memory episodes.

These models are bio-inspired engineering abstractions motivated by the
curated scientific source. They do not reproduce a known biological memory
algorithm. Structural validity is modeled explicitly; no time-to-live or
time-based decay field is included because Section 2.6 does not justify time
as the primary validity mechanism.
"""

from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def _utc_now() -> datetime:
    """Return a timezone-aware timestamp for persistence metadata."""

    return datetime.now(UTC)


def _new_episode_id() -> str:
    """Generate a compact, prefixed identifier suitable for serialization."""

    return f"E{uuid4().hex[:12]}"


class AnchorLevel(str, Enum):
    """Stability tier of a repository landmark.

    Section 2.4 motivates distinguishing broad structural cues from more
    volatile local detail. Validation anchors form a separate tier because
    tests and checks provide evidence about an episode's outcome.
    """

    STRUCTURAL = "structural"
    REGIONAL = "regional"
    LOCAL = "local"
    VALIDATION = "validation"


class AnchorRelation(str, Enum):
    """Role played by a repository landmark in an episode.

    Recording the relation preserves how each independently useful cue
    supports the episode instead of treating anchors as interchangeable tags.
    """

    PRIMARY = "primary"
    MODIFIED = "modified"
    DEPENDENCY = "dependency"
    VALIDATION = "validation"


class AnchorState(str, Enum):
    """Observed structural drift state for one anchor.

    The states follow the graceful-degradation proposal in Section 3.5. An
    anchor starts unverified until it is compared with the current repository.
    """

    VALID = "valid"
    CHANGED = "changed"
    RENAMED = "renamed"
    # Retained for backward-compatible deserialization of pre-Phase-6 data.
    PARTIALLY_BROKEN = "partially_broken"
    CONTRADICTED = "contradicted"
    MISSING = "missing"
    UNVERIFIED = "unverified"


class Anchor(BaseModel):
    """A structural cue that connects an episode to the repository.

    Multi-anchor episodes are motivated by Sections 2.2 and 2.3: redundant
    cues may preserve discoverability when one symbol moves or disappears.
    This model intentionally permits single-anchor episodes; confidence policy
    belongs to the future scoring layer rather than schema validation.
    """

    symbol: str
    content_hash: str | None = None
    level: AnchorLevel
    relation: AnchorRelation
    state: AnchorState = AnchorState.UNVERIFIED
    last_verified_commit: str | None = None
    last_verified_at: datetime | None = None


class EpisodeType(str, Enum):
    """Category of salient event that caused durable episode formation.

    The categories implement an event-driven encoding boundary inspired by
    Section 2.8, rather than continuous logging of every observation or token.
    """

    DECISION = "decision"
    BUG_FIX = "bug_fix"
    FAILED_APPROACH = "failed_approach"
    OBSERVATION = "observation"
    CONVENTION = "convention"


class OutcomeStatus(str, Enum):
    """Observed result of the event represented by an episode."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class Outcome(BaseModel):
    """Outcome evidence kept separately from the episode narrative."""

    status: OutcomeStatus = OutcomeStatus.UNKNOWN
    tests_passed: bool | None = None
    notes: str | None = None


class Provenance(BaseModel):
    """Traceability metadata for the repository and agent session of origin."""

    commit: str | None = None
    session_id: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class EpisodeState(BaseModel):
    """Mutable content and retrieval state, separate from structural anchors.

    Section 2.9 and hypothesis H7 motivate keeping memory identity/location
    distinct from current content state. Contradicting or superseding an
    episode therefore does not mutate the drift state of any anchor.
    """

    structurally_valid: bool = True
    contradicted: bool = False
    superseded_by: str | None = None
    retrieval_count: int = 0
    last_retrieved_at: datetime | None = None


class MemoryStrength(BaseModel):
    """Independent evidence signals for future retrieval scoring.

    Section 2.7 motivates testing unequal, evidence-based memory strength as an
    engineering analogue; these fields are not claims about neural storage.
    They remain separate so a future scoring function can weight each signal
    experimentally.
    """

    anchor_integrity: float = 1.0
    retrieval_success: float = 0.5
    outcome_support: float = 0.5

    @field_validator(
        "anchor_integrity",
        "retrieval_success",
        "outcome_support",
        mode="after",
    )
    @classmethod
    def clamp_unit_interval(cls, value: float) -> float:
        """Clamp evidence signals to the closed interval from zero to one."""

        return min(1.0, max(0.0, value))


class Episode(BaseModel):
    """A durable event record anchored to one or more repository landmarks.

    Anchors describe structural identity, while ``state`` describes mutable
    content and retrieval status. Empty and single-anchor episodes are accepted
    so that confidence can be assessed later instead of losing the record.
    """

    id: str = Field(default_factory=_new_episode_id)
    type: EpisodeType
    summary: str
    anchors: list[Anchor] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    decision: str | None = None
    outcome: Outcome = Field(default_factory=Outcome)
    provenance: Provenance = Field(default_factory=Provenance)
    state: EpisodeState = Field(default_factory=EpisodeState)
    strength: MemoryStrength = Field(default_factory=MemoryStrength)

    def primary_anchor(self) -> Anchor | None:
        """Return the first anchor identified as the episode's primary subject."""

        return next(
            (
                anchor
                for anchor in self.anchors
                if anchor.relation == AnchorRelation.PRIMARY
            ),
            None,
        )

    def surviving_anchor_count(self) -> int:
        """Count anchors verified as valid in the current repository."""

        return sum(anchor.state == AnchorState.VALID for anchor in self.anchors)
