"""A platform timeout during resolution is transient, not a quarantine (BUG-4)."""

import pytest

from tuneshift.db import Database
from tuneshift.library.resolvers import PlatformResolver
from tuneshift.library.worker import ResolutionRateLimited
from tuneshift.models import Track
from tuneshift.platforms.timeout import PlatformTimeout


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


class _TimingOutClient:
    platform_name = "tidal"

    def search_track(self, query, limit=10):
        raise PlatformTimeout("stalled")

    def search_isrc(self, isrc):
        raise PlatformTimeout("stalled")

    def search_album(self, query, limit=5):
        raise PlatformTimeout("stalled")

    def get_album_tracks(self, album_id):
        raise PlatformTimeout("stalled")

    def search_artist(self, query, limit=3):
        raise PlatformTimeout("stalled")


def test_resolver_maps_platform_timeout_to_rate_limited(db):
    tid = db.insert_track(Track(title="Blinding Lights", artist="The Weeknd"))
    track = db.get_track(tid)
    resolver = PlatformResolver(db, _TimingOutClient())
    with pytest.raises(ResolutionRateLimited):
        list(resolver(track))
