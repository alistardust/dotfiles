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
        name, total, new, skipped = ingest_from_platform(db, client, args.playlist_id)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    msg = f'Ingested "{name}" from {args.platform}: {total} tracks ({new} new)'
    if skipped:
        msg += f" ({skipped} unavailable, skipped)"
    print(msg)
    return 0


def _load_client(platform_name: str):
    """Load a platform client by name.

    Delegates to the one construction point so every client arrives
    wrapped in the push guard. Kept as a module-level name because tests
    patch it here to inject fakes.
    """
    from tuneshift.platforms.factory import load_client

    return load_client(platform_name)
