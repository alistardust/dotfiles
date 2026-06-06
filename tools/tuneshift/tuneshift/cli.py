"""Command-line entry point for tuneshift."""

import argparse
import sys

from tuneshift import __version__
from tuneshift.db import Database


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="tuneshift",
        description="Canonical playlist manager with cross-platform distribution",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--db", type=str, default=None,
        help="Path to database file (default: auto-detect)",
    )

    sub = parser.add_subparsers(dest="command")

    # ingest
    p_ingest = sub.add_parser("ingest", help="Import a playlist from a platform")
    p_ingest.add_argument("platform", choices=["tidal", "spotify", "ytmusic"])
    p_ingest.add_argument("playlist_id", help="Platform-specific playlist ID or URL")

    # sync
    p_sync = sub.add_parser("sync", help="Reconcile and push playlist to platform")
    p_sync.add_argument("playlist", nargs="?", help="Playlist name")
    p_sync.add_argument("platform", nargs="?", help="Target platform")
    p_sync.add_argument("--all", action="store_true", help="Sync all playlists")
    p_sync.add_argument("--reconcile", action="store_true", help="Force re-reconciliation")
    p_sync.add_argument("--auto", action="store_true", help="Accept all best matches without prompting")

    # diff
    p_diff = sub.add_parser("diff", help="Show what would change on sync")
    p_diff.add_argument("playlist", help="Playlist name")
    p_diff.add_argument("platform", nargs="?", help="Target platform")

    # add
    p_add = sub.add_parser("add", help="Add a track to a playlist")
    p_add.add_argument("playlist", help="Playlist name (created if new)")
    p_add.add_argument("title", help="Track title")
    p_add.add_argument("artist", help="Artist name")
    p_add.add_argument("--album", help="Album name")

    # rm
    p_rm = sub.add_parser("rm", help="Remove a track from a playlist")
    p_rm.add_argument("playlist", help="Playlist name")
    p_rm.add_argument("target", help="Position number or title substring")

    # login
    p_login = sub.add_parser("login", help="Authenticate with a platform")
    p_login.add_argument("platform", choices=["tidal", "spotify", "ytmusic"])

    # status
    p_status = sub.add_parser("status", help="Show playlist status")
    p_status.add_argument("playlist", nargs="?", help="Playlist name (all if omitted)")

    # list
    sub.add_parser("list", help="List all playlists")

    # order
    p_order = sub.add_parser("order", help="Reorder playlist by energy arc")
    p_order.add_argument("playlist", help="Playlist name")
    p_order.add_argument("--arc", default="wave", help="Arc shape (default: wave)")
    p_order.add_argument("--no-sync", action="store_true", help="Skip pushing to platforms")

    # resolve
    p_resolve = sub.add_parser("resolve", help="Resolve track identity via MusicBrainz/Discogs")
    p_resolve.add_argument("playlist", nargs="?", help="Playlist name to resolve")
    p_resolve.add_argument("--track", nargs=2, metavar=("TITLE", "ARTIST"), help="Resolve single track")
    p_resolve.add_argument("--all", action="store_true", help="Resolve all unresolved tracks")
    p_resolve.add_argument("--upgrade", action="store_true", help="Re-resolve tracks below CONFIRMED")
    p_resolve.add_argument("--force", action="store_true", help="Re-resolve all tracks (requires --upgrade)")
    p_resolve.add_argument("--status", action="store_true", help="Show resolution statistics")
    p_resolve.add_argument("--verbose", "-v", action="store_true", help="Show skipped tracks")

    # import-text
    p_import_text = sub.add_parser("import-text", help="Import playlist from a text file")
    p_import_text.add_argument("file", help="Path to playlist text file")
    p_import_text.add_argument("--name", help="Override playlist name")
    p_import_text.add_argument("--force", action="store_true", help="Overwrite existing playlist")

    # enrich
    p_enrich = sub.add_parser("enrich", help="Fetch audio metadata (BPM, key) from platform")
    p_enrich.add_argument("playlist", help="Playlist name")
    p_enrich.add_argument("--platform", default="tidal", help="Source platform (default: tidal)")

    # Shell completions via shtab
    try:
        import shtab
        shtab.add_argument_to(parser)
    except ImportError:
        pass

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the tuneshift CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    from pathlib import Path
    db_path = Path(args.db) if args.db else None
    db = Database(db_path)

    try:
        if args.command == "ingest":
            from tuneshift.commands.ingest_cmd import handle_ingest
            return handle_ingest(args, db)
        elif args.command == "sync":
            from tuneshift.commands.sync_cmd import handle_sync
            return handle_sync(args, db)
        elif args.command == "diff":
            from tuneshift.commands.diff_cmd import handle_diff
            return handle_diff(args, db)
        elif args.command == "add":
            from tuneshift.commands.add_cmd import handle_add
            return handle_add(args, db)
        elif args.command == "rm":
            from tuneshift.commands.rm_cmd import handle_rm
            return handle_rm(args, db)
        elif args.command == "login":
            from tuneshift.commands.login_cmd import handle_login
            return handle_login(args, db)
        elif args.command == "status":
            from tuneshift.commands.status_cmd import handle_status
            return handle_status(args, db)
        elif args.command == "list":
            from tuneshift.commands.status_cmd import handle_list
            return handle_list(args, db)
        elif args.command == "order":
            from tuneshift.commands.order_cmd import handle_order
            return handle_order(args, db)
        elif args.command == "resolve":
            from tuneshift.commands.resolve import run_resolve
            run_resolve(args, db)
            return 0
        elif args.command == "import-text":
            from tuneshift.commands.import_text_cmd import handle_import_text
            return handle_import_text(args, db)
        elif args.command == "enrich":
            from tuneshift.commands.enrich_cmd import handle_enrich
            return handle_enrich(args, db)
        else:
            parser.print_help()
            return 1
    finally:
        db.close()

