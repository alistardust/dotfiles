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
    rec_parser = subparsers.add_parser(
        "reconcile", help="Match CSV tracks against Tidal catalog"
    )
    rec_parser.add_argument("csv_path", type=Path, help="Path to Soundiiz CSV file")
    rec_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output JSON path (default: <csv>.reconciled.json)",
    )
    rec_parser.add_argument(
        "--playlist-id", help="Existing Tidal playlist ID to diff against"
    )

    # import subcommand
    imp_parser = subparsers.add_parser(
        "import", help="Import/sync reconciled tracks to Tidal"
    )
    imp_parser.add_argument(
        "json_path", type=Path, help="Path to .reconciled.json file"
    )
    imp_parser.add_argument("--name", required=True, help="Playlist name")
    imp_parser.add_argument(
        "--playlist-id",
        help="Existing playlist ID to sync (creates new if omitted)",
    )
    imp_parser.add_argument(
        "--no-remove",
        action="store_true",
        help="Keep extra tracks in existing playlist",
    )
    imp_parser.add_argument(
        "--dry-run", action="store_true", help="Show plan without modifying"
    )

    # login subcommand
    login_parser = subparsers.add_parser("login", help="Authenticate with Tidal")

    # sequence subcommand
    seq_parser = subparsers.add_parser(
        "sequence", help="Reorder playlist for optimal flow"
    )
    seq_parser.add_argument("playlist_id", help="Tidal playlist ID or UUID")
    seq_parser.add_argument("--profile", default="default", help="Named weight profile")
    seq_parser.add_argument(
        "--arc",
        help="Energy arc shape (wave/narrative/descending/ascending/free)",
    )
    seq_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show proposed order without applying",
    )
    seq_parser.add_argument("--save-as", help="Create new playlist with this name")
    seq_parser.add_argument(
        "--bold-jump", type=float, help="Bold jump probability (0.0-1.0)"
    )
    seq_parser.add_argument(
        "--artist-sep", type=int, help="Min tracks between same artist"
    )
    seq_parser.add_argument(
        "--verbose", action="store_true", help="Show transition scores"
    )
    seq_parser.add_argument("--themes", type=float, help="Theme weight override")
    seq_parser.add_argument("--energy", type=float, help="Energy weight override")
    seq_parser.add_argument(
        "--instrumentation", type=float, help="Instrumentation weight override"
    )
    seq_parser.add_argument("--bpm", type=float, help="BPM weight override")
    seq_parser.add_argument("--mode", type=float, help="Mode weight override")
    seq_parser.add_argument("--key", type=float, help="Key weight override")

    # auth subcommand
    auth_parser = subparsers.add_parser("auth", help="Configure API credentials")
    auth_parser.add_argument(
        "service",
        choices=["spotify", "lastfm", "anthropic"],
        help="Service to authenticate",
    )

    args = parser.parse_args(argv)

    if args.command == "login":
        return _cmd_login()
    elif args.command == "reconcile":
        return _cmd_reconcile(args)
    elif args.command == "import":
        return _cmd_import(args)
    elif args.command == "sequence":
        return _cmd_sequence(args)
    elif args.command == "auth":
        return _cmd_auth(args)
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
    print()

    save_reconciled(reconciled, output_path)

    matched = sum(1 for t in reconciled if t.status == "matched")
    ambiguous = sum(1 for t in reconciled if t.status == "ambiguous")
    not_found = sum(1 for t in reconciled if t.status == "not_found")
    already = sum(1 for t in reconciled if t.status == "already_in_playlist")

    print(
        f"\nResults: {matched} matched, {already} already in playlist, {ambiguous} ambiguous, {not_found} not found"
    )
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
    print()

    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{prefix}Playlist: {result.playlist_name} ({result.playlist_id})")
    print(
        f"{prefix}Added: {result.tracks_added}, Removed: {result.tracks_removed}, Reordered: {result.tracks_reordered}"
    )
    print(
        f"{prefix}Skipped: {result.tracks_skipped}, Total in playlist: {result.total_in_playlist}"
    )
    return 0


