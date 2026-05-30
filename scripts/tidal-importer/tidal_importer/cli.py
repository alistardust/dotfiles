"""CLI entrypoint for tidal-importer."""
import argparse
import os
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

    # atmos subcommand
    atmos_parser = subparsers.add_parser(
        "atmos", help="Create Atmos derivative playlist"
    )
    atmos_parser.add_argument("playlist_id", help="Source Tidal playlist ID or UUID")
    atmos_parser.add_argument(
        "--name", help="Name for the Atmos playlist (default: original name + Atmos)"
    )
    atmos_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show matches without creating playlist",
    )
    atmos_parser.add_argument(
        "--sequence",
        action="store_true",
        help="Auto-sequence the Atmos playlist after creation",
    )
    atmos_parser.add_argument(
        "--profile", default="default", help="Sequencing profile (if --sequence)"
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
    elif args.command == "atmos":
        return _cmd_atmos(args)
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

            anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
            if not anthropic_key:
                anthropic_creds = creds_dir / "anthropic_credentials.json"
                if anthropic_creds.exists():
                    import json as _json

                    anthropic_key = _json.loads(
                        anthropic_creds.read_text()
                    ).get("api_key")
            anthropic_client = anthropic.Anthropic(
                api_key=anthropic_key
            ) if anthropic_key else anthropic.Anthropic()
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


def _cmd_atmos(args) -> int:
    """Create an Atmos derivative playlist from an existing playlist."""
    import re
    import time
    from difflib import SequenceMatcher

    import tidalapi
    import json

    from tidal_importer.client import TidalClient

    session_file = Path.home() / ".local" / "share" / "tidal-importer" / "session.json"
    if not session_file.exists():
        print("Not logged in. Run 'tidal-importer login' first.", file=sys.stderr)
        return 1

    data = json.loads(session_file.read_text())
    session = tidalapi.Session()
    session.load_oauth_session(
        token_type=data["token_type"],
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token"),
    )

    print(f"Fetching playlist {args.playlist_id}...")
    playlist = session.playlist(args.playlist_id)
    tracks = playlist.tracks()
    playlist_name = playlist.name
    print(f"  '{playlist_name}' - {len(tracks)} tracks")

    # Collect unique artists from the playlist
    artist_ids = {}
    for t in tracks:
        if t.artist and t.artist.id not in artist_ids:
            artist_ids[t.artist.id] = t.artist

    # Search for Atmos albums from these artists
    print(f"Searching Atmos catalog for {len(artist_ids)} artists...")
    atmos_index = {}  # (normalized_artist, normalized_title) -> track_id

    def strip_extras(title):
        t = title.lower().strip()
        for p in [
            r'\s*\(.*?remaster.*?\)', r'\s*\(.*?remix.*?\)',
            r'\s*\(.*?mix.*?\)', r'\s*\(.*?version.*?\)',
            r'\s*\(.*?deluxe.*?\)', r'\s*\(.*?live.*?\)',
            r'\s*\(.*?edition.*?\)', r'\s*\(.*?anniversary.*?\)',
            r'\s*\[.*?\]', r'\s*-\s*\d{4}\s*remaster',
            r'\s*\(atmos.*?\)', r'\s*\(2\d{3}.*?\)',
        ]:
            t = re.sub(p, '', t, flags=re.IGNORECASE)
        return t.strip()

    for artist_id, artist_obj in artist_ids.items():
        time.sleep(0.3)
        try:
            all_albums = []
            all_albums.extend(artist_obj.get_albums(limit=50))
            time.sleep(0.2)
            try:
                all_albums.extend(artist_obj.get_albums_other(limit=50))
            except Exception:
                pass
            time.sleep(0.2)
            try:
                all_albums.extend(artist_obj.get_ep_singles(limit=50))
            except Exception:
                pass

            for album in all_albums:
                if (hasattr(album, 'audio_modes') and album.audio_modes
                        and 'DOLBY_ATMOS' in album.audio_modes):
                    time.sleep(0.2)
                    try:
                        album_tracks = album.tracks()
                        for at in album_tracks:
                            artist_name = strip_extras(
                                at.artist.name if at.artist else artist_obj.name
                            )
                            title = strip_extras(at.name or "")
                            key = (artist_name, title)
                            if key not in atmos_index:
                                atmos_index[key] = at.id
                    except Exception:
                        pass
        except Exception:
            pass

    print(f"  Found {len(atmos_index)} Atmos tracks from playlist artists")

    # Match playlist tracks to Atmos versions
    matches = []
    for t in tracks:
        artist_raw = t.artist.name if t.artist else ""
        title_raw = t.name or ""
        artist_stripped = strip_extras(artist_raw)
        title_stripped = strip_extras(title_raw)

        key = (artist_stripped, title_stripped)
        if key in atmos_index:
            matches.append({
                "original": f"{artist_raw} - {title_raw}",
                "atmos_id": atmos_index[key],
            })
            continue

        # Fuzzy title match within same artist
        for (idx_artist, idx_title), atmos_id in atmos_index.items():
            if title_stripped == idx_title:
                if (idx_artist in artist_stripped
                        or artist_stripped in idx_artist
                        or SequenceMatcher(
                            None, idx_artist, artist_stripped
                        ).ratio() > 0.6):
                    matches.append({
                        "original": f"{artist_raw} - {title_raw}",
                        "atmos_id": atmos_id,
                    })
                    break

    print(f"\n  Matched: {len(matches)}/{len(tracks)} tracks have Atmos versions")

    if not matches:
        print("No Atmos tracks found for this playlist.", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"\nAtmos tracks ({len(matches)}):")
        for m in matches:
            print(f"  + {m['original']}")
        print("\n[DRY RUN] No playlist created.")
        return 0

    # Create the Atmos playlist
    atmos_name = args.name or f"{playlist_name} (Atmos)"
    print(f"\nCreating playlist: {atmos_name}")

    client = TidalClient()
    client.load_session()
    new_playlist = client.create_playlist(
        atmos_name, f"Atmos derivative of {playlist_name}"
    )

    atmos_ids = [m["atmos_id"] for m in matches]
    client.add_tracks(new_playlist.playlist_id, atmos_ids)
    print(f"  Created: {new_playlist.playlist_id} ({len(atmos_ids)} tracks)")

    if args.sequence:
        print(f"\nSequencing with profile '{args.profile}'...")
        seq_argv = [
            "sequence", new_playlist.playlist_id,
            "--profile", args.profile,
        ]
        from unittest.mock import patch
        with patch("sys.argv", ["tidal-importer"] + seq_argv):
            seq_args = type("Args", (), {
                "playlist_id": new_playlist.playlist_id,
                "profile": args.profile,
                "arc": None,
                "dry_run": False,
                "save_as": None,
                "bold_jump": None,
                "artist_sep": None,
                "verbose": False,
                "themes": None,
                "energy": None,
                "instrumentation": None,
                "bpm": None,
                "mode": None,
                "key": None,
            })()
            _cmd_sequence(seq_args)

    print("Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
