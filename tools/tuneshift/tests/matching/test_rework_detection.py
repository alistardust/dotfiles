"""Named/qualified Edit/Mix reworks classify as distinct recordings (remix).

A "[Producer] New Edit" / "Re-Edit" / "Bootleg" is a distinct reworking, not the
album master, so it must be down-ranked vs a studio source. Radio/single/album
edits are packaging (same recording) and must NOT be treated as remixes.
"""

from tuneshift.matching.track import score_match_with_version
from tuneshift.matching.version import RecordingClass, infer_version


def test_named_new_edit_is_a_remix():
    assert infer_version(
        "Human Nature (Howie Tee New Edit)", "The Remixes"
    ).recording is RecordingClass.REMIX


def test_rework_markers_are_remixes():
    for marker in (
        "Song (Re-Edit)",
        "Song (Reedit)",
        "Song (Rework)",
        "Song (2024 Bootleg)",
        "Song (DJ Mashup)",
        "Song (Vocal Mix)",
        "Song (New Mix)",
    ):
        assert infer_version(marker, "Album").recording is RecordingClass.REMIX, marker


def test_packaging_edits_are_not_remixes():
    # Radio/single/album edits are the SAME recording (packaging), not reworks.
    for marker in (
        "Song (Radio Edit)",
        "Song (Single Edit)",
        "Song (Single Version)",
        "Song (Album Version)",
        "Song (Radio Version)",
    ):
        assert infer_version(marker, "Album").recording is not RecordingClass.REMIX, marker


def test_album_edition_names_are_not_remixes():
    # "Deluxe Edition" etc. contain "edit" only inside "edition" (no boundary).
    for album in ("Bedtime Stories (Deluxe Edition)", "Pearl (Legacy Edition)"):
        assert infer_version("Human Nature", album).recording is RecordingClass.STUDIO, album


def test_studio_source_downranks_a_named_edit_candidate():
    # A studio/album source must not auto-select the rework edit.
    album_version = score_match_with_version(
        "Human Nature", "Madonna", "Bedtime Stories",
        "Human Nature", "Madonna", "Bedtime Stories",
    )
    edit = score_match_with_version(
        "Human Nature", "Madonna", "Bedtime Stories",
        "Human Nature (Howie Tee New Edit)", "Madonna", "The Remixes",
    )
    assert edit < album_version