def _cmd_sequence(args) -> int:
    """Execute the sequence subcommand."""
    from tidal_importer.client import TidalClient
    from tidal_importer.sequencer.profiles import get_profile, merge_cli_overrides
    from tidal_importer.sequencer.cache import MetadataCache
    from tidal_importer.sequencer.metadata import (
        MetadataFetcher,
        SpotifySource,
        MusicBrainzSource,
        LastFmSource,
    )
    from tidal_importer.sequencer.classifier import TrackClassifier
    from tidal_importer.sequencer.optimizer import optimize_sequence
    from tidal_importer.sequencer.scoring import score_pair

    client = TidalClient()
    if not client.load_session():
        print("Not logged in. Run 'tidal-importer login' first.", file=sys.stderr)
        return 1

    try:
        profile = get_profile(args.profile)
    except KeyError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    weights = dict(profile.weights)
    overrides = {}
    for dim in ["themes", "energy", "instrumentation", "bpm", "mode", "key"]:
        val = getattr(args, dim, None)
        if val is not None:
            overrides[dim] = val
    if overrides:
        weights = merge_cli_overrides(weights, overrides)

    arc = args.arc or profile.arc
    bold_jump = (
        args.bold_jump
        if args.bold_jump is not None
        else profile.bold_jump_chance
    )
    artist_sep = (
        args.artist_sep
        if args.artist_sep is not None
        else profile.artist_min_separation
    )

    print(f"Fetching playlist {args.playlist_id}...")
    playlist_tracks = client.get_playlist_tracks(args.playlist_id)
    if not playlist_tracks:
        print("Error: playlist is empty or not found.", file=sys.stderr)
        return 1
    print(f"  {len(playlist_tracks)} tracks found")

    track_infos = []
    for track in playlist_tracks:
        track_infos.append(
            {
                "isrc": getattr(track, "isrc", None) or f"TIDAL-{track.tidal_id}",
                "tidal_id": track.tidal_id,
                "title": track.title,
                "artist": track.artist,
            }
        )

    cache = MetadataCache()
    spotify_source = None
    mb_source = None
    lastfm_source = None

    creds_dir = Path.home() / ".local" / "share" / "tidal-importer"

    spotify_creds = creds_dir / "spotify_credentials.json"
    if spotify_creds.exists():
        try:
            import json as _json
            import spotipy
            from spotipy.oauth2 import SpotifyClientCredentials

            creds = _json.loads(spotify_creds.read_text())
            sp = spotipy.Spotify(
                auth_manager=SpotifyClientCredentials(
                    client_id=creds["client_id"],
                    client_secret=creds["client_secret"],
                )
            )
            spotify_source = SpotifySource(client=sp)
        except Exception as e:
            print(f"  Warning: Spotify unavailable: {e}")

    try:
        import musicbrainzngs

        musicbrainzngs.set_useragent(
            "tidal-importer",
            "0.2.0",
            "https://github.com/user/tidal-importer",
        )
        mb_source = MusicBrainzSource(client=musicbrainzngs)
    except ImportError:
        pass

    lastfm_creds = creds_dir / "lastfm_credentials.json"
    if lastfm_creds.exists():
        try:
            import json as _json
            import pylast

            creds = _json.loads(lastfm_creds.read_text())
            network = pylast.LastFMNetwork(api_key=creds["api_key"])
            lastfm_source = LastFmSource(client=network)
        except Exception as e:
            print(f"  Warning: Last.fm unavailable: {e}")

    fetcher = MetadataFetcher(
        cache=cache,
        spotify_source=spotify_source,
        musicbrainz_source=mb_source,
        lastfm_source=lastfm_source,
    )

    def metadata_progress(current, total):
        print(f"\r  Metadata: {current}/{total}", end="", flush=True)

    print("Collecting metadata...")
    metadata_map = fetcher.get_metadata(
        track_infos, progress_callback=metadata_progress
    )
    print()

    unclassified = [
        {"title": m.title, "artist": m.artist, "isrc": m.isrc}
        for m in metadata_map.values()
        if not m.has_classification()
    ]
    if unclassified:
        print(f"Classifying {len(unclassified)} tracks...")
        try:
            import anthropic

            anthropic_client = anthropic.Anthropic()
            classifier = TrackClassifier(client=anthropic_client)

            def classify_progress(current, total):
                print(f"\r  Classifying: {current}/{total}", end="", flush=True)

            classifications = classifier.classify_batched(
                [{"title": t["title"], "artist": t["artist"]} for t in unclassified],
                progress_callback=classify_progress,
            )
            print()

            for track_info, classification in zip(unclassified, classifications):
                if not classification:
                    continue
                meta = metadata_map.get(track_info["isrc"])
                if meta is None:
                    continue
                meta.themes = classification.get("themes", [])
                meta.vibes = classification.get("vibes", [])
                meta.instruments = classification.get("instruments", [])
                meta.density = classification.get("density")
                meta.era_mood = classification.get("era_mood", [])
                cache.save(meta)
        except ImportError:
            print("  Warning: anthropic not installed, skipping classification")
        except Exception as e:
            print(f"  Warning: classification failed: {e}")

    tracks_to_sequence = list(metadata_map.values())
    print(f"Optimizing sequence (arc={arc}, profile={profile.name})...")
    sequenced = optimize_sequence(
        tracks_to_sequence,
        weights=weights,
        arc=arc,
        artist_min_separation=artist_sep,
        bold_jump_chance=bold_jump,
    )

    if args.dry_run or args.verbose:
        print(f"\nProposed sequence ({len(sequenced)} tracks):")
        for i, track in enumerate(sequenced):
            line = f"  {i + 1:3d}. {track.artist} - {track.title}"
            if args.verbose and i > 0:
                prev = sequenced[i - 1]
                transition = score_pair(prev, track, weights)
                line += f" [score: {transition:.3f}]"
            print(line)

    if args.dry_run:
        print("\n[DRY RUN] No changes applied.")
        return 0

    ordered_ids = [track.tidal_id for track in sequenced]

    if args.save_as:
        print(f"Creating new playlist: {args.save_as}")
        new_playlist = client.create_playlist(
            args.save_as, f"Sequenced from {args.playlist_id}"
        )
        client.add_tracks(new_playlist.playlist_id, ordered_ids)
        print(f"  Created: {new_playlist.playlist_id} ({len(ordered_ids)} tracks)")
    else:
        print("Applying new sequence to playlist...")
        client.set_playlist_order(args.playlist_id, ordered_ids)
        print(f"  Reordered {len(ordered_ids)} tracks")

    print("Done!")
    return 0


