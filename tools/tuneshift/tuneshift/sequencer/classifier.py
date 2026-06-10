"""LLM-based track theme, vibe, and instrumentation classification."""
import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_CLASSIFICATION_PROMPT = """Classify the following tracks. Return a JSON array with one object per track.

{track_list}

Response format (JSON array):
[
  {{
    "title": "Track Title",
    "artist": "Artist Name",
    "themes": ["theme1", "theme2", "theme3"],
    "vibes": ["vibe1", "vibe2", "vibe3"],
    "instruments": ["instrument1", "instrument2"],
    "density": "sparse",
    "era_mood": ["era tag 1"]
  }}
]

Rules:
- themes: 3-5 tags describing what the song is about
- vibes: 3-5 tags describing how it feels
- instruments: primary instruments heard in the recording
- density: one of "sparse", "mid", "dense"
- era_mood: 1-2 tags capturing production era and cultural moment
- Return ONLY the JSON array, no other text"""


def build_default_client(api_key: str | None = None) -> Any | None:
    """Build a default Anthropic client when credentials are available."""
    resolved_api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not resolved_api_key:
        logger.info("Skipping classification because ANTHROPIC_API_KEY is not set")
        return None

    try:
        from anthropic import Anthropic
    except ImportError:
        logger.warning("Skipping classification because anthropic is not installed")
        return None

    return Anthropic(api_key=resolved_api_key)


def build_classification_prompt(tracks: list[dict[str, str]]) -> str:
    """Build the LLM prompt for a batch of tracks."""
    track_list = "\n".join(
        f'- "{track["title"]}" by {track["artist"]}' for track in tracks
    )
    return _CLASSIFICATION_PROMPT.format(track_list=track_list)


def parse_classification_response(response_text: str) -> list[dict[str, Any]]:
    """Parse an LLM response into classification dictionaries."""
    text = response_text.strip()

    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse classification response as JSON")
        return []

    if isinstance(result, list):
        return result
    return []


class TrackClassifier:
    """Classify tracks using an LLM client for themes and vibe metadata."""

    def __init__(
        self,
        client: Any = None,
        model: str = "claude-haiku-4-5-20241022",
    ) -> None:
        self._client = client if client is not None else build_default_client()
        self._model = model
        try:
            from anthropic import APIError
            self._api_errors: tuple = (OSError, KeyError, IndexError, ValueError, APIError)
        except ImportError:
            self._api_errors = (OSError, KeyError, IndexError, ValueError)

    def classify(
        self,
        tracks: list[dict[str, str]],
        max_retries: int = 3,
    ) -> list[dict[str, Any]]:
        """Classify a batch of tracks."""
        if not tracks:
            return []
        if self._client is None:
            logger.info("Skipping classification because no LLM client is configured")
            return []

        prompt = build_classification_prompt(tracks)

        for attempt in range(max_retries):
            try:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.content[0].text
                results = parse_classification_response(text)
                if results:
                    return results
            except self._api_errors as exc:
                logger.warning(
                    "Classification attempt %s/%s failed: %s",
                    attempt + 1,
                    max_retries,
                    exc,
                    exc_info=True,
                )
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                continue

        return []

    def classify_batched(
        self,
        tracks: list[dict[str, str]],
        batch_size: int = 20,
        progress_callback: Any = None,
    ) -> list[dict[str, Any]]:
        """Classify tracks in batches for efficiency."""
        all_results: list[dict[str, Any]] = []

        for index in range(0, len(tracks), batch_size):
            batch = tracks[index : index + batch_size]
            results = self.classify(batch)

            if results:
                all_results.extend(results)
            else:
                for track in batch:
                    result = self.classify([track])
                    if result:
                        all_results.extend(result)

            if progress_callback:
                progress_callback(min(index + batch_size, len(tracks)), len(tracks))

        return all_results
