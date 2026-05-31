"""Weight profiles and playlist intent configuration."""
from dataclasses import dataclass, field


DEFAULT_WEIGHTS: dict[str, float] = {
    "themes": 0.35,
    "energy": 0.22,
    "instrumentation": 0.18,
    "bpm": 0.12,
    "mode": 0.08,
    "key": 0.05,
}


@dataclass
class WeightProfile:
    """A named configuration for sequencing behavior."""

    name: str
    description: str
    weights: dict[str, float]
    arc: str = "wave"
    bold_jump_chance: float = 0.10
    artist_min_separation: int = 4
    narrative_mode: str = "river"  # "river" | "chapter" | "dj_set"
    context_window: int = 5
    penalty_overrides: dict[str, float] = field(default_factory=dict)


_BUILTIN_PROFILES: dict[str, WeightProfile] = {
    "default": WeightProfile(
        name="default",
        description="Balanced defaults for 60s-70s rock/folk/psych",
        weights=dict(DEFAULT_WEIGHTS),
        arc="wave",
        bold_jump_chance=0.10,
        artist_min_separation=4,
        narrative_mode="river",
        context_window=5,
    ),
    "psych-journey": WeightProfile(
        name="psych-journey",
        description="Psychedelic exploration with intentional strangeness",
        weights={"themes": 0.30, "energy": 0.25, "instrumentation": 0.25,
                 "bpm": 0.05, "mode": 0.10, "key": 0.05},
        arc="narrative",
        bold_jump_chance=0.15,
        artist_min_separation=3,
        narrative_mode="dj_set",
        context_window=5,
    ),
    "sunset-chill": WeightProfile(
        name="sunset-chill",
        description="Gradual energy descent for evening listening",
        weights={"themes": 0.35, "energy": 0.30, "instrumentation": 0.15,
                 "bpm": 0.10, "mode": 0.05, "key": 0.05},
        arc="descending",
        bold_jump_chance=0.05,
        artist_min_separation=5,
        narrative_mode="river",
        context_window=6,
    ),
    "folk-narrative": WeightProfile(
        name="folk-narrative",
        description="Chronological/thematic storytelling",
        weights={"themes": 0.45, "energy": 0.15, "instrumentation": 0.15,
                 "bpm": 0.10, "mode": 0.10, "key": 0.05},
        arc="narrative",
        bold_jump_chance=0.08,
        artist_min_separation=4,
        narrative_mode="chapter",
        context_window=5,
    ),
    "road-trip": WeightProfile(
        name="road-trip",
        description="High energy with variety, tolerates texture jumps",
        weights={"themes": 0.30, "energy": 0.30, "instrumentation": 0.10,
                 "bpm": 0.20, "mode": 0.05, "key": 0.05},
        arc="wave",
        bold_jump_chance=0.12,
        artist_min_separation=3,
        narrative_mode="dj_set",
        context_window=4,
    ),
}


def get_profile(name: str) -> WeightProfile:
    """Load a named profile. Raises KeyError if not found."""
    if name not in _BUILTIN_PROFILES:
        raise KeyError(f"Unknown profile: '{name}'. Available: {list(_BUILTIN_PROFILES.keys())}")
    return _BUILTIN_PROFILES[name]


def list_profiles() -> list[str]:
    """Return all available profile names."""
    return list(_BUILTIN_PROFILES.keys())


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """Normalize weights to sum to 1.0."""
    total = sum(weights.values())
    if total == 0:
        raise ValueError("Weights cannot all be zero")
    return {k: v / total for k, v in weights.items()}


def merge_cli_overrides(
    base: dict[str, float],
    overrides: dict[str, float],
) -> dict[str, float]:
    """Apply CLI weight overrides to base profile, then renormalize."""
    merged = dict(base)
    for key, value in overrides.items():
        if key in merged:
            merged[key] = value
    return normalize_weights(merged)
