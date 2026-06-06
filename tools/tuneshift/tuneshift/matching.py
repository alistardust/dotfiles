"""Track matching: normalization, scoring, and classification."""
import re
import unicodedata
from difflib import SequenceMatcher

_EDITION_PARENS_RE = re.compile(
    r"\s*\("
    r"(?:\d{4}\s*)?"
    r"(?:Remastered|Remaster|Deluxe Edition|Deluxe|Mono|Stereo|"
    r"Expanded Edition|Expanded|Anniversary Edition|Anniversary|"
    r"Super Deluxe|Special Edition)[^)]*\)",
    re.IGNORECASE,
)
_THE_PREFIX_RE = re.compile(r"^the\s+", re.IGNORECASE)


def normalize_title(title: str) -> str:
    """Normalize a track/album title for comparison."""
    if not title:
        return ""
    title = unicodedata.normalize("NFC", title)
    title = _EDITION_PARENS_RE.sub("", title)
    return title.strip().casefold()


def normalize_artist(artist: str) -> str:
    """Normalize an artist name for comparison."""
    if not artist:
        return ""
    artist = unicodedata.normalize("NFC", artist)
    artist = artist.strip()
    artist = _THE_PREFIX_RE.sub("", artist)
    artist = artist.replace("&", "and")
    return artist.casefold()


def is_remaster(album: str) -> bool:
    """Check if an album name indicates a remaster."""
    if not album:
        return False
    return "remaster" in album.casefold()


def score_match(
    source_title: str | object,
    source_artist: str | object,
    source_album: str | None = None,
    result_title: str | None = None,
    result_artist: str | None = None,
    result_album: str | None = None,
) -> int:
    """Score a search result against source metadata. Returns 0-100."""
    canonical = None
    candidate = None
    if result_title is None and result_artist is None and result_album is None:
        canonical = source_title
        candidate = source_artist
        if not all(hasattr(obj, attr) for obj, attr in (
            (canonical, "title"),
            (canonical, "artist"),
            (candidate, "title"),
            (candidate, "artist"),
            (candidate, "album"),
        )):
            raise TypeError("score_match requires either 6 fields or track-like objects")
        source_title = canonical.title
        source_artist = canonical.artist
        source_album = canonical.album
        result_title = candidate.title
        result_artist = candidate.artist
        result_album = candidate.album

    if result_title is None or result_artist is None or result_album is None:
        raise TypeError("score_match requires complete candidate metadata")

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

    if canonical is not None and candidate is not None:
        canonical_isrc = getattr(canonical, "isrc", None)
        candidate_isrc = getattr(candidate, "isrc", None)
        if canonical_isrc and candidate_isrc and canonical_isrc.upper() == candidate_isrc.upper():
            score = min(100, score + 15)

    return min(100, score)


def classify_results(scores: list[int]) -> str:
    """Classify match confidence.

    Returns 'high', 'ambiguous', or 'not_found'.
    High: top >= 80 AND second-best < 70 (clear gap).
    Ambiguous: top >= 50 but no clear gap.
    Not found: top < 50 or no results.
    """
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
