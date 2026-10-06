"""The single place a platform client is constructed.

Every client is wrapped so that the four mutating protocol methods ask for
push authority before they reach a platform. Guarding at construction rather
than at each call site means a mutating call written next year is covered the
day it is written, without anyone remembering to add a check.

Reads are forwarded untouched. A library with no push authority is still fully
usable for searching, diffing and reporting; only writes refuse.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, cast

from tuneshift.platforms.write_guard import require_push_authority

if TYPE_CHECKING:
    from tuneshift.platforms.protocol import MusicPlatformClient

MUTATING_METHODS = frozenset(
    {
        "create_playlist",
        "add_tracks",
        "remove_tracks_by_positions",
        "replace_playlist_tracks",
    }
)
"""The protocol methods that change state on a live platform.

Kept in one place so a new mutator added to
:class:`~tuneshift.platforms.protocol.MusicPlatformClient` is a one-line
change here rather than a new unguarded path.
"""


class _GuardedClient:
    """Forwards everything, and refuses mutations without push authority.

    Refusal happens when the method is called, not when it is looked up, so
    ``hasattr`` and other introspection behave normally.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if name not in MUTATING_METHODS or not callable(attr):
            return attr

        @functools.wraps(attr)
        def guarded(*args: Any, **kwargs: Any) -> Any:
            require_push_authority()
            return attr(*args, **kwargs)

        return guarded

    def __repr__(self) -> str:
        return f"<guarded {self._inner!r}>"


def guard_client(client: Any) -> MusicPlatformClient:
    """Wrap an already-constructed client in the push guard."""
    return cast("MusicPlatformClient", _GuardedClient(client))


def load_client(platform_name: str) -> MusicPlatformClient | None:
    """Construct a guarded client for ``platform_name``, or None if unknown.

    Imports are deferred per platform so a missing optional SDK only breaks the
    platform that needs it.
    """
    if platform_name == "tidal":
        from tuneshift.platforms.tidal import TidalClient

        return guard_client(TidalClient())
    if platform_name == "spotify":
        from tuneshift.platforms.spotify import SpotifyClient

        return guard_client(SpotifyClient())
    if platform_name == "ytmusic":
        from tuneshift.platforms.ytmusic import YTMusicClient

        return guard_client(YTMusicClient())
    return None
