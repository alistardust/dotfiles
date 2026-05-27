"""Track reconciliation: CSV parsing, matching, and playlist diff."""
import csv
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable
from datetime import datetime, UTC

from tidal_importer.client import TidalClientProtocol, TrackResult
from tidal_importer.matching import score_match, classify_results, is_remaster



@dataclass
class SourceTrack:
    """A track from the CSV source."""
    title: str
    artist: str
    album: str | None
    row_number: int


@dataclass
class ReconciledTrack:
    """A track after reconciliation."""
    source: SourceTrack
    status: str  # "matched" | "ambiguous" | "not_found" | "already_in_playlist"
    confidence: str  # "high" | "ambiguous" | "not_found"
    tidal_id: int | None
    tidal_title: str | None
    tidal_artist: str | None
    tidal_album: str | None
    score: int
    alternatives: list[dict]


def parse_csv(csv_path: Path) -> list[SourceTrack]:
    """Parse a Soundiiz CSV file into SourceTrack list.
    CSV format: title,artist,album (with header row).
    """
    tracks = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=1):
            title = row.get("title", "").strip()
            artist = row.get("artist", "").strip()
            album = row.get("album", "").strip()
            tracks.append(SourceTrack(
                title=title,
                artist=artist,
                album=album if album else None,
                row_number=idx,
            ))
    return tracks


def reconcile_track(
    source: SourceTrack,
    client: TidalClientProtocol,
    existing_track_ids: set[int] | None = None,
) -> ReconciledTrack:
    """Search Tidal for a single track, score results, classify.
    
    If existing_track_ids is provided and a match is found in that set,
    mark as 'already_in_playlist'.
    Prefer remasters when breaking ties between equal scores.
    """
    # Try to search Tidal
    try:
        query = f'"{source.title}" {source.artist}'
        results = client.search_track(query, limit=10)
    except Exception:
        # Search error - treat as not found
        return ReconciledTrack(
            source=source,
            status="not_found",
            confidence="not_found",
            tidal_id=None,
            tidal_title=None,
            tidal_artist=None,
            tidal_album=None,
            score=0,
            alternatives=[],
        )
    
    if not results:
        return ReconciledTrack(
            source=source,
            status="not_found",
            confidence="not_found",
            tidal_id=None,
            tidal_title=None,
            tidal_artist=None,
            tidal_album=None,
            score=0,
            alternatives=[],
        )
    
    # Score all results
    scored_results = []
    for result in results:
        score = score_match(
            source.title,
            source.artist,
            source.album,
            result.title,
            result.artist,
            result.album,
        )
        scored_results.append((score, result))
    
    # Sort by score (desc), then prefer remasters on ties
    scored_results.sort(
        key=lambda x: (x[0], is_remaster(x[1].album)),
        reverse=True
    )
    
    # Get top match
    top_score, top_result = scored_results[0]
    
    # Classify confidence
    scores = [s for s, _ in scored_results]
    confidence = classify_results(scores)
    
    # Check if already in playlist
    if existing_track_ids and top_result.tidal_id in existing_track_ids:
        if confidence != "not_found":
            return ReconciledTrack(
                source=source,
                status="already_in_playlist",
                confidence=confidence,
                tidal_id=top_result.tidal_id,
                tidal_title=top_result.title,
                tidal_artist=top_result.artist,
                tidal_album=top_result.album,
                score=top_score,
                alternatives=[],
            )
    
    # Determine status based on confidence
    if confidence == "not_found":
        status = "not_found"
        tidal_id = None
        tidal_title = None
        tidal_artist = None
        tidal_album = None
    elif confidence == "high":
        status = "matched"
        tidal_id = top_result.tidal_id
        tidal_title = top_result.title
        tidal_artist = top_result.artist
        tidal_album = top_result.album
    else:  # ambiguous
        status = "ambiguous"
        tidal_id = top_result.tidal_id
        tidal_title = top_result.title
        tidal_artist = top_result.artist
        tidal_album = top_result.album
    
    # Build alternatives list (top 3)
    alternatives = []
    if status == "ambiguous":
        for score, result in scored_results[:3]:
            alternatives.append({
                "tidal_id": result.tidal_id,
                "title": result.title,
                "artist": result.artist,
                "album": result.album,
                "score": score,
            })
    
    return ReconciledTrack(
        source=source,
        status=status,
        confidence=confidence,
        tidal_id=tidal_id,
        tidal_title=tidal_title,
        tidal_artist=tidal_artist,
        tidal_album=tidal_album,
        score=top_score,
        alternatives=alternatives,
    )


