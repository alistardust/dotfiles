"""Pin command: manage track pins for sequencer constraints."""
import sys

from tuneshift.db import Database


def handle_pin(args, db: Database) -> int:
    """Manage track pins (opener, closer, adjacency groups)."""
    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        print(f"Playlist not found: {args.playlist}", file=sys.stderr)
        return 1

    if getattr(args, "list_pins", False):
        return _list_pins(db, playlist)

    if getattr(args, "remove", None):
        return _remove_pin(db, playlist, args.remove)

    if getattr(args, "opener", None):
        return _set_position_pin(db, playlist, args.opener, "opener")

    if getattr(args, "closer", None):
        return _set_position_pin(db, playlist, args.closer, "closer")

    if getattr(args, "adjacent", None):
        return _set_adjacency(db, playlist, args.adjacent, getattr(args, "group", None))

    print("Specify --opener, --closer, --adjacent, --remove, or --list.", file=sys.stderr)
    return 1


def _find_track_in_playlist(db: Database, playlist, title: str):
    """Find a track in a playlist by partial title match."""
    tracks = db.get_playlist_tracks(playlist.id)
    title_lower = title.lower()
    matches = [t for t in tracks if title_lower in t.title.lower()]
    if not matches:
        print(f'  Track not found: "{title}"', file=sys.stderr)
        return None
    if len(matches) > 1:
        exact = [t for t in matches if t.title.lower() == title_lower]
        if len(exact) == 1:
            return exact[0]
        print(f'  Ambiguous match for "{title}":', file=sys.stderr)
        for t in matches[:5]:
            print(f"    - {t.title} - {t.artist}", file=sys.stderr)
        return None
    return matches[0]


def _set_position_pin(db: Database, playlist, title: str, pin_type: str) -> int:
    """Pin a track as opener or closer."""
    track = _find_track_in_playlist(db, playlist, title)
    if not track:
        return 1

    # Remove any existing pin of this type for the playlist
    existing_pins = db.get_pins(playlist.id)
    for pin in existing_pins:
        if pin.pin_type == pin_type:
            db.remove_pin(playlist.id, pin.track_id)

    db.set_pin(playlist.id, track.id, pin_type)
    print(f'Pinned "{track.title}" as {pin_type} in "{playlist.name}"')
    return 0


def _set_adjacency(db: Database, playlist, titles: list[str], group_name: str | None) -> int:
    """Pin tracks as an adjacency group."""
    tracks = []
    for title in titles:
        track = _find_track_in_playlist(db, playlist, title)
        if not track:
            return 1
        tracks.append(track)

    group_id = group_name or f"adj-{tracks[0].id}"

    for order, track in enumerate(tracks):
        # Remove any existing pin for this track first
        db.remove_pin(playlist.id, track.id)
        db.set_pin(playlist.id, track.id, "anchor", group_id=group_id, group_order=order)

    track_names = " -> ".join(f'"{t.title}"' for t in tracks)
    print(f'Pinned adjacency group "{group_id}": {track_names}')
    return 0


def _remove_pin(db: Database, playlist, title: str) -> int:
    """Remove a pin from a track."""
    track = _find_track_in_playlist(db, playlist, title)
    if not track:
        return 1
    db.remove_pin(playlist.id, track.id)
    print(f'Removed pin from "{track.title}" in "{playlist.name}"')
    return 0


def _list_pins(db: Database, playlist) -> int:
    """List all pins for a playlist."""
    pins = db.get_pins(playlist.id)
    if not pins:
        print(f'No pins set for "{playlist.name}"')
        return 0

    print(f'Pins for "{playlist.name}":')
    tracks_map = {t.id: t for t in db.get_playlist_tracks(playlist.id)}

    for pin in pins:
        track = tracks_map.get(pin.track_id)
        name = f"{track.title} - {track.artist}" if track else f"(track {pin.track_id})"
        if pin.pin_type in ("opener", "closer"):
            print(f"  {pin.pin_type}: {name}")
        elif pin.pin_type == "anchor":
            print(f"  anchor [{pin.group_id}#{pin.group_order}]: {name}")

    return 0
