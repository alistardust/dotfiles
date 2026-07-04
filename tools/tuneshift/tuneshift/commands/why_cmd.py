"""``why`` command: explain a track's match decision on each platform.

Surfaces the persisted :class:`~tuneshift.matching.MatchAudit` for a track so a
human can answer "why did it pick that / why did it say not-found?" without
reading logs or re-running a search. Reads the durable audit written by sync /
doctor / add; ``--live`` forces a fresh reconcile (needs auth) and re-persists.
"""
import sys

from tuneshift.db import Database
from tuneshift.matching import describe_availability, describe_reason

_ALL_PLATFORMS = ("spotify", "tidal", "ytmusic")


def handle_why(args, db: Database) -> int:
    """Explain the stored (or live) match decision for a track."""
    track = db.get_track(args.track_id)
    if track is None:
        print(f"No track with id {args.track_id}", file=sys.stderr)
        return 1

    album = f" [{track.album}]" if track.album else ""
    print(f"Track #{track.id}: {track.title} — {track.artist}{album}")
    if track.isrc:
        print(f"  ISRC: {track.isrc}")
    print()

    platforms = [args.platform] if args.platform else list(_ALL_PLATFORMS)

    if getattr(args, "live", False):
        return _explain_live(db, track, platforms)

    audits = db.get_match_audits_for_track(track.id)
    if args.platform:
        audits = {p: a for p, a in audits.items() if p == args.platform}
    if not audits:
        print("No stored match decision for this track yet.")
        print("Run `tuneshift sync` / `tuneshift doctor`, or `tuneshift why "
              f"{track.id} --live` to reconcile now.")
        return 1

    for platform in sorted(audits):
        _print_audit(platform, audits[platform])
    return 0


def _explain_live(db: Database, track, platforms: list[str]) -> int:
    """Run a fresh reconcile against each platform, persist, and explain."""
    from tuneshift.commands.ingest_cmd import _load_client
    from tuneshift.reconcile import reconcile_track

    any_done = False
    for platform in platforms:
        client = _load_client(platform)
        if client is None:
            print(f"{platform}: unknown platform, skipped", file=sys.stderr)
            continue
        if not client.load_session():
            print(f"{platform}: not logged in (run `tuneshift login {platform}`), skipped",
                  file=sys.stderr)
            continue
        result = reconcile_track(db, track.id, client, force=True)
        db.save_match_audit(track.id, platform, result.audit)
        if result.audit is not None:
            _print_audit(platform, result.audit)
            any_done = True
    return 0 if any_done else 1


def _print_audit(platform: str, audit) -> None:
    """Render one platform's audit as a compact, human-readable block."""
    avail = describe_availability(audit.availability)
    reason = describe_reason(audit.reason_code)
    print(f"  {platform}: {avail}")
    print(f"    reason: {reason} [{audit.reason_code}]")
    if audit.locked:
        print("    locked: yes (durable user lock)")
    if audit.chosen_platform_id:
        detail = f"    chosen: {audit.chosen_platform_id} (score {audit.chosen_score}"
        if audit.distance is not None:
            detail += f", distance {audit.distance}"
        detail += ")"
        print(detail)
        if audit.decisive_signal:
            print(f"    decisive signal: {audit.decisive_signal}")
    if audit.rejected:
        print("    rejected:")
        for cand in audit.rejected:
            signal = f" — {cand.decisive_signal}" if cand.decisive_signal else ""
            print(f"      [{cand.score}] {cand.title} — {cand.artist} "
                  f"({cand.album}){signal}")
    if audit.note:
        print(f"    note: {audit.note}")
    print()
