"""Batch operations: plan/apply model for bulk playlist changes."""

from __future__ import annotations

import json
import shutil
import sys
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


def split_artist_credits(artist: str) -> list[str]:
    """Split a multi-artist credit into individual artist names.

    Handles: "Drake, 21 Savage", "Jack & Diane", "A and B", "X x Y"
    """
    import re
    parts = re.split(r"\s*(?:,\s+|&|\band\b|\bx\b)\s*", artist, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


def check_track_against_bans(db: Database, title: str, artist: str) -> str | None:
    """Check if any credited artist on a track is banned.

    Checks primary artist (split on multi-credit delimiters) and featured
    artists extracted from the title. Returns the banned name if found, None otherwise.
    """
    # Check primary artist segments
    for segment in split_artist_credits(artist):
        if db.is_artist_banned(segment):
            return segment
    # Check featured artists in title
    for featured in extract_featured_artists(title):
        if db.is_artist_banned(featured):
            return featured
    return None


@dataclass
class PlanOperation:
    """A single planned change to a playlist."""

    action: str  # "rm", "add", "keep", "create_playlist", "move_to_playlist", "assign_section", "set_narrative"
    track_title: str = ""
    track_artist: str = ""
    track_id: int | None = None
    reason: str = ""
    position: int | None = None
    previous_position: int | None = None
    previous_section: str | None = None
    target_name: str | None = None  # for split/merge/section targets
    section_name: str | None = None


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


def plan_sweep_banned(
    db: Database, playlist_id: int | None = None
) -> dict[int, list[PlanOperation]]:
    """Sweep one or all playlists for banned artists.

    Returns a dict of playlist_id -> list of removal operations.
    """
    if playlist_id is not None:
        playlist_ids = [playlist_id]
    else:
        playlists = db.list_playlists()
        playlist_ids = [p.id for p in playlists]

    results: dict[int, list[PlanOperation]] = {}
    for pid in playlist_ids:
        tracks = db.get_playlist_tracks(pid)
        ops: list[PlanOperation] = []
        for i, t in enumerate(tracks):
            banned_name = check_track_against_bans(db, t.title, t.artist)
            if banned_name:
                ops.append(PlanOperation(
                    action="rm",
                    track_title=t.title,
                    track_artist=t.artist,
                    track_id=t.id,
                    reason=f"banned artist: {banned_name}",
                    position=i,
                    previous_position=i,
                ))
        if ops:
            results[pid] = ops
    return results


def parse_plan_file(content: str) -> list[PlanOperation]:
    """Parse a plan file in simple text format.

    Format:
      - Title - Artist          # remove
      + Title - Artist          # add
      = Title - Artist -> pos:7       # move to position
      = Title - Artist -> sec:WRATH   # move to section
      = Title - Artist -> sec:WRATH:3 # move to position within section
    """
    ops: list[PlanOperation] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("- "):
            parts = line[2:].rsplit(" - ", 1)
            if len(parts) == 2:
                ops.append(PlanOperation(action="rm", track_title=parts[0].strip(), track_artist=parts[1].strip()))
            else:
                ops.append(PlanOperation(action="rm", track_title=line[2:].strip()))
        elif line.startswith("+ "):
            parts = line[2:].rsplit(" - ", 1)
            if len(parts) == 2:
                ops.append(PlanOperation(action="add", track_title=parts[0].strip(), track_artist=parts[1].strip()))
            else:
                ops.append(PlanOperation(action="add", track_title=line[2:].strip()))
        elif line.startswith("= "):
            # Move operation: = Title - Artist -> target
            if " -> " not in line:
                continue
            left, target = line[2:].rsplit(" -> ", 1)
            parts = left.rsplit(" - ", 1)
            title = parts[0].strip() if parts else left.strip()
            artist = parts[1].strip() if len(parts) == 2 else ""
            target = target.strip()

            if target.startswith("pos:"):
                pos = int(target[4:])
                ops.append(PlanOperation(
                    action="assign_section", track_title=title, track_artist=artist,
                    position=pos, reason=f"move to position {pos}",
                ))
            elif target.startswith("sec:"):
                sec_parts = target[4:].split(":", 1)
                section = sec_parts[0]
                sec_pos = int(sec_parts[1]) if len(sec_parts) > 1 else None
                ops.append(PlanOperation(
                    action="assign_section", track_title=title, track_artist=artist,
                    section_name=section, position=sec_pos,
                    reason=f"move to section {section}" + (f" position {sec_pos}" if sec_pos else ""),
                ))
    return ops


def apply_plan(db: Database, plan: BatchPlan) -> tuple[int, int]:
    """Apply a plan: execute ALL local DB changes first, then sync.

    DB changes are atomic (all happen or none). Platform sync happens after
    and failures don't affect local state. History records only what actually
    executed.

    Returns (removals_applied, additions_applied).
    """
    removed = 0
    added = 0
    executed_ops: list[dict] = []

    # Phase 1: Execute ALL local DB changes (no platform sync yet)
    for op in plan.removals:
        if op.track_id is None:
            continue
        tracks = db.get_playlist_tracks(plan.playlist_id)
        track = next((t for t in tracks if t.id == op.track_id), None)
        if track is None:
            continue
        position = next(
            (i for i, t in enumerate(tracks) if t.id == op.track_id), 0
        )
        db.remove_track_from_playlist(plan.playlist_id, track.id)
        removed += 1
        executed_ops.append({
            "action": "rm", "track": op.track_title, "artist": op.track_artist,
            "track_id": op.track_id, "reason": op.reason,
            "position": position, "previous_position": position,
            "previous_section": op.previous_section,
        })

    for op in plan.additions:
        if not op.track_title:
            continue
        tracks_found = db.find_tracks_by_title_artist(op.track_title, op.track_artist)
        if tracks_found:
            track = tracks_found[0]
            existing = db.get_playlist_tracks(plan.playlist_id)
            # Skip if already in playlist
            if any(t.id == track.id for t in existing):
                continue
            next_pos = len(existing)
            db.conn.execute(
                "INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES (?, ?, ?)",
                (plan.playlist_id, track.id, next_pos),
            )
            db.conn.commit()
            added += 1
            executed_ops.append({
                "action": "add", "track": op.track_title, "artist": op.track_artist,
                "track_id": track.id, "reason": op.reason,
                "position": next_pos, "previous_position": None,
                "previous_section": None,
            })

    # Phase 2: Record ONLY what actually executed in history
    if executed_ops:
        db.record_batch(plan.playlist_id, json.dumps({
            "playlist": plan.playlist_name,
            "created": plan.created_at,
            "operations": executed_ops,
        }))

    # Phase 3: Auto-reorder if enabled
    playlist_row = db.conn.execute(
        "SELECT auto_reorder, reorder_arc FROM playlists WHERE id = ?",
        (plan.playlist_id,),
    ).fetchone()
    if playlist_row and playlist_row[0]:
        from tuneshift.sequencer.optimizer import sequence_playlist
        arc = playlist_row[1] or "wave"
        sequence_playlist(db, plan.playlist_id, arc=arc)

    # Phase 4: Report sync instructions
    if removed or added:
        print(f"  Run `tuneshift sync \"{plan.playlist_name}\" <platform>` to push changes.")

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


def undo_batch(db: Database, history_id: int | None = None) -> bool:
    """Undo a specific batch plan by reversing its operations.

    If history_id is None, undoes the most recent non-reverted plan.
    Returns True if successful.
    """
    if history_id is None:
        row = db.conn.execute(
            "SELECT id, playlist_id, plan_json FROM batch_history "
            "WHERE reverted_at IS NULL ORDER BY applied_at DESC LIMIT 1"
        ).fetchone()
    else:
        row = db.conn.execute(
            "SELECT id, playlist_id, plan_json FROM batch_history WHERE id = ?",
            (history_id,),
        ).fetchone()

    if row is None:
        return False

    hid, playlist_id, plan_json_str = row[0], row[1], row[2]
    plan_data = json.loads(plan_json_str)

    # Reverse each operation
    for op in plan_data.get("operations", []):
        if op["action"] == "rm" and op.get("track_id"):
            # Re-add the track at its previous position
            pos = op.get("previous_position", op.get("position"))
            existing = db.get_playlist_tracks(playlist_id)
            insert_pos = min(pos, len(existing)) if pos is not None else len(existing)
            # Shift positions down to make room (from end to avoid PK conflicts)
            max_pos = db.conn.execute(
                "SELECT MAX(position) FROM playlist_tracks WHERE playlist_id = ?",
                (playlist_id,),
            ).fetchone()[0] or 0
            for shift_pos in range(max_pos, insert_pos - 1, -1):
                db.conn.execute(
                    "UPDATE playlist_tracks SET position = ? "
                    "WHERE playlist_id = ? AND position = ?",
                    (shift_pos + 1, playlist_id, shift_pos),
                )
            db.conn.execute(
                "INSERT OR IGNORE INTO playlist_tracks (playlist_id, track_id, position) "
                "VALUES (?, ?, ?)",
                (playlist_id, op["track_id"], insert_pos),
            )
        elif op["action"] == "add" and op.get("track_id"):
            # Remove the track that was added
            db.conn.execute(
                "DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
                (playlist_id, op["track_id"]),
            )
            # Re-compact positions
            tracks = db.get_playlist_tracks(playlist_id)
            for i, t in enumerate(tracks):
                db.conn.execute(
                    "UPDATE playlist_tracks SET position = ? "
                    "WHERE playlist_id = ? AND track_id = ?",
                    (i, playlist_id, t.id),
                )

    db.conn.commit()
    db.mark_batch_reverted(hid)
    return True


def handle_batch(args, db: Database) -> int:
    """Handle batch operations: plan, show, apply, discard, undo, history."""
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

    # History
    if getattr(args, "history", False):
        playlist_name = args.playlist or args.history
        playlist = db.find_playlist_by_name(playlist_name) if isinstance(playlist_name, str) else None
        if playlist is None:
            # Show all history
            rows = db.conn.execute(
                "SELECT id, playlist_id, applied_at, reverted_at, plan_json "
                "FROM batch_history ORDER BY applied_at DESC LIMIT 20"
            ).fetchall()
        else:
            rows = db.conn.execute(
                "SELECT id, playlist_id, applied_at, reverted_at, plan_json "
                "FROM batch_history WHERE playlist_id = ? ORDER BY applied_at DESC",
                (playlist.id,),
            ).fetchall()

        if not rows:
            print("No batch history found.")
            return 0

        for row in rows:
            plan_data = json.loads(row[4])
            status = "REVERTED" if row[3] else "active"
            op_count = len(plan_data.get("operations", []))
            rm_count = sum(1 for o in plan_data.get("operations", []) if o["action"] == "rm")
            print(f"  #{row[0]} [{status}] {row[2]} - {plan_data.get('playlist', '?')} "
                  f"({op_count} ops, {rm_count} removals)")
        return 0

    # Undo
    if getattr(args, "undo", False):
        undo_id = getattr(args, "id", None)
        if undo_batch(db, undo_id):
            print(f"Undone: plan #{undo_id or 'last'} reversed.")
        else:
            print("Nothing to undo.", file=sys.stderr)
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
        removed, added = apply_plan(db, plan)
        print(f"\nApplied: {removed} removed, {added} added")
        BatchPlan.discard()
        return 0

    # Sweep banned (works with or without playlist)
    if getattr(args, "sweep_banned", False):
        playlist = db.find_playlist_by_name(args.playlist) if args.playlist else None
        results = plan_sweep_banned(db, playlist.id if playlist else None)
        if not results:
            print("No banned artists found.")
            return 0

        # For single playlist, create one plan
        if playlist:
            ops = results.get(playlist.id, [])
            plan = BatchPlan(playlist_name=playlist.name, playlist_id=playlist.id, operations=ops)
            print(render_plan(plan))
            if getattr(args, "plan", False):
                plan.save()
                print("\nPlan saved. Apply with: tuneshift batch --apply")
            return 0

        # Multi-playlist: show summary
        total_ops = sum(len(ops) for ops in results.values())
        print(f"Banned artist sweep: {total_ops} tracks across {len(results)} playlists")
        for pid, ops in results.items():
            pl_name = db.conn.execute("SELECT name FROM playlists WHERE id = ?", (pid,)).fetchone()[0]
            print(f"  {pl_name}: {len(ops)} tracks")
            for op in ops:
                print(f"    - \"{op.track_title}\" by {op.track_artist} ({op.reason})")
        if getattr(args, "plan", False):
            # Save the first playlist's plan (multi-playlist sweep applies sequentially)
            first_pid = next(iter(results))
            first_name = db.conn.execute("SELECT name FROM playlists WHERE id = ?", (first_pid,)).fetchone()[0]
            plan = BatchPlan(playlist_name=first_name, playlist_id=first_pid, operations=results[first_pid])
            plan.save()
            print(f"\nSaved plan for \"{first_name}\". Apply sequentially with: tuneshift batch --apply")
        return 0

    # Generate a plan (requires playlist name for most operations)
    if not args.playlist:
        print("Playlist name required for plan generation.", file=sys.stderr)
        return 1

    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        print(f"Playlist not found: {args.playlist}", file=sys.stderr)
        return 1

    # Check mutual exclusivity
    if getattr(args, "interactive", False) and getattr(args, "from_stdin", False):
        print("--interactive and --from-stdin are mutually exclusive.", file=sys.stderr)
        return 1

    ops: list[PlanOperation] = []

    # Multi-rm/add from CLI flags
    for rm_title in (getattr(args, "rm", None) or []):
        parts = rm_title.rsplit(" - ", 1)
        title = parts[0].strip()
        artist = parts[1].strip() if len(parts) == 2 else ""
        # Find matching track
        tracks = db.get_playlist_tracks(playlist.id)
        for i, t in enumerate(tracks):
            if t.title.casefold() == title.casefold() or title.casefold() in t.title.casefold():
                if not artist or t.artist.casefold() == artist.casefold():
                    ops.append(PlanOperation(
                        action="rm", track_title=t.title, track_artist=t.artist,
                        track_id=t.id, position=i, previous_position=i,
                        reason="CLI --rm",
                    ))
                    break

    for add_spec in (getattr(args, "add", None) or []):
        parts = add_spec.rsplit(" - ", 1)
        title = parts[0].strip()
        artist = parts[1].strip() if len(parts) == 2 else ""
        ops.append(PlanOperation(action="add", track_title=title, track_artist=artist, reason="CLI --add"))

    # Plan file input
    plan_file = getattr(args, "plan_file", None)
    if plan_file:
        content = Path(plan_file).read_text()
        ops.extend(parse_plan_file(content))

    # Stdin input
    if getattr(args, "from_stdin", False):
        import sys as _sys
        if not _sys.stdin.isatty():
            content = _sys.stdin.read()
            ops.extend(parse_plan_file(content))

    # Existing operations
    if getattr(args, "dedupe", False):
        cap = getattr(args, "cap", 1)
        if getattr(args, "interactive", False):
            ops.extend(_interactive_dedupe(db, playlist.id, cap))
        else:
            ops.extend(plan_dedupe(db, playlist.id, cap))

    if getattr(args, "rm_artist", None):
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
        print()
        confirm = input("Apply now? [y/N] ").strip().lower()
        if confirm in ("y", "yes"):
            removed, added = apply_plan(db, plan)
            print(f"\nApplied: {removed} removed, {added} added")
        else:
            plan_path = plan.save()
            print(f"Plan saved to {plan_path}. Apply with: tuneshift batch --apply")

    return 0
