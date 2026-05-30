"""LLM-based track theme/vibe/instrumentation classification."""
import json
import time
from typing import Any


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
- themes: 3-5 tags describing what the song is about (lyrical content)
- vibes: 3-5 tags describing how it makes you feel (emotional quality)
- instruments: primary instruments heard in the recording
- density: one of "sparse", "mid", "dense"
- era_mood: 1-2 tags capturing production era and cultural moment
- Return ONLY the JSON array, no other text"""


def build_classification_prompt(tracks: list[dict[str, str]]) -> str:
    """Build the LLM prompt for a batch of tracks."""
    track_list = "\n".join(
        f'- "{track["title"]}" by {track["artist"]}' for track in tracks
    )
    return _CLASSIFICATION_PROMPT.format(track_list=track_list)


def parse_classification_response(response_text: str) -> list[dict[str, Any]]:
    """Parse LLM response into list of classification dicts."""
    text = response_text.strip()

    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        return []

    if isinstance(result, list):
        return result
    return []


class TrackClassifier:
    """Classify tracks using an LLM client for themes and vibe metadata."""

    def __init__(self, client: Any = None, model: str = "claude-haiku-4-5-20241022"):
        self._client = client
        self._model = model

    def classify(
        self,
        tracks: list[dict[str, str]],
        max_retries: int = 3,
    ) -> list[dict[str, Any]]:
        """Classify a batch of tracks."""
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
            except Exception:
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
