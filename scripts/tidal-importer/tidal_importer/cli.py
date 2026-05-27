"""CLI entrypoint for tidal-importer."""
import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tidal-importer",
        description="Import CSV playlists into Tidal with fuzzy matching",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # reconcile subcommand
    rec_parser = subparsers.add_parser("reconcile", help="Match CSV tracks against Tidal catalog")
    rec_parser.add_argument("csv_path", type=Path, help="Path to Soundiiz CSV file")
    rec_parser.add_argument("-o", "--output", type=Path, help="Output JSON path (default: <csv>.reconciled.json)")
    rec_parser.add_argument("--playlist-id", help="Existing Tidal playlist ID to diff against")

    # import subcommand
    imp_parser = subparsers.add_parser("import", help="Import/sync reconciled tracks to Tidal")
    imp_parser.add_argument("json_path", type=Path, help="Path to .reconciled.json file")
    imp_parser.add_argument("--name", required=True, help="Playlist name")
    imp_parser.add_argument("--playlist-id", help="Existing playlist ID to sync (creates new if omitted)")
    imp_parser.add_argument("--no-remove", action="store_true", help="Keep extra tracks in existing playlist")
    imp_parser.add_argument("--dry-run", action="store_true", help="Show plan without modifying")

    # login subcommand
    login_parser = subparsers.add_parser("login", help="Authenticate with Tidal")

    args = parser.parse_args(argv)

    if args.command == "login":
        return _cmd_login()
    elif args.command == "reconcile":
        return _cmd_reconcile(args)
    elif args.command == "import":
        return _cmd_import(args)
    return 1


def _cmd_login() -> int:
    from tidal_importer.client import TidalClient
    client = TidalClient()
    url = client.login()
    print(f"Open this URL to log in:\n\n  {url}\n")
    print("Waiting for authentication...")
    if client.login_wait():
        print("Logged in successfully! Session saved.")
        return 0
    print("Login failed or timed out.", file=sys.stderr)
    return 1


def _cmd_reconcile(args) -> int:
    from tidal_importer.client import TidalClient
    from tidal_importer.reconcile import reconcile_playlist, save_reconciled
    from tidal_importer.sanitize import sanitize_exception

    client = TidalClient()
    if not client.load_session():
        print("Not logged in. Run 'tidal-importer login' first.", file=sys.stderr)
        return 1

    output_path = args.output or args.csv_path.with_suffix(".reconciled.json")

    def progress(current, total):
        print(f"\r  Reconciling: {current}/{total}", end="", flush=True)

    print(f"Reconciling {args.csv_path.name}...")
    try:
        reconciled = reconcile_playlist(
            args.csv_path,
            client,
            existing_playlist_id=args.playlist_id,
            progress_callback=progress,
        )
    except Exception as e:
        print(f"\nError: {sanitize_exception(e)}", file=sys.stderr)
        return 1
    print()  # newline after progress

    save_reconciled(reconciled, output_path)

    matched = sum(1 for t in reconciled if t.status == "matched")
    ambiguous = sum(1 for t in reconciled if t.status == "ambiguous")
    not_found = sum(1 for t in reconciled if t.status == "not_found")
    already = sum(1 for t in reconciled if t.status == "already_in_playlist")

    print(f"\nResults: {matched} matched, {already} already in playlist, {ambiguous} ambiguous, {not_found} not found")
    print(f"Saved to: {output_path}")
    return 0


def _cmd_import(args) -> int:
    from tidal_importer.client import TidalClient
    from tidal_importer.importer import import_playlist
    from tidal_importer.sanitize import sanitize_exception

    client = TidalClient()
    if not client.load_session():
        print("Not logged in. Run 'tidal-importer login' first.", file=sys.stderr)
        return 1

    def progress(phase, current, total):
        print(f"\r  {phase}: {current}/{total}", end="", flush=True)

    try:
        result = import_playlist(
            reconciled_path=args.json_path,
            playlist_name=args.name,
            client=client,
            existing_playlist_id=args.playlist_id,
            remove_extra=not args.no_remove,
            dry_run=args.dry_run,
            progress_callback=progress,
        )
    except Exception as e:
        print(f"\nError: {sanitize_exception(e)}", file=sys.stderr)
        return 1
    print()  # newline after progress

    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{prefix}Playlist: {result.playlist_name} ({result.playlist_id})")
    print(f"{prefix}Added: {result.tracks_added}, Removed: {result.tracks_removed}, Reordered: {result.tracks_reordered}")
    print(f"{prefix}Skipped: {result.tracks_skipped}, Total in playlist: {result.total_in_playlist}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
