"""Genius API client for lyrics lookup."""

from __future__ import annotations

import json
import re
import urllib.request
import urllib.parse
from pathlib import Path

_TOKEN_DIR = Path.home() / ".local" / "share" / "tuneshift"
_BASE_URL = "https://api.genius.com"


def _load_access_token() -> str | None:
    """Load Genius access token from config."""
    import os
    token = os.environ.get("GENIUS_ACCESS_TOKEN")
    if token:
        return token
    creds_file = _TOKEN_DIR / "genius.json"
    if creds_file.exists():
        data = json.loads(creds_file.read_text())
        return data.get("access_token")
    return None


def _request(path: str, params: dict | None = None) -> dict:
    """Make a Genius API request."""
    token = _load_access_token()
    if not token:
        raise ValueError("No Genius access token configured.")

    url = f"{_BASE_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "User-Agent": "tuneshift/1.0",
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def search_song(title: str, artist: str) -> str | None:
    """Search for a song and return its Genius URL (for lyrics scraping)."""
    try:
        data = _request("/search", {"q": f"{title} {artist}"})
        hits = data.get("response", {}).get("hits", [])
        if not hits:
            return None
        # Find best match by artist
        artist_lower = artist.lower()
        for hit in hits[:5]:
            result = hit.get("result", {})
            primary = result.get("primary_artist", {}).get("name", "")
            if artist_lower in primary.lower() or primary.lower() in artist_lower:
                return result.get("url")
        # Fallback: first result
        return hits[0].get("result", {}).get("url")
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def get_lyrics(title: str, artist: str) -> str | None:
    """Get lyrics for a track by searching Genius and scraping the page.

    Returns the full lyrics text."""
    url = search_song(title, artist)
    if not url:
        return None

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "tuneshift/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Extract lyrics from Genius HTML
        # Genius stores lyrics in <div data-lyrics-container="true"> elements
        containers = re.findall(
            r'<div[^>]*data-lyrics-container="true"[^>]*>(.*?)</div>',
            html, re.DOTALL,
        )
        if not containers:
            return None

        raw = " ".join(containers)
        # Strip HTML tags
        text = re.sub(r"<br\s*/?>", "\n", raw)
        text = re.sub(r"<[^>]+>", "", text)
        # Decode HTML entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&#x27;", "'").replace("&quot;", '"')
        text = text.strip()

        return text if text else None

    except (OSError, ValueError):
        return None


def is_available() -> bool:
    """Check if Genius access token is configured."""
    return _load_access_token() is not None
