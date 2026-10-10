"""Ingest command: import a playlist from a streaming platform."""

import sys

from tuneshift.db import Database
from tuneshift.ingest import ingest_from_platform


def handle_ingest(args, db: Database) -> int:
    """Import a playlist from a platform into the canonical database."""
    client = _load_client(args.platform)
    if client is None:
        print(f"Unknown platform: {args.platform}", file=sys.stderr)
        return 1

    if not client.load_session():
        print(
            f"Not logged in to {args.platform}. Run: tuneshift login {args.platform}",
            file=sys.stderr,
        )
        return 1

    try:
        result = ingest_from_platform(
            db, client, args.playlist_id, replace=getattr(args, "replace", False)
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    msg = (
        f'Ingested "{result.name}" from {args.platform}: '
        f"{result.total_remote} remote tracks, {result.added_to_playlist} added"
    )
    if result.new_tracks:
        msg += f", {result.new_tracks} new to library"
    if result.kept_local_only:
        msg += f", {result.kept_local_only} local-only kept"
    if result.skipped:
        msg += f", {result.skipped} unavailable and skipped"
    print(msg)

    if result.removed_from_playlist:
        print(
            f"  Removed {result.removed_from_playlist} local-only track(s) "
            f"absent from {args.platform}, because --replace was given.",
            file=sys.stderr,
        )
    return 0


def _load_client(platform_name: str):
    """Load a platform client by name.

    Delegates to the one construction point so every client arrives
    wrapped in the push guard. Kept as a module-level name because tests
    patch it here to inject fakes.
    """
    from tuneshift.platforms.factory import load_client

    return load_client(platform_name)
