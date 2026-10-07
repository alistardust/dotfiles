"""Remove command: remove a track from a playlist and sync to platforms."""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tuneshift.db import Database


def _primary_db_path() -> Path | None:
    """Return the recorded primary database path, or None if unregistered."""
    from tuneshift.persistence.primary import get_primary_db

    return get_primary_db()


def _is_primary_db(active: Path) -> bool:
    """Whether ``active`` is the recorded primary database."""
    from tuneshift.persistence.primary import is_primary_db

    return is_primary_db(active)


def _resolve_target(args, tracks):
    """Resolve the CLI target to a ``(position, track)`` pair, or an exit code.

    A bare number used to be matched against titles first, so a positional
    intent could silently hit a track whose title merely contained that
    digit. An ambiguous bare number is now refused.
    """
    target = args.target
    want_position = getattr(args, "position", False)
    want_title = getattr(args, "title", False)

    title_matches = [
        (i + 1, t) for i, t in enumerate(tracks) if target.lower() in t.title.lower()
    ]

    try:
        position = int(target)
    except ValueError:
        position = None

    if want_position and position is None:
        print(f'"{target}" is not a position.', file=sys.stderr)
        return 1

    if position is not None and not want_title:
        if title_matches and not want_position:
            print(
                f'Ambiguous target "{target}": it is a valid position and also '
                f"matches {len(title_matches)} title(s). "
                "Re-run with --position or --title.",
                file=sys.stderr,
            )
            return 1
        if position < 1 or position > len(tracks):
            print(
                f"Position {position} out of range (1-{len(tracks)})",
                file=sys.stderr,
            )
            return 1
        return position, tracks[position - 1]

    if not title_matches:
        print(f'No track matching "{target}"', file=sys.stderr)
        return 1

    if len(title_matches) == 1:
        return title_matches[0]

    print(f'Multiple matches for "{target}":')
    offered = dict(title_matches)
    for pos, track in title_matches:
        print(f"  {pos}. {track.title} - {track.artist}")
    choice = input("Remove which position? ").strip()
    try:
        pos = int(choice)
    except ValueError:
        print("Cancelled.", file=sys.stderr)
        return 1
    # Only an offered position is accepted. Indexing the full track list here
    # meant "0" selected tracks[-1], the LAST track, and "-1" selected another
    # bystander: negative indices wrap instead of raising IndexError. That is
    # the same class of failure as the numeric-target bug, a number quietly
    # selecting a track the user never named, and this path then pushes the
    # removal live.
    if pos not in offered:
        print(
            f"{pos} is not one of the offered positions "
            f"({', '.join(str(p) for p in offered)}).",
            file=sys.stderr,
        )
        return 1
    return pos, offered[pos]


def handle_rm(args, db: Database) -> int:
    """Remove a track from a playlist by position or title match."""
    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        print(f"Playlist not found: {args.playlist}", file=sys.stderr)
        return 1

    tracks = db.get_playlist_tracks(playlist.id)
    resolved = _resolve_target(args, tracks)
    if isinstance(resolved, int):
        return resolved
    position, track = resolved

    platforms = db.get_linked_platforms(playlist.id)
    label = f'"{track.title} - {track.artist}" (position {position})'

    if getattr(args, "dry_run", False):
        print(f'Dry run: would remove {label} from "{playlist.name}"')
        for platform_name in platforms:
            print(f"  would push removal to {platform_name}")
        if not platforms:
            print("  no linked platforms; local removal only")
        return 0

    # A copied database is not a sandbox: platform_playlists travels
    # with the copy, so a push from it reaches the same live playlist.
    if platforms and not getattr(args, "allow_nonprimary_push", False):
        active = Path(db.path).resolve()
        if not _is_primary_db(active):
            if _primary_db_path() is None:
                # Unregistered is not the same as "this is a copy", and the
                # remedy must not be the push override: a guard that answers
                # every refusal with --allow-nonprimary-push teaches people to
                # leave it on, which is precisely when a copy bites.
                print(
                    "Refusing to push: no primary database is registered, so "
                    "there is no way to tell this from a copy. Register the "
                    "real one once with: tuneshift primary --set <path>",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Refusing to push: {active} is not the primary database "
                    f"({_primary_db_path()}). Platform IDs travel with a "
                    "copied database, so this would mutate the live playlist. "
                    "Re-run with --allow-nonprimary-push if that is genuinely "
                    "what you want.",
                    file=sys.stderr,
                )
            return 1

    if platforms and not getattr(args, "yes", False):
        print(f'About to remove {label} from "{playlist.name}"')
        print(f"  and push that removal live to: {', '.join(platforms)}")
        if input("Proceed? [y/N] ").strip().lower() not in {"y", "yes"}:
            print("Cancelled.", file=sys.stderr)
            return 1

    had_failure = _remove_and_sync(db, playlist, track, position)
    return 1 if had_failure else 0


