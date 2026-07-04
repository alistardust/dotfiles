"""Reconcile-level artist-alias behavior: retrieval expansion + scoring.

Reproduces the two real 98\u00b0 failures on stub clients:

* ``why 2614`` shape — the 98\u00ba recording never surfaces under a
  "98 Degrees" query, so alias-expanded retrieval must query the variant
  spelling to find it at all.
* ``why 2612`` shape — the candidate is retrieved but its variant artist
  spelling tanked the score below threshold; alias-aware scoring must clear it.

Plus the cost guarantee: a non-aliased artist issues no extra API calls.
"""
from pathlib import Path

import pytest
from unittest.mock import MagicMock

from tuneshift.db import Database
from tuneshift.models import Track, TrackResult
from tuneshift.reconcile import reconcile_track

DEG = "\u00b0"  # U+00B0 degree sign
ORD = "\u00ba"  # U+00BA masculine ordinal indicator


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db")


def _track(db: Database, title: str, artist: str, **kw) -> int:
    return db.add_track(Track(title=title, artist=artist, **kw))


def _base_client() -> MagicMock:
    client = MagicMock()
    client.platform_name = "tidal"
    client.search_isrc.return_value = None
    client.search_album.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []
    client.get_album_tracks.return_value = []
    return client


class TestRetrievalExpansion:
    def test_variant_only_track_surfaces_via_alias_query(self, db: Database):
        # The source says "98 Degrees"; the platform only indexes the 98\u00ba
        # spelling. A plain query returns the wrong artist entirely.
        track_id = _track(
            db, "The Hardest Thing", "98 Degrees", duration_seconds=280,
        )
        right = TrackResult(
            platform_id="right", title="The Hardest Thing", artist=f"98{ORD}",
            album="98 Degrees and Rising", duration_seconds=280,
        )
        wrong = TrackResult(
            platform_id="wrong", title="The Hardest Thing", artist="Gorillaz",
            album="Demon Days", duration_seconds=200,
        )
        client = _base_client()

        def _search(query, limit=10):
            # The variant spelling only appears in the alias-expanded query.
            if f"98{ORD}" in query or f"98{DEG}" in query:
                return [right]
            return [wrong]

        client.search_track.side_effect = _search

        result = reconcile_track(db, track_id, client)
        assert result.platform_track_id == "right"
        assert result.match_type == "alias_expansion"
        # The variant spelling was actually queried.
        queried = [c.args[0] for c in client.search_track.call_args_list]
        assert any(f"98{ORD}" in q for q in queried)

    def test_no_extra_calls_for_non_aliased_artist(self, db: Database):
        # Gorillaz is in no alias class: retrieval must not issue variant queries.
        track_id = _track(db, "Feel Good Inc", "Gorillaz", duration_seconds=222)
        found = TrackResult(
            platform_id="fg", title="Feel Good Inc", artist="Gorillaz",
            album="Demon Days", duration_seconds=222,
        )
        client = _base_client()
        client.search_track.return_value = [found]

        reconcile_track(db, track_id, client)
        # Only the two title-based strategies fire (no album on the track);
        # no alias-expansion query is added.
        assert client.search_track.call_count == 2


class TestScoringClearsThreshold:
    def test_retrieved_variant_now_scores_high(self, db: Database):
        # The candidate is retrieved by the standard search but carries the
        # variant artist spelling that previously scored below threshold.
        track_id = _track(
            db, "I Do Cherish You", "98 Degrees", duration_seconds=240,
        )
        candidate = TrackResult(
            platform_id="cand", title="I Do Cherish You", artist=f"98{ORD}",
            album="98 Degrees and Rising", duration_seconds=240,
        )
        client = _base_client()
        client.search_track.return_value = [candidate]

        result = reconcile_track(db, track_id, client)
        assert result.platform_track_id == "cand"
        assert result.confidence == "high"
        assert result.score >= 80
        # An aliased artist must not be flagged as a divergent artist mismatch.
        assert not (result.divergence_note or "").startswith("Artist mismatch")

    def test_db_added_class_bridges_at_reconcile(self, db: Database):
        # A user-curated class the seed does not know still rescues the match.
        db.add_artist_alias(["Prince", "The Artist"])
        track_id = _track(db, "Kiss", "The Artist", duration_seconds=226)
        candidate = TrackResult(
            platform_id="p", title="Kiss", artist="Prince",
            album="Parade", duration_seconds=226,
        )
        client = _base_client()
        client.search_track.return_value = [candidate]

        result = reconcile_track(db, track_id, client)
        assert result.platform_track_id == "p"
        assert result.confidence == "high"
