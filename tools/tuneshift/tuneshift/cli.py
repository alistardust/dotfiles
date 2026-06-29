"""Command-line entry point for tuneshift."""

import argparse
import os
import sys

from tuneshift import TuneShiftError, __version__
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
    p_add.add_argument("--replace", help="Title of track to replace (inherits position and pins)")

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
    p_order.add_argument("--weights", help="Weight preset name or JSON dict")
    p_order.add_argument("--dry-run", action="store_true", help="Show proposed order without applying")
    p_order.add_argument("--no-sync", action="store_true", help="Skip pushing to platforms")
    p_order.add_argument("--auto-on", action="store_true", help="Enable auto-reorder on sync")
    p_order.add_argument("--auto-off", action="store_true", help="Disable auto-reorder on sync")

    # pin
    p_pin = sub.add_parser("pin", help="Pin tracks as openers, closers, or adjacency groups")
    p_pin.add_argument("playlist", help="Playlist name")
    p_pin.add_argument("--opener", metavar="TITLE", help="Pin track as opener")
    p_pin.add_argument("--closer", metavar="TITLE", help="Pin track as closer")
    p_pin.add_argument("--position", nargs=2, metavar=("INDEX", "TITLE"), help="Pin track to specific position (0-based)")
    p_pin.add_argument("--adjacent", nargs="+", metavar="TITLE", help="Pin tracks as adjacent group (in order)")
    p_pin.add_argument("--group", metavar="NAME", help="Name for adjacency group (default: auto)")
    p_pin.add_argument("--moment", metavar="TITLE", help="Pin track as a narrative moment (placed at climax)")
    p_pin.add_argument("--remove", metavar="TITLE", help="Remove pin from track")
    p_pin.add_argument("--list", action="store_true", dest="list_pins", help="Show current pins")

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
    p_enrich = sub.add_parser("enrich", help="Fetch audio metadata and/or classify tracks")
    p_enrich.add_argument("playlist", help="Playlist name")
    p_enrich.add_argument("--platform", default=None, help="Source platform for audio metadata (BPM, key)")
    p_enrich.add_argument("--classify", action="store_true", help="Run LLM classification for narrative fields")
    p_enrich.add_argument("--reclassify", action="store_true", help="Force re-classify all tracks (overwrites existing)")
    p_enrich.add_argument("--model", help="Override LLM model for classification")

    # narrative
    p_narrative = sub.add_parser("narrative", help="Set or show the intended narrative arc for a playlist")
    p_narrative.add_argument("playlist", help="Playlist name")
    p_narrative.add_argument("text", nargs="?", help="Narrative description (omit to show current)")
    p_narrative.add_argument("-f", "--file", help="Read narrative from file")
    p_narrative.add_argument("--clear", action="store_true", help="Remove narrative")

    # export
    p_export = sub.add_parser("export", help="Export playlist to file")
    p_export.add_argument("playlist", help="Playlist name")
    p_export.add_argument("-f", "--format", default="text",
                          choices=["text", "csv", "json", "soundiiz", "tunemymusic"],
                          help="Output format (default: text)")
    p_export.add_argument("-o", "--output", default="-", help="Output file (default: stdout)")

    # map
    p_map = sub.add_parser("map", help="Manually map a track to a platform ID")
    p_map.add_argument("playlist", help="Playlist name")
    p_map.add_argument("title", help="Track title (substring match)")
    p_map.add_argument("--tidal", help="Tidal track ID")
    p_map.add_argument("--ytmusic", help="YouTube Music video ID")
    p_map.add_argument("--verify", action="store_true", help="Verify ID exists on platform")

    # unmap
    p_unmap = sub.add_parser("unmap", help="Remove a manual platform mapping")
    p_unmap.add_argument("playlist", help="Playlist name")
    p_unmap.add_argument("title", help="Track title (substring match)")
    p_unmap.add_argument("--tidal", action="store_true", help="Remove Tidal mapping")
    p_unmap.add_argument("--ytmusic", action="store_true", help="Remove YouTube Music mapping")

    # goal
    p_goal = sub.add_parser("goal", help="Set or show playlist goal/theme")
    p_goal.add_argument("playlist", help="Playlist name")
    p_goal.add_argument("text", nargs="?", help="Goal text to set")
    p_goal.add_argument("--clear", action="store_true", help="Clear the goal")

    # weights
    p_weights = sub.add_parser("weights", help="Manage sequencing weight presets")
    p_weights.add_argument("action", nargs="?", default="list", choices=["list", "set", "show"])
    p_weights.add_argument("playlist", nargs="?", help="Playlist name")
    p_weights.add_argument("--preset", help="Named preset to apply")
    p_weights.add_argument("values", nargs="*", help="dimension=value pairs")

    # curate
    p_curate = sub.add_parser("curate", help="Curate playlist (trim/analyze/fill)")
    p_curate.add_argument("playlist", help="Playlist name")
    p_curate.add_argument("mode", choices=["trim", "analyze", "fill"], help="Curation mode")
    p_curate.add_argument("--dry-run", action="store_true", help="Preview without applying")
    p_curate.add_argument("--strategy", default="quick", choices=["quick", "hybrid", "deep"], help="Curation strategy")
    p_curate.add_argument("--target-tracks", type=int, help="Target track count for trim")
    p_curate.add_argument("--hard-limit", type=int, help="Hard limit track count")

    # prefs
    p_prefs = sub.add_parser("prefs", help="Manage global version preferences")
    p_prefs.add_argument("action", choices=["show", "set"], help="Show or set preferences")
    p_prefs.add_argument("key", nargs="?", help="Preference key (section.name)")
    p_prefs.add_argument("value", nargs="?", help="Value to set")
    p_prefs.add_argument("--config-path", help="Path to preferences file")

    # share
    p_share = sub.add_parser("share", help="Generate shareable links for a playlist")
    p_share.add_argument("name", help="Playlist name")
    p_share.add_argument(
        "--format", choices=["plain", "markdown", "slack", "discord", "urls"],
        default="plain", help="Output format (default: plain)",
    )

    # link
    p_link = sub.add_parser("link", help="Link platform playlist IDs (auto-discover or manual)")
    p_link.add_argument("platform", choices=["tidal", "spotify", "ytmusic"])
    p_link.add_argument("name", nargs="?", help="Playlist name (for manual link)")
    p_link.add_argument("url", nargs="?", help="Platform URL or playlist ID (for manual link)")
    p_link.add_argument("--quiet", "-q", action="store_true", help="Suppress 'not found' messages")

    # compose
    p_compose = sub.add_parser("compose", help="Narrative-driven playlist composition")
    p_compose.add_argument("playlist", help="Playlist name")
    p_compose.add_argument("--analyze", action="store_true", help="Analyze only (gap report)")
    p_compose.add_argument("--reorder", action="store_true", help="Reorder only")
    p_compose.add_argument("--fill-gaps", action="store_true", help="Find candidates for gaps")
    p_compose.add_argument("--dry-run", action="store_true", help="Preview without applying")
    p_compose.add_argument("--apply", action="store_true", help="Apply changes to playlist")

    # concept
    p_concept = sub.add_parser("concept", help="Set or show playlist concept/theme")
    p_concept.add_argument("playlist", help="Playlist name")
    p_concept.add_argument("--theme", help="Playlist theme")
    p_concept.add_argument("--require", help="Add a hard rule")
    p_concept.add_argument("--prefer", help="Add a soft rule")
    p_concept.add_argument("--show", action="store_true", help="Show current concept")
    p_concept.add_argument("--clear", action="store_true", help="Clear concept")

    # review
    p_review = sub.add_parser("review", help="Review playlist for concept compliance")
    p_review.add_argument("playlist", help="Playlist name")
    p_review.add_argument("--fix", action="store_true", help="Remove tracks that violate hard rules")

    # config
    p_config = sub.add_parser("config", help="Configure TuneShift settings")
    p_config.add_argument("key", nargs="?", help="Config key (e.g., anthropic-key, openai-key, llm-backend)")
    p_config.add_argument("value", nargs="?", help="Config value")
    p_config.add_argument("--show", action="store_true", help="Show current LLM configuration")

    # batch
    p_batch = sub.add_parser("batch", help="Batch playlist operations (plan/apply model)")
    p_batch.add_argument("playlist", nargs="?", help="Playlist name")
    p_batch.add_argument("--dedupe", action="store_true", help="Flag artists with more than --cap tracks")
    p_batch.add_argument("--cap", type=int, default=1, help="Max tracks per artist for --dedupe (default: 1)")
    p_batch.add_argument("--rm-artist", help="Remove all tracks by an artist (including features)")
    p_batch.add_argument("--rm", action="append", help="Remove a track (repeatable: --rm 'Title - Artist')")
    p_batch.add_argument("--add", action="append", help="Add a track (repeatable: --add 'Title - Artist')")
    p_batch.add_argument("--review-findings", action="store_true", help="Plan fixes from concept review")
    p_batch.add_argument("--sweep-banned", action="store_true", help="Sweep for banned artists")
    p_batch.add_argument("--split", help="Split matching tracks into a new playlist (name)")
    p_batch.add_argument("--filter", action="append", help="Filter for --split (artist:X, vibe:X, energy:<0.4)")
    p_batch.add_argument("--rebuild", action="store_true", help="Concept-driven rebuild (review + fill)")
    p_batch.add_argument("--count", type=int, default=50, help="Target track count for --rebuild")
    p_batch.add_argument("--fresh", action="store_true", help="Rebuild from scratch (clear all first)")
    p_batch.add_argument("--structure", action="store_true", help="Retroactive narrative structuring")
    p_batch.add_argument("--narrative-file", help="Narrative file for --structure (user-provided sections)")
    p_batch.add_argument("--plan", action="store_true", help="Generate plan (no changes)")
    p_batch.add_argument("--plan-file", help="Load operations from a plan file")
    p_batch.add_argument("--from-stdin", action="store_true", help="Read operations from stdin")
    p_batch.add_argument("--show-plan", action="store_true", help="Show current plan")
    p_batch.add_argument("--apply", action="store_true", help="Apply current plan")
    p_batch.add_argument("--discard", action="store_true", help="Discard current plan")
    p_batch.add_argument("--undo", action="store_true", help="Undo a batch (operation-based)")
    p_batch.add_argument("--id", type=int, help="History ID for --undo")
    p_batch.add_argument("--history", nargs="?", const=True, help="Show batch history")
    p_batch.add_argument("--interactive", action="store_true", help="Walk through decisions one at a time")

    # ban
    p_ban = sub.add_parser("ban", help="Manage the global banned artist list")
    p_ban.add_argument("artist", nargs="?", help="Artist name to ban")
    p_ban.add_argument("--reason", help="Reason for banning")
    p_ban.add_argument("--list", action="store_true", help="List all banned artists")
    p_ban.add_argument("--remove", help="Remove an artist from the ban list")

    # merge (separate command since it takes multiple playlist args)
    p_merge = sub.add_parser("merge", help="Merge playlists into one")
    p_merge.add_argument("sources", nargs="+", help="Source playlist names")
    p_merge.add_argument("--into", required=True, help="Target playlist name")
    p_merge.add_argument("--plan", action="store_true", help="Generate plan (no changes)")
    p_merge.add_argument("--delete-sources", action="store_true", help="Delete source playlists after merge")

    # audit
    p_audit = sub.add_parser("audit", help="Full playlist health audit (all checks)")
    p_audit.add_argument("playlist", nargs="?", help="Playlist name (omit for all)")
    p_audit.add_argument("--matching-only", action="store_true", help="Only check platform mapping quality")
    p_audit.add_argument("--vibes-only", action="store_true", help="Only check vibe outliers")
    p_audit.add_argument("--concept-only", action="store_true", help="Only check concept rules")
    p_audit.add_argument("--fix", action="store_true", help="Generate batch plan from findings")

    # tag / untag
    p_tag = sub.add_parser("tag", help="Tag a playlist with a collection")
    p_tag.add_argument("playlist", help="Playlist name")
    p_tag.add_argument("collection", help="Collection name")

    p_untag = sub.add_parser("untag", help="Remove a collection tag from a playlist")
    p_untag.add_argument("playlist", help="Playlist name")
    p_untag.add_argument("collection", help="Collection name")

    # collections
    p_collections = sub.add_parser("collections", help="List or manage collections")
    p_collections.add_argument("collection", nargs="?", help="Show playlists in this collection")
    p_collections.add_argument("--create", dest="create_name", help="Create a collection")
    p_collections.add_argument("--delete", dest="delete_name", help="Delete a collection")

    # folders
    p_folders = sub.add_parser("folders", help="Manage Tidal folders")
    p_folders_sub = p_folders.add_subparsers(dest="action")
    p_folders_sub.add_parser("list", help="List Tidal folders")
    p_folders_sub.add_parser("import", help="Import existing Tidal structure")
    p_fc = p_folders_sub.add_parser("create", help="Create folder on Tidal")
    p_fc.add_argument("name", help="Folder name")
    p_fr = p_folders_sub.add_parser("rename", help="Rename folder on Tidal")
    p_fr.add_argument("old_name", help="Current name")
    p_fr.add_argument("new_name", help="New name")
    p_fd = p_folders_sub.add_parser("delete", help="Delete folder on Tidal")
    p_fd.add_argument("name", help="Folder name")
    p_fm = p_folders_sub.add_parser("move", help="Assign playlist to folder")
    p_fm.add_argument("playlist", help="Playlist name")
    p_fm.add_argument("--to", required=True, help="Target folder name")
    p_fu = p_folders_sub.add_parser("unassign", help="Remove folder assignment")
    p_fu.add_argument("playlist", help="Playlist name")
    p_folders_sub.add_parser("sync", help="Push folder assignments to Tidal")
    p_folders_sub.add_parser("pull", help="Update local from Tidal state")
    p_folders_sub.add_parser("status", help="Show folder assignment status")

    # Shell completions via shtab
    try:
        import shtab
        shtab.add_argument_to(parser)
    except ImportError:
        pass

    return parser