@dataclass(frozen=True)
class _PlatformLink:
    """A logged-in client and the remote playlist it is pointed at."""

    name: str
    client: Any
    playlist_id: str


@dataclass(frozen=True)
class _RemovalTarget:
    """What is known locally about the track being removed.

    Captured before the local delete, because removing the last copy of a track
    also deletes its pin row, and the pin is what vetoes guessing.
    """

    title: str
    artist: str
    playlist_name: str
    is_pinned: bool
    recorded_ids: dict[str, list[str]]

    @property
    def label(self) -> str:
        return f'"{self.title} - {self.artist}"'


def _norm(value: str | None) -> str:
    """Casefold and collapse whitespace for comparison."""
    return " ".join((value or "").split()).casefold()


def _recorded_platform_ids(
    db: Database, playlist_id: int, track_id: int, platform: str
) -> list[str]:
    """Platform ids recorded for this track, most specific first.

    Mirrors the identity precedence in ``planapply.rematch``: a per-playlist
    override describes what this playlist points at, and the library-wide
    mapping is the default. Both are kept because either can legitimately be
    the id sitting remotely: ``order`` pushes the library id while ``apply``
    pushes the override. Both name a verified release of this same track, so
    matching either can never reach a different song.
    """
    ids: list[str] = []
    override = db.get_playlist_track_mapping(playlist_id, track_id, platform)
    if override and override["platform_track_id"]:
        ids.append(str(override["platform_track_id"]).strip())
    mapping = db.get_platform_mapping(track_id, platform)
    if mapping and mapping.platform_track_id:
        library_id = str(mapping.platform_track_id).strip()
        if library_id and library_id not in ids:
            ids.append(library_id)
    return [i for i in ids if i]


def _match_by_id(remote: list[Any], recorded_ids: list[str]) -> list[int]:
    """Positions holding a recorded id, taking the most specific id that hits."""
    for wanted in recorded_ids:
        hits = [
            i
            for i, pt in enumerate(remote)
            if str(getattr(pt, "platform_id", "") or "").strip() == wanted
        ]
        if hits:
            return hits
    return []


def _match_exactly(remote: list[Any], target: _RemovalTarget) -> list[int]:
    """Positions whose title AND artist match exactly.

    Artist is part of the predicate because title alone cannot separate the
    many songs that share a name across different artists.
    """
    title, artist = _norm(target.title), _norm(target.artist)
    return [
        i
        for i, pt in enumerate(remote)
        if _norm(getattr(pt, "title", None)) == title
        and _norm(getattr(pt, "artist", None)) == artist
    ]


def _plausible_candidates(remote: list[Any], target: _RemovalTarget) -> list[int]:
    """Positions that could be another release of the same song.

    Deliberately wider than ``_match_exactly``: that predicate decides what to
    delete and must be strict, this one decides whether to worry and should
    not miss "Blue (2019 Remaster)" when the recorded release of "Blue" has
    gone. Its only failure mode is a refusal where the track was genuinely
    already gone, never a wrong deletion.
    """
    title, artist = _norm(target.title), _norm(target.artist)
    hits = []
    for i, pt in enumerate(remote):
        if _norm(getattr(pt, "artist", None)) != artist:
            continue
        other = _norm(getattr(pt, "title", None))
        if other == title or title in other or other in title:
            hits.append(i)
    return hits


def _resolve_hint(target: _RemovalTarget) -> str:
    return f'Resolve it first: tuneshift resolve "{target.playlist_name}"'


