"""Artist-alias persistence: add / list / remove, bridging, and idempotency.

These lock the DB half of the artist-alias equivalence feature (schema v14):
raw surface forms are retained verbatim, normalized keys drive class bridging,
and a class collapses once it drops below two distinct members.
"""
from pathlib import Path

import pytest

from tuneshift.db import Database

DEG = "\u00b0"  # U+00B0 degree sign
ORD = "\u00ba"  # U+00BA masculine ordinal indicator


@pytest.fixture
def db(tmp_db: Path) -> Database:
    return Database(tmp_db)


def _flatten(classes):
    return {m for members in classes for m in members}


class TestSchema:
    def test_migrated_version_is_14(self, db: Database):
        version = db.conn.execute(
            "SELECT value FROM schema_meta WHERE key='version'"
        ).fetchone()[0]
        assert int(version) == 14

    def test_artist_aliases_table_and_index_exist(self, db: Database):
        cols = {r[1] for r in db.conn.execute(
            "PRAGMA table_info(artist_aliases)"
        ).fetchall()}
        assert {"class_id", "member", "norm_member", "created_at"} <= cols
        indexes = {r[1] for r in db.conn.execute(
            "PRAGMA index_list(artist_aliases)"
        ).fetchall()}
        assert "idx_artist_aliases_norm" in indexes


class TestAddListRemove:
    def test_round_trip(self, db: Database):
        db.add_artist_alias(["98 Degrees", f"98{DEG}", f"98{ORD}"])
        classes = db.get_artist_alias_classes()
        assert len(classes) == 1
        assert classes[0] == frozenset({"98 Degrees", f"98{DEG}", f"98{ORD}"})

    def test_raw_surface_forms_preserved_verbatim(self, db: Database):
        db.add_artist_alias(["Ke$ha", "Kesha"])
        assert _flatten(db.get_artist_alias_classes()) == {"Ke$ha", "Kesha"}

    def test_surrounding_whitespace_trimmed(self, db: Database):
        db.add_artist_alias(["  98 Degrees ", f" 98{ORD}"])
        assert _flatten(db.get_artist_alias_classes()) == {"98 Degrees", f"98{ORD}"}

    def test_requires_two_distinct_members(self, db: Database):
        with pytest.raises(ValueError):
            db.add_artist_alias(["Solo"])
        with pytest.raises(ValueError):
            db.add_artist_alias(["Dup", "Dup", " Dup "])

    def test_two_independent_classes(self, db: Database):
        db.add_artist_alias(["98 Degrees", f"98{ORD}"])
        db.add_artist_alias(["Ke$ha", "Kesha"])
        assert len(db.get_artist_alias_classes()) == 2


class TestIdempotencyAndBridging:
    def test_adding_duplicate_members_is_noop(self, db: Database):
        db.add_artist_alias(["98 Degrees", f"98{ORD}"])
        db.add_artist_alias(["98 Degrees", f"98{ORD}"])
        classes = db.get_artist_alias_classes()
        assert len(classes) == 1
        assert len(classes[0]) == 2

    def test_overlapping_add_extends_same_class(self, db: Database):
        db.add_artist_alias(["98 Degrees", f"98{ORD}"])
        db.add_artist_alias([f"98{ORD}", "Ninety-Eight Degrees"])
        classes = db.get_artist_alias_classes()
        assert len(classes) == 1
        assert classes[0] == frozenset(
            {"98 Degrees", f"98{ORD}", "Ninety-Eight Degrees"}
        )

    def test_bridging_merges_two_existing_classes(self, db: Database):
        db.add_artist_alias(["A One", "A Two"])
        db.add_artist_alias(["B One", "B Two"])
        assert len(db.get_artist_alias_classes()) == 2
        # A member bridging both classes collapses them into one.
        db.add_artist_alias(["A One", "B One"])
        classes = db.get_artist_alias_classes()
        assert len(classes) == 1
        assert classes[0] == frozenset({"A One", "A Two", "B One", "B Two"})


class TestRemove:
    def test_remove_from_larger_class_keeps_class(self, db: Database):
        db.add_artist_alias(["98 Degrees", f"98{DEG}", f"98{ORD}"])
        assert db.remove_artist_alias(f"98{DEG}") is True
        classes = db.get_artist_alias_classes()
        assert len(classes) == 1
        assert classes[0] == frozenset({"98 Degrees", f"98{ORD}"})

    def test_remove_below_two_drops_class(self, db: Database):
        db.add_artist_alias(["Ke$ha", "Kesha"])
        assert db.remove_artist_alias("Kesha") is True
        assert db.get_artist_alias_classes() == []

    def test_remove_trims_before_matching(self, db: Database):
        db.add_artist_alias(["98 Degrees", f"98{ORD}"])
        assert db.remove_artist_alias("  98 Degrees ") is True

    def test_remove_absent_member_returns_false(self, db: Database):
        db.add_artist_alias(["98 Degrees", f"98{ORD}"])
        assert db.remove_artist_alias("Nobody") is False

    def test_remove_empty_returns_false(self, db: Database):
        assert db.remove_artist_alias("   ") is False


class TestPersistenceAcrossReopen:
    def test_classes_survive_reopen(self, tmp_db: Path):
        db = Database(tmp_db)
        db.add_artist_alias(["98 Degrees", f"98{ORD}"])
        reopened = Database(tmp_db)
        assert reopened.get_artist_alias_classes() == [
            frozenset({"98 Degrees", f"98{ORD}"})
        ]
