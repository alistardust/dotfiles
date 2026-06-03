"""Order command: sequence a playlist by energy arc."""
import sys

from tuneshift.db import Database


def handle_order(args, db: Database) -> int:
    """Reorder a playlist using the sequencer."""
    from tuneshift.sequencer import sequence_playlist

    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        print(f"Playlist not found: {args.playlist}", file=sys.stderr)
        return 1

    tracks = db.get_playlist_tracks(playlist.id)
    if not tracks:
        print(f'Playlist "{playlist.name}" is empty.')
        return 0

    track_ids = [track.id for track in tracks if track.id is not None]
    arc = getattr(args, "arc", "wave")

    reordered = sequence_playlist(db, track_ids, arc=arc)
    db.set_playlist_tracks(playlist.id, reordered)

    print(f'Reordered "{playlist.name}" ({len(reordered)} tracks, arc={arc})')
    return 0
