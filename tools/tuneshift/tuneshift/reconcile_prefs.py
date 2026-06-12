"""Version preference model for reconciliation."""
from dataclasses import dataclass, field


@dataclass
class VersionPreferences:
    prefer: list[str] = field(default_factory=lambda: ["studio", "original", "explicit"])
    avoid: list[str] = field(default_factory=lambda: ["live", "remix", "acoustic", "radio-edit", "clean"])
    duration_tolerance_percent: float = 15.0
    tiebreak_order: list[str] = field(default_factory=lambda: ["newest-remaster", "original-release"])


def resolve_preferences(
    global_prefs: dict | None,
    playlist_prefs: dict | None,
    track_prefs: dict | None,
) -> VersionPreferences:
    """Cascade preferences: track > playlist > global > defaults."""
    base = VersionPreferences()

    for layer in [global_prefs, playlist_prefs, track_prefs]:
        if not layer:
            continue
        if "prefer" in layer:
            base.prefer = layer["prefer"]
        if "avoid" in layer:
            base.avoid = layer["avoid"]
        if "duration_tolerance_percent" in layer:
            base.duration_tolerance_percent = layer["duration_tolerance_percent"]
        if "tiebreak_order" in layer:
            base.tiebreak_order = layer["tiebreak_order"]

    return base


def score_version(
    album_name: str,
    duration_seconds: float,
    prefs: VersionPreferences,
    expected_duration: float | None = None,
) -> float:
    """Score a track version based on preferences. Higher = better."""
    score = 0.0
    name_lower = album_name.lower()

    for keyword in prefs.prefer:
        if keyword.lower() in name_lower:
            score += 10.0

    for keyword in prefs.avoid:
        if keyword.lower() in name_lower:
            score -= 20.0

    if expected_duration and prefs.duration_tolerance_percent:
        tolerance = expected_duration * prefs.duration_tolerance_percent / 100.0
        deviation = abs(duration_seconds - expected_duration)
        if deviation > tolerance:
            score -= 200.0  # hard reject

    return score