def _handle_config(args) -> int:
    """Handle the config command."""
    import sys
    from tuneshift.sequencer.classifier import detect_backend, store_llm_key, _load_stored_key, _TOKEN_DIR

    if getattr(args, "show", False) or not args.key:
        name, backend = detect_backend()
        print("LLM Configuration:")
        if name:
            from tuneshift.sequencer.classifier import TrackClassifier
            classifier = TrackClassifier()
            print(f"  Backend: {classifier.backend_info}")
        else:
            print("  Backend: none configured")
        print()
        print(f"  Stored keys: {_TOKEN_DIR}")
        for key_name in ("anthropic", "openai"):
            stored = _load_stored_key(key_name)
            if stored:
                print(f"    {key_name}: {stored[:8]}...")
            else:
                print(f"    {key_name}: not set")
        print()
        print("  To configure: tuneshift config anthropic-key <your-key>")
        print("                tuneshift config openai-key <your-key>")
        print("                tuneshift config lastfm-key <your-key>")
        return 0

    key_map = {
        "anthropic-key": "anthropic",
        "openai-key": "openai",
        "lastfm-key": "lastfm",
    }

    if args.key not in key_map:
        print(f"Unknown config key: {args.key}", file=sys.stderr)
        print(f"Valid keys: {', '.join(key_map.keys())}", file=sys.stderr)
        return 1

    if not args.value:
        print(f"Usage: tuneshift config {args.key} <value>", file=sys.stderr)
        return 1

    backend_name = key_map[args.key]
    store_llm_key(backend_name, args.value)
    print(f"Stored {backend_name} API key in {_TOKEN_DIR / f'{backend_name}_key'}")

    # Verify it works
    name, backend = detect_backend()
    if name:
        print(f"Backend now active: {name}")
    return 0