def _cmd_auth(args) -> int:
    """Configure API credentials for external services."""
    import json

    from tidal_importer.paths import secure_write

    creds_dir = Path.home() / ".local" / "share" / "tidal-importer"
    creds_dir.mkdir(parents=True, exist_ok=True)

    if args.service == "spotify":
        print("Spotify API credentials (from developer.spotify.com):")
        client_id = input("  Client ID: ").strip()
        client_secret = input("  Client Secret: ").strip()
        if not client_id or not client_secret:
            print("Error: both fields required.", file=sys.stderr)
            return 1
        secure_write(
            creds_dir / "spotify_credentials.json",
            json.dumps(
                {"client_id": client_id, "client_secret": client_secret}
            ),
        )
        print("Spotify credentials saved.")

    elif args.service == "lastfm":
        print("Last.fm API key (from last.fm/api/account/create):")
        api_key = input("  API Key: ").strip()
        if not api_key:
            print("Error: API key required.", file=sys.stderr)
            return 1
        secure_write(
            creds_dir / "lastfm_credentials.json",
            json.dumps({"api_key": api_key}),
        )
        print("Last.fm credentials saved.")

    elif args.service == "anthropic":
        print("Anthropic API key (or set ANTHROPIC_API_KEY env var):")
        api_key = input("  API Key: ").strip()
        if not api_key:
            print("Error: API key required.", file=sys.stderr)
            return 1
        secure_write(
            creds_dir / "anthropic_credentials.json",
            json.dumps({"api_key": api_key}),
        )
        print("Anthropic credentials saved.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
