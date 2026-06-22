"""Batch operations: plan/apply model for bulk playlist changes."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from tuneshift.db import Database

_PLAN_DIR = Path.home() / ".local" / "share" / "tuneshift" / "plans"
_BACKUP_DIR = Path.home() / ".local" / "share" / "tuneshift" / "backups"

# Regex for extracting featured artists from track titles
_FEAT_EXTRACT_RE = None


def _get_feat_re():
    """Lazy-load the featured artist extraction regex."""
    global _FEAT_EXTRACT_RE
    if _FEAT_EXTRACT_RE is None:
        import re
        _FEAT_EXTRACT_RE = re.compile(
            r"[\(\[]\s*(?:feat\.?|ft\.?|featuring|with)\s+([^\)\]]+)[\)\]]",
            re.IGNORECASE,
        )
    return _FEAT_EXTRACT_RE


def extract_featured_artists(title: str) -> list[str]:
    """Extract featured artist names from a track title."""
    match = _get_feat_re().search(title)
    if not match:
        return []
    raw = match.group(1)
    # Split on common delimiters: ", ", " & ", " and "
    import re
    parts = re.split(r"\s*(?:,|&|and)\s*", raw, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


@dataclass
class PlanOperation:
    """A single planned change to a playlist."""

    action: str  # "rm", "add", "keep"
    track_title: str
    track_artist: str
    track_id: int | None = None
    reason: str = ""
    position: int | None = None


@dataclass
class BatchPlan:
    """A set of planned changes to a playlist."""

    playlist_name: str
    playlist_id: int
    operations: list[PlanOperation] = field(default_factory=list)
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    @property
    def removals(self) -> list[PlanOperation]:
        return [op for op in self.operations if op.action == "rm"]

    @property
    def additions(self) -> list[PlanOperation]:
        return [op for op in self.operations if op.action == "add"]

    @property
    def keeps(self) -> list[PlanOperation]:
        return [op for op in self.operations if op.action == "keep"]

    def save(self) -> Path:
        """Save plan to disk."""
        _PLAN_DIR.mkdir(parents=True, exist_ok=True)
        plan_file = _PLAN_DIR / "current.json"
        data = {
            "playlist": self.playlist_name,
            "playlist_id": self.playlist_id,
            "created": self.created_at,
            "operations": [
                {
                    "action": op.action,
                    "track": op.track_title,
                    "artist": op.track_artist,
                    "track_id": op.track_id,
                    "reason": op.reason,
                }
                for op in self.operations
            ],
        }
        plan_file.write_text(json.dumps(data, indent=2))
        return plan_file

    @classmethod
    def load(cls) -> BatchPlan | None:
        """Load the current plan from disk."""
        plan_file = _PLAN_DIR / "current.json"
        if not plan_file.exists():
            return None
        data = json.loads(plan_file.read_text())
        plan = cls(
            playlist_name=data["playlist"],
            playlist_id=data["playlist_id"],
            created_at=data["created"],
        )
        for op in data["operations"]:
            plan.operations.append(PlanOperation(
                action=op["action"],
                track_title=op["track"],
                track_artist=op["artist"],
                track_id=op.get("track_id"),
                reason=op.get("reason", ""),
            ))
        return plan

    @staticmethod
    def discard() -> bool:
        """Remove the current plan file."""
        plan_file = _PLAN_DIR / "current.json"
        if plan_file.exists():
            plan_file.unlink()
            return True
        return False


def backup_db(db: Database) -> Path:
    """Create a timestamped backup of the database before applying changes."""
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = _BACKUP_DIR / f"tuneshift-{timestamp}.db"
    src = Path(db.conn.execute("PRAGMA database_list").fetchone()[2])
    shutil.copy2(src, backup_path)
    return backup_path


def restore_backup(db: Database) -> Path | None:
    """Restore the most recent backup."""
    if not _BACKUP_DIR.exists():
        return None
    backups = sorted(_BACKUP_DIR.glob("tuneshift-*.db"), reverse=True)
    if not backups:
        return None
    latest = backups[0]
    db_path = Path(db.conn.execute("PRAGMA database_list").fetchone()[2])
    db.conn.close()
    shutil.copy2(latest, db_path)
    return latest


def plan_dedupe(
    db: Database, playlist_id: int, cap: int
) -> list[PlanOperation]:
    """Plan deduplication: flag artists with more than cap tracks."""
    tracks = db.get_playlist_tracks(playlist_id)
    by_artist: dict[str, list] = {}
    for i, t in enumerate(tracks):
        by_artist.setdefault(t.artist, []).append((i, t))

    ops: list[PlanOperation] = []
    for artist, entries in by_artist.items():
        if len(entries) <= cap:
            continue
        # Keep the first N tracks (by current position), remove the rest
        entries.sort(key=lambda e: e[0])
        for idx, (pos, track) in enumerate(entries):
            if idx < cap:
                ops.append(PlanOperation(
                    action="keep",
                    track_title=track.title,
                    track_artist=track.artist,
                    track_id=track.id,
                    reason=f"dedupe cap={cap}, keeping #{idx + 1} of {len(entries)}",
                    position=pos,
                ))
            else:
                ops.append(PlanOperation(
                    action="rm",
                    track_title=track.title,
                    track_artist=track.artist,
                    track_id=track.id,
                    reason=f"dedupe cap={cap}, {artist} has {len(entries)} tracks",
                    position=pos,
                ))
    return ops


def plan_rm_artist(
    db: Database, playlist_id: int, artist_name: str
) -> list[PlanOperation]:
    """Plan removal of all tracks by an artist (including featured)."""
    tracks = db.get_playlist_tracks(playlist_id)
    target_lower = artist_name.lower()
    ops: list[PlanOperation] = []

    for i, t in enumerate(tracks):
        is_primary = t.artist.lower() == target_lower
        featured = extract_featured_artists(t.title)
        is_featured = any(f.lower() == target_lower for f in featured)

        if is_primary or is_featured:
            credit = "primary artist" if is_primary else f"featured in title"
            ops.append(PlanOperation(
                action="rm",
                track_title=t.title,
                track_artist=t.artist,
                track_id=t.id,
                reason=f"artist removal: {artist_name} ({credit})",
                position=i,
            ))
    return ops


def plan_review_fixes(
    db: Database, playlist_id: int
) -> list[PlanOperation]:
    """Plan fixes based on review findings (hard violations = rm, soft = warn)."""
    from tuneshift.commands.compose_cmd import _get_concept, _build_artist_lookup
    from tuneshift.composer.reviewer import review_playlist
    from tuneshift.sequencer.metadata import track_to_metadata

    concept = _get_concept(db, playlist_id)
    if concept is None:
        return []

    tracks_raw = db.get_playlist_tracks(playlist_id)
    tracks = [track_to_metadata(t) for t in tracks_raw]
    artist_lookup = _build_artist_lookup(db, playlist_id)

    findings = review_playlist(tracks, concept=concept, artist_lookup=artist_lookup)

    ops: list[PlanOperation] = []
    seen_track_ids: set[int] = set()

    for finding in findings:
        if finding.severity < 0.8:
            continue
        # Extract track info from finding description
        import re
        match = re.search(r'"([^"]+)" by (.+?) - Rule:', finding.description)
        if not match:
            continue
        title = match.group(1)
        artist = match.group(2)
        # Find the track
        for i, t in enumerate(tracks_raw):
            if t.title == title and t.artist == artist and t.id not in seen_track_ids:
                ops.append(PlanOperation(
                    action="rm",
                    track_title=t.title,
                    track_artist=t.artist,
                    track_id=t.id,
                    reason=finding.description,
                    position=i,
                ))
                seen_track_ids.add(t.id)
                break

    return ops


def apply_plan(db: Database, plan: BatchPlan) -> tuple[int, int]:
    """Apply a plan: execute removals and additions, sync to platforms.

    Returns (removals_applied, additions_applied).
    """
    from tuneshift.commands.rm_cmd import _remove_and_sync

    removed = 0
    added = 0

    # Process removals first
    for op in plan.removals:
        if op.track_id is None:
            continue
        tracks = db.get_playlist_tracks(plan.playlist_id)
        track = next((t for t in tracks if t.id == op.track_id), None)
        if track is None:
            continue
        position = next(
            (i + 1 for i, t in enumerate(tracks) if t.id == op.track_id), 0
        )
        _remove_and_sync(db, type("P", (), {"id": plan.playlist_id, "name": plan.playlist_name})(), track, position)
        removed += 1

    # TODO: process additions when add-from/fill is implemented

    return removed, added


def render_plan(plan: BatchPlan) -> str:
    """Render a plan as human-readable text."""
    lines: list[str] = []
    lines.append(f'Plan for "{plan.playlist_name}" (created {plan.created_at})')
    lines.append("")

    if plan.removals:
        lines.append(f"REMOVE ({len(plan.removals)}):")
        for op in plan.removals:
            lines.append(f'  - "{op.track_title}" by {op.track_artist}')
            lines.append(f"    Reason: {op.reason}")
        lines.append("")

    if plan.keeps:
        lines.append(f"KEEP ({len(plan.keeps)}):")
        for op in plan.keeps:
            lines.append(f'  - "{op.track_title}" by {op.track_artist}')
            lines.append(f"    Reason: {op.reason}")
        lines.append("")

    if plan.additions:
        lines.append(f"ADD ({len(plan.additions)}):")
        for op in plan.additions:
            lines.append(f'  - "{op.track_title}" by {op.track_artist}')
            lines.append(f"    Reason: {op.reason}")
        lines.append("")

    summary = []
    if plan.removals:
        summary.append(f"{len(plan.removals)} removal(s)")
    if plan.additions:
        summary.append(f"{len(plan.additions)} addition(s)")
    if plan.keeps:
        summary.append(f"{len(plan.keeps)} keep(s)")
    lines.append(f"Summary: {', '.join(summary) if summary else 'no changes'}")

    return "\n".join(lines)


def _interactive_dedupe(
    db: Database, playlist_id: int, cap: int
) -> list[PlanOperation]:
    """Walk through dedupe decisions one artist at a time."""
    tracks = db.get_playlist_tracks(playlist_id)
    by_artist: dict[str, list] = {}
    for i, t in enumerate(tracks):
        by_artist.setdefault(t.artist, []).append((i, t))

    ops: list[PlanOperation] = []
    for artist, entries in sorted(by_artist.items()):
        if len(entries) <= cap:
            continue
        entries.sort(key=lambda e: e[0])

        print(f"\n{artist} has {len(entries)} tracks (cap: {cap}). Keep which?")
        for idx, (pos, track) in enumerate(entries):
            print(f"  {idx + 1}. {track.title}")

        choices_raw = input(f"Keep (1-{len(entries)}, comma-separated, or 'all'/'none'): ").strip()
        if choices_raw.lower() == "all":
            continue
        if choices_raw.lower() == "none":
            keep_indices: set[int] = set()
        else:
            try:
                keep_indices = {int(c.strip()) - 1 for c in choices_raw.split(",")}
            except ValueError:
                print("  Invalid input, keeping all.")
                continue

        for idx, (pos, track) in enumerate(entries):
            if idx in keep_indices:
                ops.append(PlanOperation(
                    action="keep",
                    track_title=track.title,
                    track_artist=track.artist,
                    track_id=track.id,
                    reason=f"dedupe cap={cap}, curator choice",
                    position=pos,
                ))
            else:
                ops.append(PlanOperation(
                    action="rm",
                    track_title=track.title,
                    track_artist=track.artist,
                    track_id=track.id,
                    reason=f"dedupe cap={cap}, {artist} has {len(entries)} tracks",
                    position=pos,
                ))
    return ops


def handle_batch(args, db: Database) -> int:
    """Handle batch operations: plan, show, apply, discard, undo."""
    import sys

    # Show current plan
    if getattr(args, "show_plan", False):
        plan = BatchPlan.load()
        if plan is None:
            print("No plan exists. Create one with: tuneshift batch <playlist> --<operation> --plan")
            return 1
        print(render_plan(plan))
        return 0

    # Discard current plan
    if getattr(args, "discard", False):
        if BatchPlan.discard():
            print("Plan discarded.")
        else:
            print("No plan to discard.")
        return 0

    # Undo (restore backup)
    if getattr(args, "undo", False):
        restored = restore_backup(db)
        if restored:
            print(f"Restored from backup: {restored}")
            print("Restart tuneshift to use the restored database.")
        else:
            print("No backup found.", file=sys.stderr)
            return 1
        return 0

    # Apply current plan
    if getattr(args, "apply", False):
        plan = BatchPlan.load()
        if plan is None:
            print("No plan to apply. Create one first.", file=sys.stderr)
            return 1
        print(render_plan(plan))
        print()
        confirm = input("Apply this plan? [y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Cancelled.")
            return 0
        backup_path = backup_db(db)
        print(f"Backup created: {backup_path}")
        removed, added = apply_plan(db, plan)
        print(f"\nApplied: {removed} removed, {added} added")
        BatchPlan.discard()
        return 0

    # Generate a plan (requires playlist name)
    if not args.playlist:
        print("Playlist name required for plan generation.", file=sys.stderr)
        return 1

    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        print(f"Playlist not found: {args.playlist}", file=sys.stderr)
        return 1

    ops: list[PlanOperation] = []

    if getattr(args, "dedupe", False):
        cap = getattr(args, "cap", 1)
        if getattr(args, "interactive", False):
            ops.extend(_interactive_dedupe(db, playlist.id, cap))
        else:
            ops.extend(plan_dedupe(db, playlist.id, cap))

    if getattr(args, "rm_artist", False):
        ops.extend(plan_rm_artist(db, playlist.id, args.rm_artist))

    if getattr(args, "review_findings", False):
        ops.extend(plan_review_fixes(db, playlist.id))

    if not ops:
        print("No changes needed.")
        return 0

    plan = BatchPlan(
        playlist_name=playlist.name,
        playlist_id=playlist.id,
        operations=ops,
    )

    print(render_plan(plan))

    if getattr(args, "plan", False):
        plan_path = plan.save()
        print(f"\nPlan saved to {plan_path}")
        print("Review with: tuneshift batch --show-plan")
        print("Apply with:  tuneshift batch --apply")
        print("Discard:     tuneshift batch --discard")
    else:
        # No --plan flag: ask to apply directly
        print()
        confirm = input("Apply now? [y/N] ").strip().lower()
        if confirm in ("y", "yes"):
            backup_path = backup_db(db)
            print(f"Backup created: {backup_path}")
            removed, added = apply_plan(db, plan)
            print(f"\nApplied: {removed} removed, {added} added")
        else:
            plan_path = plan.save()
            print(f"Plan saved to {plan_path}. Apply with: tuneshift batch --apply")

    return 0
