"""Import/sync module: create and update Tidal playlists from reconciled tracks."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tidal_importer.client import TidalClientProtocol, PlaylistInfo, TrackResult
from tidal_importer.reconcile import ReconciledTrack, load_reconciled


@dataclass
class ImportResult:
    """Result of a playlist import/sync operation."""
    playlist_id: str
    playlist_name: str
    tracks_added: int
    tracks_removed: int
    tracks_reordered: bool
    tracks_skipped: int
    total_in_playlist: int


@dataclass
class SyncPlan:
    """Plan for syncing a playlist before execution."""
    to_add: list[int]
    to_remove: list[int]
    final_order: list[int]
    already_present: int


def build_sync_plan(
    reconciled: list[ReconciledTrack],
    current_track_ids: list[int],
    remove_extra: bool = True,
) -> SyncPlan:
    """Build a sync plan from reconciled tracks and current playlist state.
    
    Args:
        reconciled: List of reconciled tracks (from CSV order)
        current_track_ids: Current ordered tidal_ids in the playlist
        remove_extra: If True, tracks in playlist not in CSV are removed
    
    Returns:
        SyncPlan with add/remove/reorder instructions
    """
    # Desired IDs from reconciled (only matched/already_in_playlist with tidal_id)
    desired_ids = [
        t.tidal_id for t in reconciled
        if t.tidal_id is not None and t.status in ("matched", "already_in_playlist")
    ]
    
    current_set = set(current_track_ids)
    desired_set = set(desired_ids)
    
    to_add = [tid for tid in desired_ids if tid not in current_set]
    to_remove = [tid for tid in current_track_ids if tid not in desired_set] if remove_extra else []
    already_present = len(desired_set & current_set)
    
    # Final order is the desired order
    final_order = desired_ids
    
    return SyncPlan(
        to_add=to_add,
        to_remove=to_remove,
        final_order=final_order,
        already_present=already_present,
    )


def import_playlist(
    reconciled_path: Path,
    playlist_name: str,
    client: TidalClientProtocol,
    existing_playlist_id: str | None = None,
    remove_extra: bool = True,
    dry_run: bool = False,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> ImportResult:
    """Import/sync a reconciled JSON to a Tidal playlist.
    
    Args:
        reconciled_path: Path to .reconciled.json
        playlist_name: Name for new playlist (or verification for existing)
        client: TidalClient (real or fake)
        existing_playlist_id: If provided, sync to existing playlist
        remove_extra: Remove tracks from playlist not in CSV
        dry_run: If True, build plan but don't execute
        progress_callback: Called with (phase, current, total)
    
    Workflow:
    1. Load reconciled JSON
    2. If existing_playlist_id: fetch current tracks, build sync plan
    3. If no existing: create new playlist
    4. Execute plan: remove extras, add new tracks, reorder
    5. Return ImportResult
    """
    # 1. Load reconciled JSON
    if progress_callback:
        progress_callback("loading", 0, 1)
    
    reconciled = load_reconciled(reconciled_path)
    
    if progress_callback:
        progress_callback("loading", 1, 1)
    
    # Count skipped tracks (ambiguous + not_found + tracks without tidal_id)
    tracks_skipped = sum(
        1 for t in reconciled
        if t.status in ("ambiguous", "not_found") or t.tidal_id is None
    )
    
    # 2. Determine if syncing existing or creating new
    if existing_playlist_id:
        # Sync to existing playlist
        current_tracks = client.get_playlist_tracks(existing_playlist_id)
        current_track_ids = [t.tidal_id for t in current_tracks]
        
        # Build sync plan
        plan = build_sync_plan(reconciled, current_track_ids, remove_extra)
        
        playlist_id = existing_playlist_id
        
        if dry_run:
            # Return plan stats without executing
            return ImportResult(
                playlist_id=playlist_id,
                playlist_name=playlist_name,
                tracks_added=len(plan.to_add),
                tracks_removed=len(plan.to_remove),
                tracks_reordered=plan.final_order != current_track_ids,
                tracks_skipped=tracks_skipped,
                total_in_playlist=len(plan.final_order),
            )
        
        # Execute plan
        tracks_removed = 0
        if plan.to_remove:
            if progress_callback:
                progress_callback("removing", 0, len(plan.to_remove))
            tracks_removed = client.remove_tracks(playlist_id, plan.to_remove)
            if progress_callback:
                progress_callback("removing", len(plan.to_remove), len(plan.to_remove))
        
        tracks_added = 0
        if plan.to_add:
            if progress_callback:
                progress_callback("adding", 0, len(plan.to_add))
            tracks_added = client.add_tracks(playlist_id, plan.to_add)
            if progress_callback:
                progress_callback("adding", len(plan.to_add), len(plan.to_add))
        
        # Check if reorder is needed
        current_after_changes = client.get_playlist_tracks(playlist_id)
        current_ids_after = [t.tidal_id for t in current_after_changes]
        
        tracks_reordered = False
        # Only reorder if we removed extras (all current tracks are in desired)
        # or if order doesn't match
        if remove_extra and current_ids_after != plan.final_order:
            if progress_callback:
                progress_callback("reordering", 0, 1)
            client.set_playlist_order(playlist_id, plan.final_order)
            tracks_reordered = True
            if progress_callback:
                progress_callback("reordering", 1, 1)
        elif not remove_extra:
            # When keeping extras, check if desired tracks are in order (ignoring extras)
            desired_set = set(plan.final_order)
            filtered_current = [tid for tid in current_ids_after if tid in desired_set]
            if filtered_current != plan.final_order:
                # Need to reorder: place desired tracks first, then extras
                new_order = plan.final_order + [tid for tid in current_ids_after if tid not in desired_set]
                if progress_callback:
                    progress_callback("reordering", 0, 1)
                client.set_playlist_order(playlist_id, new_order)
                tracks_reordered = True
                if progress_callback:
                    progress_callback("reordering", 1, 1)
        
        return ImportResult(
            playlist_id=playlist_id,
            playlist_name=playlist_name,
            tracks_added=tracks_added,
            tracks_removed=tracks_removed,
            tracks_reordered=tracks_reordered,
            tracks_skipped=tracks_skipped,
            total_in_playlist=len(plan.final_order),
        )
    
    else:
        # Create new playlist
        plan = build_sync_plan(reconciled, current_track_ids=[], remove_extra=False)
        
        if dry_run:
            # Return plan stats without creating
            return ImportResult(
                playlist_id="dry-run-id",
                playlist_name=playlist_name,
                tracks_added=len(plan.to_add),
                tracks_removed=0,
                tracks_reordered=False,
                tracks_skipped=tracks_skipped,
                total_in_playlist=len(plan.final_order),
            )
        
        # Create playlist
        playlist_info = client.create_playlist(playlist_name, description="")
        playlist_id = playlist_info.playlist_id
        
        # Add all tracks
        tracks_added = 0
        if plan.to_add:
            if progress_callback:
                progress_callback("adding", 0, len(plan.to_add))
            tracks_added = client.add_tracks(playlist_id, plan.to_add)
            if progress_callback:
                progress_callback("adding", len(plan.to_add), len(plan.to_add))
        
        return ImportResult(
            playlist_id=playlist_id,
            playlist_name=playlist_name,
            tracks_added=tracks_added,
            tracks_removed=0,
            tracks_reordered=False,
            tracks_skipped=tracks_skipped,
            total_in_playlist=len(plan.final_order),
        )
