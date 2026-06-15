from tuneshift.composer.candidate_finder import find_candidates
from tuneshift.composer.models import GapSpec, PlaylistConcept
from tuneshift.models import Track


class StubDatabase:
    def __init__(self, tracks: list[Track]) -> None:
        self.tracks = tracks

    def search_tracks_by_metadata(
        self,
        intensity_range=None,
        stance=None,
        keywords=None,
        limit=20,
    ) -> list[Track]:
        return self.tracks[:limit]


def _track(track_id: int, title: str, artist: str, **metadata) -> Track:
    return Track(id=track_id, title=title, artist=artist, metadata=metadata)


def test_find_candidates_finds_library_matches() -> None:
    db = StubDatabase(
        [
            _track(
                1,
                "Rage Bloom",
                "The Sparks",
                emotional_intensity=0.88,
                narrator_stance="defiant",
                vibes=["fury"],
            ),
            _track(
                2,
                "Quiet Hour",
                "Still Life",
                emotional_intensity=0.2,
                narrator_stance="peaceful",
                vibes=["calm"],
            ),
        ]
    )
    gap = GapSpec(
        section_name="WRATH",
        mood=["fury"],
        intensity_range=(0.75, 0.95),
        stance="defiant",
        keywords=["wrath", "defiance"],
    )

    candidates = find_candidates(gap, db=db, concept=PlaylistConcept(theme="trans fury"))

    assert len(candidates) == 2
    assert candidates[0].track_id == 1
    assert candidates[0].source == "library"


def test_find_candidates_excludes_assigned_tracks() -> None:
    db = StubDatabase(
        [
            _track(1, "Rage Bloom", "The Sparks", emotional_intensity=0.88, narrator_stance="defiant"),
            _track(2, "Defiant Hearts", "The Sparks", emotional_intensity=0.84, narrator_stance="defiant"),
        ]
    )
    gap = GapSpec(section_name="WRATH", intensity_range=(0.7, 1.0), stance="defiant", keywords=["defiant"])

    candidates = find_candidates(gap, db=db, exclude_ids={1})

    assert [candidate.track_id for candidate in candidates] == [2]


def test_find_candidates_returns_empty_when_no_tier_matches() -> None:
    gap = GapSpec(section_name="WRATH", intensity_range=(0.7, 1.0))

    candidates = find_candidates(gap, db=StubDatabase([]), tiers=["streaming"])

    assert candidates == []


def test_find_candidates_returns_sorted_by_fitness() -> None:
    db = StubDatabase(
        [
            _track(1, "Almost There", "A", emotional_intensity=0.72, narrator_stance="defiant", vibes=["fury"]),
            _track(2, "Perfect Fit", "B", emotional_intensity=0.9, narrator_stance="defiant", vibes=["fury", "anthem"]),
            _track(3, "Same Song", "C", emotional_intensity=0.9, narrator_stance="defiant", vibes=["fury"]),
            _track(4, "Same Song", "C", emotional_intensity=0.82, narrator_stance="defiant", vibes=["fury"]),
        ]
    )
    gap = GapSpec(
        section_name="WRATH",
        mood=["fury"],
        intensity_range=(0.82, 0.95),
        stance="defiant",
        keywords=["anthem", "defiant"],
    )

    candidates = find_candidates(gap, db=db)

    assert [candidate.track_id for candidate in candidates] == [2, 3, 1]
