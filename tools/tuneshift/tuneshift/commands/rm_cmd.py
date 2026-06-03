"""Remove command: remove a track from a playlist."""
import sys

from tuneshift.db import Database


def handle_rm(args, db: Database) -> int:
    """Remove a track from a playlist by position or title match."""
    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        print(f"Playlist not found: {args.playlist}", file=sys.stderr)
        return 1

    target = args.target

    # Try as position number first
    try:
        position = int(target)
        db.remove_playlist_track_by_position(playlist.id, position)
        print(f"Removed track at position {position} from \"{playlist.name}\"")
        return 0
    except ValueError:
        pass

    # Match by title
    tracks = db.get_playlist_tracks(playlist.id)
    target_lower = target.lower()
    matches = [(i + 1, t) for i, t in enumerate(tracks) if target_lower in t.title.lower()]

    if not matches:
        print(f"No track matching \"{target}\" in \"{playlist.name}\"", file=sys.stderr)
        return 1

    if len(matches) == 1:
        pos, track = matches[0]
        db.remove_playlist_track_by_position(playlist.id, pos)
        print(f"Removed \"{track.title}\" (position {pos}) from \"{playlist.name}\"")
        return 0

    # Multiple matches: show and ask
    print(f"Multiple matches for \"{target}\":")
    for pos, track in matches:
        print(f"  {pos}. {track.title} - {track.artist}")
    choice = input("Remove which position? ").strip()
    try:
        pos = int(choice)
        db.remove_playlist_track_by_position(playlist.id, pos)
        print(f"Removed track at position {pos}")
        return 0
    except ValueError:
        print("Cancelled.", file=sys.stderr)
        return 1
