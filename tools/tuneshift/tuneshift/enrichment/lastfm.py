"""Last.fm API client for track and artist tag lookups."""

from __future__ import annotations

import json
import urllib.request
import urllib.parse
from pathlib import Path

_TOKEN_DIR = Path.home() / ".local" / "share" / "tuneshift"
_BASE_URL = "https://ws.audioscrobbler.com/2.0/"


def _load_api_key() -> str | None:
    """Load Last.fm API key from config file or environment."""
    import os
    key = os.environ.get("LASTFM_API_KEY")
    if key:
        return key
    key_file = _TOKEN_DIR / "lastfm_key"
    if key_file.exists():
        return key_file.read_text().strip()
    return None


def _request(method: str, params: dict) -> dict:
    """Make a Last.fm API request."""
    api_key = _load_api_key()
    if not api_key:
        raise ValueError("No Last.fm API key configured. Run: tuneshift config lastfm-key <key>")

    params.update({
        "method": method,
        "api_key": api_key,
        "format": "json",
    })
    query = urllib.parse.urlencode(params)
    url = f"{_BASE_URL}?{query}"

    req = urllib.request.Request(url, headers={"User-Agent": "tuneshift/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def get_track_tags(title: str, artist: str) -> list[str]:
    """Get top tags for a track from Last.fm."""
    try:
        data = _request("track.getTopTags", {
            "track": title,
            "artist": artist,
        })
        tags = data.get("toptags", {}).get("tag", [])
        if isinstance(tags, dict):
            tags = [tags]
        return [t["name"].lower() for t in tags[:15] if int(t.get("count", 0)) > 0]
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return []


def get_artist_tags(artist: str) -> list[str]:
    """Get top tags for an artist from Last.fm."""
    try:
        data = _request("artist.getTopTags", {"artist": artist})
        tags = data.get("toptags", {}).get("tag", [])
        if isinstance(tags, dict):
            tags = [tags]
        return [t["name"].lower() for t in tags[:15] if int(t.get("count", 0)) > 0]
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return []


def is_available() -> bool:
    """Check if Last.fm API key is configured."""
    return _load_api_key() is not None
