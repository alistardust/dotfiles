"""Tests for review clustering and review-burden reporting."""
from tuneshift.matching import (
    ReviewItem,
    cluster_reviews,
    compute_burden,
    needs_review,
    review_kind,
)


def _item(track_id, artist, availability, reason_code, *, album="Album",
          playlist_id=1, title="Song", platform="tidal"):
    return ReviewItem(
        track_id=track_id, title=title, artist=artist, album=album,
        platform=platform, availability=availability, reason_code=reason_code,
        playlist_id=playlist_id, playlist_name=f"PL{playlist_id}",
    )


class TestReviewKind:
    def test_clean_match_needs_no_review(self):
        assert review_kind("exact_available", "matched") is None

    def test_healthy_lock_needs_no_review(self):
        assert review_kind("exact_available", "locked") is None

    def test_substitute_needs_no_review(self):
        assert review_kind("substitute_available", "substituted") is None

    def test_ambiguous_needs_review(self):
        assert review_kind("ambiguous", "ambiguous_top") == "ambiguous"

    def test_not_found_is_hard_fail(self):
        assert review_kind("not_found", "no_candidates") == "hard_fail"

    def test_held_lock_is_hard_fail(self):
        # A durable lock whose recording is gone is surfaced, not hidden.
        assert review_kind("exact_unavailable", "lock_held") == "hard_fail"

    def test_needs_review_helper(self):
        assert needs_review(_item(1, "A", "ambiguous", "ambiguous_top"))
        assert not needs_review(_item(1, "A", "exact_available", "matched"))


class TestClustering:
    def test_same_artist_same_reason_clusters_together(self):
        items = [
            _item(1, "Big Freedia", "ambiguous", "ambiguous_top"),
            _item(2, "Big Freedia", "ambiguous", "ambiguous_top"),
            _item(3, "Big Freedia", "ambiguous", "ambiguous_top"),
        ]
        clusters = cluster_reviews(items)
        assert len(clusters) == 1
        assert clusters[0].size == 3
        assert "Big Freedia" in clusters[0].summary

    def test_artist_normalization_merges_variants(self):
        # Case differences fold together (accent folding is Chunk 8 i18n work).
        items = [
            _item(1, "Big Freedia", "ambiguous", "ambiguous_top"),
            _item(2, "BIG FREEDIA", "ambiguous", "ambiguous_top"),
        ]
        clusters = cluster_reviews(items)
        assert len(clusters) == 1
        assert clusters[0].size == 2

    def test_different_reasons_split_clusters(self):
        items = [
            _item(1, "A", "ambiguous", "ambiguous_top"),
            _item(2, "A", "not_found", "no_candidates"),
        ]
        clusters = cluster_reviews(items)
        assert len(clusters) == 2

    def test_clean_items_excluded_from_clusters(self):
        items = [
            _item(1, "A", "exact_available", "matched"),
            _item(2, "A", "ambiguous", "ambiguous_top"),
        ]
        clusters = cluster_reviews(items)
        assert len(clusters) == 1
        assert clusters[0].items[0].track_id == 2

    def test_clusters_sorted_largest_first(self):
        items = [
            _item(1, "Solo", "not_found", "no_candidates"),
            _item(2, "Popular", "ambiguous", "ambiguous_top"),
            _item(3, "Popular", "ambiguous", "ambiguous_top"),
        ]
        clusters = cluster_reviews(items)
        assert clusters[0].size == 2
        assert clusters[0].artist == "Popular"
        assert clusters[1].size == 1

    def test_empty_input(self):
        assert cluster_reviews([]) == []


class TestBurden:
    def test_all_clean_zero_burden(self):
        items = [_item(i, "A", "exact_available", "matched") for i in range(10)]
        burden = compute_burden(items, total_tracks=10)
        assert burden.needs_review == 0
        assert burden.per_1000 == 0.0
        assert burden.zero_intervention_pct == 100.0

    def test_mixed_burden_counts(self):
        items = [
            _item(1, "A", "ambiguous", "ambiguous_top", playlist_id=1),
            _item(2, "B", "not_found", "no_candidates", playlist_id=1),
            _item(3, "C", "exact_available", "matched", playlist_id=2),
        ]
        burden = compute_burden(items, total_tracks=3)
        assert burden.ambiguous == 1
        assert burden.hard_fail == 1
        assert burden.needs_review == 2

    def test_per_1000_scales(self):
        # 2 of 1000 need review -> 2.0 per 1000.
        items = [_item(1, "A", "ambiguous", "ambiguous_top"),
                 _item(2, "B", "not_found", "no_candidates")]
        burden = compute_burden(items, total_tracks=1000)
        assert burden.per_1000 == 2.0

    def test_zero_intervention_playlist_pct(self):
        items = [
            _item(1, "A", "ambiguous", "ambiguous_top", playlist_id=1),
            _item(2, "B", "exact_available", "matched", playlist_id=2),
            _item(3, "C", "exact_available", "matched", playlist_id=2),
        ]
        burden = compute_burden(items, total_tracks=3)
        # playlist 1 is dirty, playlist 2 is clean -> 1 of 2 = 50%.
        assert burden.total_playlists == 2
        assert burden.zero_intervention_playlists == 1
        assert burden.zero_intervention_pct == 50.0

    def test_empty_is_safe(self):
        burden = compute_burden([], total_tracks=0)
        assert burden.per_1000 == 0.0
        assert burden.zero_intervention_pct == 100.0
