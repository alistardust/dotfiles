"""MusicBrainz source for track identity resolution."""

from __future__ import annotations

import logging

import musicbrainzngs

from tidal_importer.identity.matching import duration_matches, match_title
from tidal_importer.identity.models import Evidence, RecordingCandidate, SourceResult

logger = logging.getLogger(__name__)

musicbrainzngs.set_useragent("TuneShift", "0.1", "tuneshift@example.com")


class MusicBrainzSource:
    """MusicBrainz API source for ISRC and text-based lookups."""

    def lookup_isrc(
        self, isrc: str, duration_ms: int | None = None
    ) -> SourceResult | None:
        """Look up a recording by ISRC."""
        try:
            result = musicbrainzngs.get_recordings_by_isrc(isrc)
        except musicbrainzngs.WebServiceError as e:
            logger.warning("MusicBrainz ISRC lookup failed for %s: %s", isrc, e)
            return None

        recordings = result.get("isrc", {}).get("recording-list", [])
        if not recordings:
            return None

        if len(recordings) == 1:
            rec = recordings[0]
            candidate = self._recording_to_candidate(rec)
            candidate.score = 0.97
            return SourceResult(
                recordings=[candidate],
                evidence=Evidence(
                    id=f"mb-isrc-{isrc}",
                    recording_id="",
                    source="musicbrainz",
                    evidence_type="isrc_match",
                    confidence=0.97,
                ),
            )

        # Multiple recordings: disambiguate by duration
        if duration_ms is not None:
            candidates = []
            for rec in recordings:
                length = rec.get("length")
                if length and duration_matches(duration_ms, int(length), tolerance_ms=5000):
                    candidate = self._recording_to_candidate(rec)
                    candidate.score = 0.92
                    candidates.append(candidate)
            if len(candidates) == 1:
                return SourceResult(
                    recordings=candidates,
                    evidence=Evidence(
                        id=f"mb-isrc-{isrc}-disambig",
                        recording_id="",
                        source="musicbrainz",
                        evidence_type="isrc_match",
                        confidence=0.92,
                    ),
                )

        # Cannot disambiguate: return all
        candidates = [self._recording_to_candidate(r) for r in recordings]
        for c in candidates:
            c.score = 0.92
        return SourceResult(
            recordings=candidates,
            evidence=Evidence(
                id=f"mb-isrc-{isrc}-multi",
                recording_id="",
                source="musicbrainz",
                evidence_type="isrc_match",
                confidence=0.92,
            ),
        )

    def search(
        self, artist: str, title: str, duration_ms: int | None = None
    ) -> SourceResult:
        """Search for a recording by artist and title."""
        query = f'artist:"{artist}" AND recording:"{title}"'
        try:
            result = musicbrainzngs.search_recordings(query=query, limit=10)
        except musicbrainzngs.WebServiceError as e:
            logger.warning("MusicBrainz search failed: %s", e)
            return SourceResult(recordings=[])

        candidates = []
        for rec in result.get("recording-list", []):
            candidate = self._recording_to_candidate(rec)
            title_score = match_title(title, candidate.title)
            if title_score < 0.85:
                continue
            if duration_ms and candidate.duration_ms:
                if not duration_matches(duration_ms, candidate.duration_ms, tolerance_ms=60000):
                    continue
            # Determine confidence based on match quality
            if title_score >= 0.90 and duration_ms and candidate.duration_ms:
                diff = abs(duration_ms - candidate.duration_ms)
                candidate.score = 0.85 if diff <= 10000 else 0.75
            else:
                candidate.score = 0.75
            candidates.append(candidate)

        candidates.sort(key=lambda c: c.score, reverse=True)

        best_confidence = candidates[0].score if candidates else 0.0
        evidence = Evidence(
            id=f"mb-search-{artist[:10]}-{title[:10]}",
            recording_id="",
            source="musicbrainz",
            evidence_type="text_search",
            confidence=best_confidence,
        ) if candidates else None

        return SourceResult(recordings=candidates, evidence=evidence)

    def get_release_group_info(self, release_group_id: str) -> dict:
        """Get release group type information."""
        try:
            result = musicbrainzngs.get_release_group_by_id(release_group_id)
        except musicbrainzngs.WebServiceError as e:
            logger.warning("MusicBrainz release-group lookup failed: %s", e)
            return {}

        rg = result.get("release-group", {})
        return {
            "id": rg.get("id"),
            "title": rg.get("title"),
            "primary_type": rg.get("primary-type"),
            "secondary_types": rg.get("secondary-type-list", []),
            "first_release_date": rg.get("first-release-date"),
        }

    def _recording_to_candidate(self, rec: dict) -> RecordingCandidate:
        artist_credit = rec.get("artist-credit", [])
        artist_name = ""
        if artist_credit:
            artist_name = artist_credit[0].get("artist", {}).get("name", "")

        return RecordingCandidate(
            title=rec.get("title", ""),
            artist=artist_name,
            mb_recording_id=rec.get("id"),
            duration_ms=int(rec["length"]) if rec.get("length") else None,
        )
