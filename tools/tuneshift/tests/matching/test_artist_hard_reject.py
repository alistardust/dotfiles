"""Zero-artist-overlap hard reject in version-aware scoring (BUG-3)."""

from tuneshift.matching.track import score_match_with_version


def test_same_title_different_artist_is_hard_rejected():
    # Lauren Jauregui "Need You Tonight" vs INXS "Need You Tonight".
    score = score_match_with_version(
        "Need You Tonight", "Lauren Jauregui", None,
        "Need You Tonight", "INXS", "Kick",
    )
    assert score == 0


def test_same_title_same_artist_not_rejected():
    score = score_match_with_version(
        "Need You Tonight", "INXS", "Kick",
        "Need You Tonight", "INXS", "Kick",
    )
    assert score > 0


def test_missing_source_artist_is_not_a_mismatch():
    # Empty artist yields no artist signal, not a hard reject.
    score = score_match_with_version(
        "Some Song", "", None,
        "Some Song", "Whoever", "Album",
    )
    assert score > 0


def test_featured_artist_containment_survives():
    # A token-subset (primary artist contained in the credited string) must
    # not hard-reject.
    score = score_match_with_version(
        "Song", "Drake", None,
        "Song", "Drake feat. Future", "Album",
    )
    assert score > 0


def test_different_artists_sharing_no_token_reject():
    # No shared token, low ratio -> hard reject even with identical title/album.
    score = score_match_with_version(
        "Halo", "Beyonce", "Album X",
        "Halo", "Depeche Mode", "Album X",
    )
    assert score == 0
