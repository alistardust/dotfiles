"""Track matching: normalization and scoring logic."""
import re
import unicodedata
from difflib import SequenceMatcher

_EDITION_PARENS_RE = re.compile(
    r"\s*\("
    r"(?:\d{4}\s*)?"
    r"(?:Remastered|Remaster|Deluxe Edition|Deluxe|Mono|Stereo|Expanded Edition|Expanded)"
    r"[^)]*\)",
    re.IGNORECASE,
)
_THE_PREFIX_RE = re.compile(r"^the\s+", re.IGNORECASE)


def normalize_title(title: str) -> str:
    """Normalize a track/album title for comparison."""
    title = unicodedata.normalize("NFC", title)
    title = _EDITION_PARENS_RE.sub("", title)
    title = title.strip().casefold()
    return title


def normalize_artist(artist: str) -> str:
    """Normalize an artist name for comparison."""
    artist = unicodedata.normalize("NFC", artist)
    artist = artist.strip()
    artist = _THE_PREFIX_RE.sub("", artist)
    artist = artist.replace("&", "and")
    return artist.casefold()


def is_remaster(album: str) -> bool:
    """Check if an album name indicates a remaster."""
    return "remaster" in album.casefold()


def score_match(
    source_title: str,
    source_artist: str,
    source_album: str | None,
    result_title: str,
    result_artist: str,
    result_album: str,
) -> int:
    """Score a Tidal result against source metadata. Returns 0-100."""
    score = 0

    norm_src_title = normalize_title(source_title)
    norm_res_title = normalize_title(result_title)
    if norm_src_title and norm_res_title:
        if norm_src_title == norm_res_title:
            score += 50
        else:
            ratio = SequenceMatcher(None, norm_src_title, norm_res_title).ratio()
            if ratio > 0.85:
                score += 30
            elif ratio >= 0.70:
                score += 15

    norm_src_artist = normalize_artist(source_artist)
    norm_res_artist = normalize_artist(result_artist)
    if norm_src_artist and norm_res_artist:
        if norm_src_artist == norm_res_artist:
            score += 30
        else:
            ratio = SequenceMatcher(None, norm_src_artist, norm_res_artist).ratio()
            if ratio > 0.80:
                score += 20

    if source_album:
        norm_src_album = normalize_title(source_album)
        norm_res_album = normalize_title(result_album)
        if norm_src_album == norm_res_album:
            score += 20
        elif norm_src_album and norm_res_album:
            ratio = SequenceMatcher(None, norm_src_album, norm_res_album).ratio()
            if ratio >= 0.75:
                score += 10

    return score


def classify_results(scores: list[int]) -> str:
    """Classify match confidence. Returns 'high', 'ambiguous', or 'not_found'."""
    if not scores:
        return "not_found"
    top = max(scores)
    if top < 50:
        return "not_found"
    sorted_desc = sorted(scores, reverse=True)
    second = sorted_desc[1] if len(sorted_desc) > 1 else 0
    if top >= 80 and second < 70:
        return "high"
    return "ambiguous"
