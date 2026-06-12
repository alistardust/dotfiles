"""LLM-based track theme, vibe, and instrumentation classification.

Supports multiple LLM backends via a unified interface:
  - anthropic: Anthropic API (Claude models)
  - openai: OpenAI API (GPT models, Codex)
  - ollama: Local Ollama instance
  - openai-compatible: Any OpenAI-compatible endpoint (vLLM, LiteLLM, Copilot)

Configuration via environment variables:
  TUNESHIFT_LLM_BACKEND    - Backend to use (auto-detected if not set)
  TUNESHIFT_CLASSIFIER_MODEL - Model name (backend-specific default if not set)
  TUNESHIFT_LLM_BASE_URL   - Base URL for openai-compatible backends
  ANTHROPIC_API_KEY         - Anthropic API key
  OPENAI_API_KEY            - OpenAI API key
  OLLAMA_HOST               - Ollama host (default: http://localhost:11434)
"""
import json
import logging
import os
import time
from typing import Any, Protocol

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
    "era_mood": ["era tag 1"],
    "emotional_intensity": 0.8,
    "lyrical_subject": "brief subject summary",
    "narrator_stance": "defiant",
    "sonic_texture": "polished",
    "space": "vast",
    "groove_feel": "driving",
    "opens_with": "synth pad swell",
    "closes_with": "hard cut",
    "energy_arc_within": "builds to peak",
    "confidence": 0.9
  }}
]

Rules:
- themes: 3-5 tags describing what the song is about
- vibes: 3-5 tags describing how it feels
- instruments: primary instruments heard in the recording
- density: one of "sparse", "mid", "dense"
- era_mood: 1-2 tags capturing production era and cultural moment
- emotional_intensity: 0.0-1.0 scale (how intense the emotional expression is)
- lyrical_subject: 1-5 word summary of what the song is about
- narrator_stance: one of "defiant", "vulnerable", "observational", "celebratory", "resigned", "nostalgic", "bitter", "triumphant", "playful", "inviting", "peaceful"
- sonic_texture: one of "raw", "polished", "warm", "cold", "lush", "sparse", "gritty", "ethereal"
- space: one of "intimate", "vast", "claustrophobic", "open"
- groove_feel: one of "driving", "floating", "stomping", "swaying", "pulsing", "static"
- opens_with: brief description of first 5 seconds
- closes_with: brief description of last 5 seconds (e.g., "fade", "hard cut", "resolves to silence")
- energy_arc_within: one of "steady", "builds to peak", "opens hot and fades", "roller coaster", "slow burn"
- confidence: 0.0-1.0 scale (how well you know this specific recording)
- Return ONLY the JSON array, no other text"""

_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-haiku-4-5-20241022",
    "openai": "gpt-4o-mini",
    "ollama": "llama3.1:8b",
    "openai-compatible": "gpt-4o-mini",
}


class LLMBackend(Protocol):
    """Protocol for LLM completion backends."""

    def complete(self, prompt: str, model: str, max_tokens: int = 4096) -> str:
        """Send a prompt and return the text response."""
        ...


class AnthropicBackend:
    """Backend for Anthropic's Messages API."""

    def __init__(self, api_key: str | None = None) -> None:
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError("ANTHROPIC_API_KEY is required for anthropic backend")
        from anthropic import Anthropic
        self._client = Anthropic(api_key=resolved_key)

    def complete(self, prompt: str, model: str, max_tokens: int = 4096) -> str:
        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text