def _sync_removal(
    link: _PlatformLink, remote: list[Any], target: _RemovalTarget
) -> bool:
    """Remove this track's remote counterpart. Returns False on a refusal.

    This used to re-find the track by title *containment* and delete the
    first hit, so removing "Blue" could delete "Blue Moon". Identity now
    comes from the recorded platform id, and anything less certain than an
    exact match refuses rather than guesses.
    """
    recorded_ids = target.recorded_ids.get(link.name, [])

    if recorded_ids:
        hits = _match_by_id(remote, recorded_ids)
    elif target.is_pinned:
        print(
            f"  {link.name}: refusing to remove - {target.label} is pinned in "
            "this playlist but has no recorded platform id, so there is no way "
            f"to tell which release the pin protects. {_resolve_hint(target)}",
            file=sys.stderr,
        )
        return False
    else:
        hits = _match_exactly(remote, target)
        if len(hits) > 1:
            print(
                f"  {link.name}: refusing to remove - {len(hits)} remote tracks "
                f"match {target.label} exactly and no platform id is recorded "
                f"for it. {_resolve_hint(target)}",
                file=sys.stderr,
            )
            return False

    if hits:
        # Remove only ONE platform occurrence to mirror the single local
        # removal. Both copies share the same platform id, so which one is
        # removed does not matter; removing all would wipe the track.
        link.client.remove_tracks_by_positions(link.playlist_id, hits[:1])
        chosen = remote[hits[0]]
        chosen_artist = getattr(chosen, "artist", "") or ""
        print(f'  {link.name}: removed "{chosen.title} - {chosen_artist}"')
        return True

    candidates = _plausible_candidates(remote, target)
    if candidates:
        other = remote[candidates[0]]
        print(
            f"  {link.name}: refusing to remove - the recorded release of "
            f"{target.label} is not in the remote playlist, but "
            f'{len(candidates)} similar track(s) are (e.g. "{other.title}"). '
            "The remote may hold a different version; check it by hand.",
            file=sys.stderr,
        )
        return False

    print(f"  {link.name}: already absent (nothing matching {target.label})")
    return True


def _remove_and_sync(db: Database, playlist, track, position: int) -> bool:
    """Remove from DB and sync removal to all linked platforms.

    Returns True if any platform operation failed.
    """
    from tuneshift.commands.ingest_cmd import _load_client

    platforms = db.get_linked_platforms(playlist.id)
    # Read identity BEFORE the local delete: removing the last copy of a track
    # also drops its pin row, and both the pin and the mappings are what decide
    # whether the remote counterpart can be named with certainty.
    target = _RemovalTarget(
        title=track.title,
        artist=track.artist,
        playlist_name=playlist.name,
        is_pinned=any(pin.track_id == track.id for pin in db.get_pins(playlist.id)),
        recorded_ids={
            name: _recorded_platform_ids(db, playlist.id, track.id, name)
            for name in platforms
        },
    )

    # `position` is the 1-based ordinal in the ordered track list, not the
    # stored playlist_tracks.position value. Map it to the real stored position so
    # we delete ONLY the chosen row: the same track_id may appear at several
    # positions, and a track_id-wide delete would silently wipe every copy.
    ordered = db.get_playlist_track_positions(playlist.id)
    stored_position = ordered[position - 1]
    db.remove_playlist_track_by_position(playlist.id, stored_position)
    print(
        f'Removed "{track.title} - {track.artist}" (position {position}) from "{playlist.name}"'  # noqa: E501
    )

    # Auto-reorder if enabled
    cfg = db.get_playlist_reorder_config(playlist.id)
    if cfg and cfg[0]:
        from tuneshift.sequencer.optimizer import sequence_playlist

        arc = cfg[1] or "wave"
        sequence_playlist(db, playlist.id, arc=arc)

    # Sync removal to linked platforms
    failures = False
    for platform_name in platforms:
        client = _load_client(platform_name)
        if not client or not client.load_session():
            print(f"  {platform_name}: skipped (not logged in)")
            continue

        platform_playlist_id = db.get_platform_playlist_id(playlist.id, platform_name)
        if not platform_playlist_id:
            print(f"  {platform_name}: skipped (no linked playlist)")
            continue

        link = _PlatformLink(
            name=platform_name, client=client, playlist_id=platform_playlist_id
        )
        try:
            remote = client.get_playlist_tracks(platform_playlist_id)
            if not _sync_removal(link, remote, target):
                failures = True
        except Exception as exc:  # noqa: BLE001
            print(f"  {platform_name}: sync failed ({exc})", file=sys.stderr)
            failures = True

    return failures
