"""Resolve command: identity resolution for tracks."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from tuneshift.identity import resolve_playlist, resolve_track
from tuneshift.identity.models import ResolutionStatus
from tuneshift.identity.sources.musicbrainz import MusicBrainzSource

if TYPE_CHECKING:
    from argparse import Namespace

    from tuneshift.db import Database


def run_resolve(args: Namespace, db: Database) -> None:
    """Execute the resolve command."""
    if args.force and not args.upgrade:
        print("Error: --force requires --upgrade", file=sys.stderr)
        raise SystemExit(1)

    if args.status:
        _show_status(args, db)
        return

    from tuneshift.platforms.rate_limiter import RateLimiter

    mb = MusicBrainzSource()
    discogs = _try_init_discogs()
    rate_limiters = {
        "musicbrainz": RateLimiter(max_per_second=1.0),
        "discogs": RateLimiter(max_per_second=1.0),
    }

    if args.track:
        _resolve_single_track(args, db, mb, discogs, rate_limiters)
    elif args.all:
        _resolve_all(args, db, mb, discogs, rate_limiters)
    elif args.playlist:
        _resolve_named_playlist(args, db, mb, discogs, rate_limiters)
    else:
        print("Error: specify a playlist name, --track, or --all", file=sys.stderr)
        raise SystemExit(1)


def _resolve_named_playlist(args, db, mb, discogs, rate_limiters) -> None:
    """Resolve all tracks in a named playlist."""
    playlist = db.find_playlist_by_name(args.playlist)
    if playlist is None:
        print(f"Error: playlist '{args.playlist}' not found", file=sys.stderr)
        raise SystemExit(1)

    tracks = db.get_playlist_tracks(playlist.id)
    print(f'Resolving "{args.playlist}" ({len(tracks)} tracks)...')

    def on_progress(track_id, index, total, result):
        del index, total
        track = db.get_track(track_id)
        if track is not None:
            _print_result(track, result, verbose=args.verbose)

    results = resolve_playlist(
        db,
        playlist.id,
        upgrade=args.upgrade,
        force=args.force,
        musicbrainz=mb,
        discogs=discogs,
        rate_limiters=rate_limiters,
        on_progress=on_progress,
    )
    _print_summary(results)


def _resolve_single_track(args, db, mb, discogs, rate_limiters) -> None:
    """Resolve a single track by title and artist lookup."""
    title, artist = args.track
    matches = db.find_tracks_by_title_artist(title=title, artist=artist)
    if not matches:
        print("Error: Track not in database. Use `tuneshift add` first.", file=sys.stderr)
        raise SystemExit(1)

    if len(matches) == 1:
        track = matches[0]
    else:
        print(f"Multiple matches for '{title}' by '{artist}':")
        for index, match in enumerate(matches, 1):
            print(f"  {index}. {match.title} - {match.artist} ({match.album or 'no album'})")
        choice = input("Select [1]: ").strip() or "1"
        try:
            track = matches[int(choice) - 1]
        except (ValueError, IndexError):
            print("Invalid selection.", file=sys.stderr)
            raise SystemExit(1)

    result = resolve_track(
        db,
        track.id,
        upgrade=args.upgrade,
        force=args.force,
        musicbrainz=mb,
        discogs=discogs,
        rate_limiters=rate_limiters,
    )
    _print_result(track, result, verbose=True)


def _resolve_all(args, db, mb, discogs, rate_limiters) -> None:
    """Resolve all unresolved tracks in the database."""
    below_tier = "CONFIRMED" if args.upgrade else None
    tracks = db.find_unresolved(below_tier=below_tier)
    print(f"Resolving {len(tracks)} tracks...")

    for track in tracks:
        result = resolve_track(
            db,
            track.id,
            upgrade=args.upgrade,
            force=args.force,
            musicbrainz=mb,
            discogs=discogs,
            rate_limiters=rate_limiters,
        )
        _print_result(track, result, verbose=args.verbose)

    print(f"\nDone. Resolved {len(tracks)} tracks.")


def _show_status(args, db) -> None:
    """Show resolution statistics."""
    if args.playlist:
        playlist = db.find_playlist_by_name(args.playlist)
        if playlist is None:
            print(f"Error: playlist '{args.playlist}' not found", file=sys.stderr)
            raise SystemExit(1)
        tracks = db.get_playlist_tracks(playlist.id)
        resolved = 0
        for track in tracks:
            tier, _, _ = db.get_resolution_state(track.id)
            if tier is not None:
                resolved += 1
        platforms = db.get_linked_platforms(playlist.id)
        platform_names = ", ".join(platforms) if platforms else "none"
        percent = 100 * resolved // len(tracks) if tracks else 0
        print(f"  {args.playlist}")
        print(f"    Tracks: {len(tracks)}")
        print(f"    Resolved: {resolved}/{len(tracks)} ({percent}%)")
        print(f"    Platforms: {platform_names}")
    else:
        all_unresolved = db.find_unresolved()
        print(f"  Unresolved tracks: {len(all_unresolved)}")


def _print_result(track, result, verbose: bool = False) -> None:
    """Print a single resolution result."""
    if result.status == ResolutionStatus.SKIPPED and not verbose:
        return
    tier = result.confidence_tier.value if result.confidence_tier else "FAILED"
    suffix = ""
    if result.status == ResolutionStatus.UNCHANGED:
        suffix = " (unchanged)"
    elif result.status == ResolutionStatus.FAILED:
        suffix = f" ({result.error})" if result.error else ""
    print(f"  [{tier}]{suffix}  {track.title} - {track.artist}")


def _print_summary(results) -> None:
    """Print resolution summary."""
    from collections import Counter

    tiers = Counter()
    for result in results:
        if result.confidence_tier:
            tiers[result.confidence_tier.value] += 1
        elif result.status == ResolutionStatus.FAILED:
            tiers["FAILED"] += 1
    parts = [f"{count} {tier}" for tier, count in sorted(tiers.items())]
    print(f"\nResolved: {len(results)} tracks ({', '.join(parts)})")


def _try_init_discogs():
    """Try to initialize Discogs source, return None if not configured."""
    try:
        from tuneshift.identity.sources.discogs import DiscogsSource

        return DiscogsSource()
    except Exception:
        return None