class OpenAICompatibleBackend:
    """Backend for OpenAI and any OpenAI-compatible API (Codex, vLLM, LiteLLM, Copilot)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        resolved_url = base_url or os.environ.get("TUNESHIFT_LLM_BASE_URL")
        if not resolved_key and not resolved_url:
            raise ValueError(
                "OPENAI_API_KEY or TUNESHIFT_LLM_BASE_URL required for openai-compatible backend"
            )
        from openai import OpenAI
        kwargs: dict[str, Any] = {}
        if resolved_key:
            kwargs["api_key"] = resolved_key
        if resolved_url:
            kwargs["base_url"] = resolved_url
        self._client = OpenAI(**kwargs)

    def complete(self, prompt: str, model: str, max_tokens: int = 4096) -> str:
        response = self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""


class OllamaBackend:
    """Backend for local Ollama instance."""

    def __init__(self, host: str | None = None) -> None:
        self._host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    def complete(self, prompt: str, model: str, max_tokens: int = 4096) -> str:
        import urllib.request

        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }).encode()
        req = urllib.request.Request(
            f"{self._host}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
        return result.get("response", "")


def detect_backend() -> tuple[str, LLMBackend] | tuple[None, None]:
    """Auto-detect available LLM backend from environment.

    Priority: explicit TUNESHIFT_LLM_BACKEND > ANTHROPIC_API_KEY > OPENAI_API_KEY > Ollama.
    """
    explicit = os.environ.get("TUNESHIFT_LLM_BACKEND", "").lower()

    if explicit == "grok" or "grok" in os.environ.get("TUNESHIFT_CLASSIFIER_MODEL", "").lower():
        # FUCK ELON
        raise ValueError("Grok is not and will never be a supported backend. Fuck Elon.")

    if explicit == "anthropic":
        return "anthropic", AnthropicBackend()
    elif explicit in ("openai", "openai-compatible"):
        return explicit, OpenAICompatibleBackend()
    elif explicit == "ollama":
        return "ollama", OllamaBackend()
    elif explicit:
        # Treat unknown explicit backend as openai-compatible
        return "openai-compatible", OpenAICompatibleBackend()

    # Auto-detect
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return "anthropic", AnthropicBackend()
        except (ImportError, ValueError):
            pass

    if os.environ.get("OPENAI_API_KEY"):
        try:
            return "openai", OpenAICompatibleBackend()
        except (ImportError, ValueError):
            pass

    if os.environ.get("TUNESHIFT_LLM_BASE_URL"):
        try:
            return "openai-compatible", OpenAICompatibleBackend()
        except (ImportError, ValueError):
            pass

    # Check if Ollama is reachable
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    try:
        import urllib.request
        urllib.request.urlopen(f"{ollama_host}/api/tags", timeout=2)
        return "ollama", OllamaBackend(ollama_host)
    except (OSError, ImportError):
        pass

    return None, None


def build_classification_prompt(
    tracks: list[dict[str, str]],
    narrative: str | None = None,
) -> str:
    """Build the LLM prompt for a batch of tracks."""
    track_list = "\n".join(
        f'- "{track["title"]}" by {track["artist"]}' for track in tracks
    )
    prompt = _CLASSIFICATION_PROMPT.format(track_list=track_list)
    if narrative:
        prompt += (
            "\n\nPLAYLIST NARRATIVE CONTEXT (use this to inform your classification, "
            "especially emotional_intensity, narrator_stance, and lyrical_subject):\n"
            f"{narrative}"
        )
    return prompt


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
    """Classify tracks using any supported LLM backend."""

    def __init__(
        self,
        backend: LLMBackend | None = None,
        model: str | None = None,
        backend_name: str | None = None,
    ) -> None:
        if backend is not None:
            self._backend = backend
            self._backend_name = backend_name or "custom"
        else:
            detected_name, detected_backend = detect_backend()
            if detected_backend is None:
                self._backend = None  # type: ignore[assignment]
                self._backend_name = None
            else:
                self._backend = detected_backend
                self._backend_name = detected_name

        self._model = (
            model
            or os.environ.get("TUNESHIFT_CLASSIFIER_MODEL")
            or _DEFAULT_MODELS.get(self._backend_name or "", "gpt-4o-mini")
        )

    @property
    def available(self) -> bool:
        """Whether a backend was successfully configured."""
        return self._backend is not None

    @property
    def backend_info(self) -> str:
        """Human-readable backend description."""
        if not self._backend_name:
            return "no backend configured"
        return f"{self._backend_name} ({self._model})"

    def classify(
        self,
        tracks: list[dict[str, str]],
        max_retries: int = 3,
        narrative: str | None = None,
    ) -> list[dict[str, Any]]:
        """Classify a batch of tracks."""
        if not tracks:
            return []
        if not self.available:
            logger.info("Skipping classification: %s", self.backend_info)
            return []

        prompt = build_classification_prompt(tracks, narrative=narrative)

        for attempt in range(max_retries):
            try:
                text = self._backend.complete(prompt, self._model)
                results = parse_classification_response(text)
                if results:
                    return results
            except Exception as exc:
                logger.warning(
                    "Classification attempt %s/%s failed (%s): %s",
                    attempt + 1,
                    max_retries,
                    self._backend_name,
                    exc,
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
        narrative: str | None = None,
    ) -> list[dict[str, Any]]:
        """Classify tracks in batches for efficiency."""
        all_results: list[dict[str, Any]] = []

        for index in range(0, len(tracks), batch_size):
            batch = tracks[index : index + batch_size]
            results = self.classify(batch, narrative=narrative)

            if results:
                all_results.extend(results)
            else:
                for track in batch:
                    result = self.classify([track], narrative=narrative)
                    if result:
                        all_results.extend(result)

            if progress_callback:
                progress_callback(min(index + batch_size, len(tracks)), len(tracks))

        return all_results