def _handle_ban(args, db) -> int:
    """Handle the ban command."""
    import sys

    if getattr(args, "list", False):
        banned = db.get_banned_artists()
        if not banned:
            print("No banned artists.")
            return 0
        print("Banned artists:")
        for name, reason in banned:
            reason_str = f" ({reason})" if reason else ""
            print(f"  - {name}{reason_str}")
        return 0

    if getattr(args, "remove", None):
        if db.unban_artist(args.remove):
            print(f"Removed \"{args.remove}\" from ban list.")
        else:
            print(f"\"{args.remove}\" not found on ban list.", file=sys.stderr)
            return 1
        return 0

    if not args.artist:
        print("Usage: tuneshift ban <artist> [--reason <reason>]", file=sys.stderr)
        print("       tuneshift ban --list", file=sys.stderr)
        return 1

    reason = getattr(args, "reason", None)
    db.ban_artist(args.artist, reason)
    print(f"Banned \"{args.artist}\"{f' ({reason})' if reason else ''}. "
          f"Future adds will be blocked. Run --sweep-banned to check existing playlists.")
    return 0


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
        elif args.command == "pin":
            from tuneshift.commands.pin_cmd import handle_pin
            return handle_pin(args, db)
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
        elif args.command == "narrative":
            from tuneshift.commands.narrative_cmd import handle_narrative
            return handle_narrative(args, db)
        elif args.command == "export":
            from tuneshift.commands.export_cmd import handle_export
            return handle_export(args, db)
        elif args.command == "map":
            from tuneshift.commands.map_cmd import handle_map
            return handle_map(args, db)
        elif args.command == "unmap":
            from tuneshift.commands.map_cmd import handle_unmap
            return handle_unmap(args, db)
        elif args.command == "goal":
            from tuneshift.commands.goal_cmd import handle_goal
            return handle_goal(args, db)
        elif args.command == "weights":
            from tuneshift.commands.weights_cmd import handle_weights
            return handle_weights(args, db)
        elif args.command == "curate":
            from tuneshift.commands.curate_cmd import handle_curate
            return handle_curate(args, db)
        elif args.command == "prefs":
            from tuneshift.commands.prefs_cmd import handle_prefs
            return handle_prefs(args)
        elif args.command == "share":
            from tuneshift.commands.share_cmd import handle_share
            return handle_share(args, db)
        elif args.command == "link":
            from tuneshift.commands.link_cmd import handle_link
            return handle_link(args, db)
        elif args.command == "compose":
            from tuneshift.commands.compose_cmd import handle_compose
            return handle_compose(args, db)
        elif args.command == "concept":
            from tuneshift.commands.compose_cmd import handle_concept
            return handle_concept(args, db)
        elif args.command == "review":
            from tuneshift.commands.compose_cmd import handle_review
            return handle_review(args, db)
        elif args.command == "config":
            return _handle_config(args)
        elif args.command == "batch":
            from tuneshift.commands.batch_cmd import handle_batch
            return handle_batch(args, db)
        elif args.command == "ban":
            return _handle_ban(args, db)
        elif args.command == "merge":
            from tuneshift.commands.batch_cmd import handle_merge
            return handle_merge(args, db)
        elif args.command == "audit":
            from tuneshift.commands.audit_cmd import handle_audit
            return handle_audit(args, db)
        elif args.command == "tag":
            from tuneshift.commands.folders_cmd import handle_tag
            return handle_tag(args, db)
        elif args.command == "untag":
            from tuneshift.commands.folders_cmd import handle_untag
            return handle_untag(args, db)
        elif args.command == "collections":
            from tuneshift.commands.folders_cmd import handle_collections
            return handle_collections(args, db)
        elif args.command == "folders":
            from tuneshift.commands.folders_cmd import handle_folders
            return handle_folders(args, db)
        else:
            parser.print_help()
            return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except TuneShiftError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("Run with TUNESHIFT_DEBUG=1 for full traceback.", file=sys.stderr)
        if os.environ.get("TUNESHIFT_DEBUG"):
            import traceback
            traceback.print_exc()
        return 2
    finally:
        db.close()
