"""Add command: add a track to a playlist."""
import sys

from tuneshift.db import Database
from tuneshift.models import Track


def handle_add(args, db: Database) -> int:
    """Add a track to a playlist."""
    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        # Create the playlist
        playlist_id = db.create_playlist(args.playlist)
        print(f"Created playlist: {args.playlist}")
    else:
        playlist_id = playlist.id

    # Find or create canonical track
    existing = db.find_track(args.title, args.artist, getattr(args, "album", None))
    if existing:
        track_id = existing.id
    else:
        track = Track(
            title=args.title,
            artist=args.artist,
            album=getattr(args, "album", None),
        )
        track_id = db.add_track(track)

    # Find next position
    tracks = db.get_playlist_tracks(playlist_id)
    position = len(tracks) + 1

    db.add_track_to_playlist(playlist_id, track_id, position)
    print(f"Added \"{args.title}\" by {args.artist} to \"{args.playlist}\" at position {position}")
    return 0