def reconcile_playlist(
    csv_path: Path,
    client: TidalClientProtocol,
    existing_playlist_id: str | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[ReconciledTrack]:
    """Reconcile all tracks from a CSV.
    
    If existing_playlist_id is provided:
    1. Fetch current tracks from playlist
    2. Build set of existing tidal_ids
    3. For each CSV track, if already matched in playlist, mark as already_in_playlist
    4. Only search Tidal for tracks NOT already in the playlist
    """
    # Parse CSV
    source_tracks = parse_csv(csv_path)
    
    # Get existing track IDs if playlist specified
    existing_track_ids = None
    if existing_playlist_id:
        try:
            existing_tracks = client.get_playlist_tracks(existing_playlist_id)
            existing_track_ids = {t.tidal_id for t in existing_tracks}
        except Exception:
            # If we can't fetch existing tracks, proceed without them
            existing_track_ids = None
    
    # Reconcile each track
    results = []
    total = len(source_tracks)
    for idx, source_track in enumerate(source_tracks, start=1):
        reconciled = reconcile_track(source_track, client, existing_track_ids)
        results.append(reconciled)
        
        if progress_callback:
            progress_callback(idx, total)
    
    return results


def save_reconciled(
    tracks: list[ReconciledTrack],
    output_path: Path,
) -> None:
    """Save reconciled tracks to JSON file.
    
    JSON schema:
    {
        "generated_at": "ISO timestamp",
        "total": N,
        "matched": N,
        "ambiguous": N,
        "not_found": N,
        "already_in_playlist": N,
        "tracks": [...]
    }
    """
    # Count statuses
    status_counts = {
        "matched": 0,
        "ambiguous": 0,
        "not_found": 0,
        "already_in_playlist": 0,
    }
    for track in tracks:
        if track.status in status_counts:
            status_counts[track.status] += 1
    
    # Build JSON structure
    data = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total": len(tracks),
        "matched": status_counts["matched"],
        "ambiguous": status_counts["ambiguous"],
        "not_found": status_counts["not_found"],
        "already_in_playlist": status_counts["already_in_playlist"],
        "tracks": [
            {
                "source": asdict(track.source),
                "status": track.status,
                "confidence": track.confidence,
                "tidal_id": track.tidal_id,
                "tidal_title": track.tidal_title,
                "tidal_artist": track.tidal_artist,
                "tidal_album": track.tidal_album,
                "score": track.score,
                "alternatives": track.alternatives,
            }
            for track in tracks
        ]
    }
    
    json_str = json.dumps(data, indent=2)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json_str, encoding="utf-8")


def load_reconciled(json_path: Path) -> list[ReconciledTrack]:
    """Load and validate reconciled JSON. Raises ValueError on invalid schema."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")
    
    # Validate required top-level fields
    required_fields = ["tracks"]
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")
    
    # Validate and reconstruct tracks
    tracks = []
    valid_statuses = {"matched", "ambiguous", "not_found", "already_in_playlist"}
    valid_confidences = {"high", "ambiguous", "not_found"}
    
    for idx, track_data in enumerate(data["tracks"]):
        # Validate status
        status = track_data.get("status")
        if status not in valid_statuses:
            raise ValueError(f"Invalid status at track {idx}: {status}")
        
        # Validate confidence
        confidence = track_data.get("confidence")
        if confidence not in valid_confidences:
            raise ValueError(f"Invalid confidence at track {idx}: {confidence}")
        
        # Validate tidal_id if matched
        tidal_id = track_data.get("tidal_id")
        if tidal_id is not None and (not isinstance(tidal_id, int) or tidal_id <= 0):
            raise ValueError(f"Invalid tidal_id at track {idx}: {tidal_id}")
        
        # Reconstruct SourceTrack
        source_data = track_data.get("source", {})
        source = SourceTrack(
            title=source_data.get("title", ""),
            artist=source_data.get("artist", ""),
            album=source_data.get("album"),
            row_number=source_data.get("row_number", 0),
        )
        
        # Reconstruct ReconciledTrack
        reconciled = ReconciledTrack(
            source=source,
            status=status,
            confidence=confidence,
            tidal_id=tidal_id,
            tidal_title=track_data.get("tidal_title"),
            tidal_artist=track_data.get("tidal_artist"),
            tidal_album=track_data.get("tidal_album"),
            score=track_data.get("score", 0),
            alternatives=track_data.get("alternatives", []),
        )
        tracks.append(reconciled)
    
    return tracks
