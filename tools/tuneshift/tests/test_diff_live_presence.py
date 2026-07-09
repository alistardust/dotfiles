"""BUG-6a: diff reflects live platform presence, not the user_approved lock flag."""

from argparse import Namespace
from types import SimpleNamespace

import pytest

from tuneshift.commands.diff_cmd import handle_diff
from tuneshift.db import Database
from tuneshift.models import Track


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


class _FakeClient:
    platform_name = "tidal"

    def __init__(self, live_ids):
        self._live = live_ids

    def load_session(self):
        return True

    def get_playlist_tracks(self, platform_playlist_id):
        return [SimpleNamespace(platform_id=i, title="x") for i in self._live]


def _linked_playlist(db, live_ids, monkeypatch):
    pid = db.create_playlist("Native Tongues")
    t1 = db.add_track(Track(title="Buddy", artist="De La Soul", album=None))
    t2 = db.add_track(Track(title="Description of a Fool", artist="A Tribe Called Quest", album=None))
    db.add_track_to_playlist(pid, t1, 0)
    db.add_track_to_playlist(pid, t2, 1)
    # Auto-matched (user_approved=0): the pre-fix diff wrongly treated these as
    # "would push".
    db.set_platform_mapping(t1, "tidal", "307819222", user_approved=False)
    db.set_platform_mapping(t2, "tidal", "222", user_approved=False)
    db.link_platform_playlist(pid, "tidal", "PL1")
    monkeypatch.setattr(
        "tuneshift.commands.ingest_cmd._load_client",
        lambda name: _FakeClient(live_ids),
    )
    return pid


def test_diff_reports_in_sync_when_auto_matched_tracks_are_live(db, capsys, monkeypatch):
    _linked_playlist(db, {"307819222", "222"}, monkeypatch)
    rc = handle_diff(Namespace(playlist="Native Tongues", platform="tidal"), db)
    out = capsys.readouterr().out
    assert rc == 0
    assert "Would push" not in out
    assert "In sync" in out


def test_diff_flags_track_missing_from_platform(db, capsys, monkeypatch):
    # Only one of the two mapped tracks is actually live -> the other would push.
    _linked_playlist(db, {"307819222"}, monkeypatch)
    rc = handle_diff(Namespace(playlist="Native Tongues", platform="tidal"), db)
    out = capsys.readouterr().out
    assert rc == 0
    assert "Would push (1 tracks)" in out
