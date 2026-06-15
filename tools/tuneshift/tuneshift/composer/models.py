"""Data models for the narrative playlist composer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from tuneshift.sequencer.metadata import TrackMetadata


class TransitionType(Enum):
    SHARP_CUT = "sharp_cut"
    COLLAPSE = "collapse"
    BUILD = "build"
    GRADUAL = "gradual"
    SUSTAIN = "sustain"


@dataclass
class PlaylistConcept:
    theme: str
    hard_rules: list[str] = field(default_factory=list)
    soft_rules: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    era: str | None = None

    @property
    def has_hard_rules(self) -> bool:
        return bool(self.hard_rules)


@dataclass
class EnhancedSection:
    name: str
    start_position: int
    end_position: int
    description: str
    implied_intensity: float
    implied_stance: str | None
    capacity: int
    mood: list[str] = field(default_factory=list)
    transition_in: TransitionType = TransitionType.GRADUAL
    transition_out: TransitionType = TransitionType.GRADUAL
    required_tracks: list[str] = field(default_factory=list)
    required_artists: list[str] = field(default_factory=list)
    section_concept: str | None = None
    min_tracks: int = 1


@dataclass
class GapSpec:
    section_name: str
    mood: list[str] = field(default_factory=list)
    intensity_range: tuple[float, float] = (0.0, 1.0)
    stance: str | None = None
    keywords: list[str] = field(default_factory=list)
    duration_range_ms: tuple[int, int] | None = None


@dataclass
class GapReport:
    gap_type: str
    section_name: str
    description: str
    severity: float
    fill_spec: GapSpec | None = None


@dataclass
class Candidate:
    title: str
    artist: str
    source: str
    fitness_score: float
    track_id: int | None = None
    platform_id: str | None = None
    isrc: str | None = None


@dataclass
class MisfitTrack:
    track: TrackMetadata
    section_name: str
    fitness_score: float
    explanation: str


@dataclass
class SectionAssignments:
    assignments: dict[str, list[TrackMetadata]]
    misfits: list[MisfitTrack]
    unassigned: list[TrackMetadata]


@dataclass
class ReviewFinding:
    category: str
    description: str
    severity: float
    section_name: str | None = None


@dataclass
class ComposeResult:
    ordered_tracks: list[TrackMetadata]
    assignments: SectionAssignments
    gaps: list[GapReport]
    review_findings: list[ReviewFinding]
    candidates: dict[str, list[Candidate]] = field(default_factory=dict)
