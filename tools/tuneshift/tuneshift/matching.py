"""Track matching: normalization, scoring, and classification."""
import re
import unicodedata
from difflib import SequenceMatcher

_EDITION_PARENS_RE = re.compile(
    r"\s*\("
    r"(?:\d{4}\s*)?"
    r"(?:Remastered|Remaster|Deluxe Edition|Deluxe Version|Deluxe|"
    r"Digital Deluxe|Mono|Stereo|"
    r"Expanded Edition|Expanded|Anniversary Edition|Anniversary|"
    r"Super Deluxe|Special Edition|"
    r"\d{4}\s+(?:Re)?[Mm]ix|Stereo Mix|Mono Mix|"
    r"Taylor's Version)[^)]*\)",
    re.IGNORECASE,
)
_THE_PREFIX_RE = re.compile(r"^the\s+", re.IGNORECASE)
_FEAT_PAREN_RE = re.compile(
    r"\s*[\(\[]\s*(?:feat\.?|ft\.?|featuring|with)\s+[^\)\]]+[\)\]]",
    re.IGNORECASE,
)
_FEAT_BARE_RE = re.compile(
    r"\s+(?:feat\.?|ft\.?|featuring)\s+.+$",
    re.IGNORECASE,
)
_PUNCT_NORMALIZE = str.maketrans({
    "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"',
    "\u2026": "...",
})
_BOUNDARY_PUNCT_RE = re.compile(r"(?:^[^\w]+|[^\w]+$)")  # Leading/trailing non-word chars
_STANDALONE_PUNCT_RE = re.compile(r"\s+[^\w\s]+\s+")  # Standalone punctuation between words


def normalize_title(title: str) -> str:
    """Normalize a track/album title for comparison."""
    if not title:
        return ""
    title = unicodedata.normalize("NFC", title)
    title = title.translate(_PUNCT_NORMALIZE)
    title = _EDITION_PARENS_RE.sub("", title)
    title = _FEAT_PAREN_RE.sub("", title)
    title = _FEAT_BARE_RE.sub("", title)
    return title.strip().casefold()


def normalize_artist(artist: str) -> str:
    """Normalize an artist name for comparison.

    Strips feat text, punctuation, articles, and casefolds so that
    legitimate variants (P!nk/Pink, feat. suffix) become identical.
    """
    if not artist:
        return ""
    artist = unicodedata.normalize("NFC", artist)
    artist = artist.translate(_PUNCT_NORMALIZE)
    artist = _FEAT_PAREN_RE.sub("", artist)
    artist = _FEAT_BARE_RE.sub("", artist)
    artist = artist.strip()
    artist = _THE_PREFIX_RE.sub("", artist)
    artist = artist.replace("&", "and")
    artist = artist.replace(",", "")
    # Strip boundary punctuation but preserve mid-word chars (P!nk stays as p!nk)
    artist = _BOUNDARY_PUNCT_RE.sub("", artist)
    artist = _STANDALONE_PUNCT_RE.sub(" ", artist)
    return artist.casefold().strip()


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
            if ratio > 0.85:
                score += 25
            elif ratio > 0.70:
                score += 15
            elif ratio > 0.50:
                # Ambiguous zone: moderate penalty (probably different artist)
                score -= 15
            else:
                # Different artist: heavy penalty proportional to dissimilarity
                score -= int(30 * (1.0 - ratio * 2))

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


_LIVE_RE = re.compile(
    r"\b(live|concert|in concert|unplugged|mtv unplugged|"
    r"here and there|one night only|at the|at madison|"
    r"17-11-70|11-17-70)\b",
    re.IGNORECASE,
)
_REMIX_RE = re.compile(
    r"\b(remix|remixed|performance mix|extended mix|"
    r"extended version|dub mix|club mix|12[\"'] mix|"
    r"12 inch|maxi)\b",
    re.IGNORECASE,
)
_REMASTER_RE = re.compile(
    r"\b(remaster(?:ed)?)\b", re.IGNORECASE
)
_DELUXE_RE = re.compile(
    r"\b(deluxe|expanded|anniversary|special edition|bonus track|"
    r"celebration)\b",
    re.IGNORECASE,
)
_COMPILATION_RE = re.compile(
    r"\b(greatest hits|best of|essentials|collection|anthology|"
    r"now that's what|various artists|soundtrack|love songs|"
    r"to be continued|diamonds|the definitive|rocket man:\s|"
    r"the very best)\b",
    re.IGNORECASE,
)
_TRIBUTE_RE = re.compile(
    r"\b(tribute|reimagin|covers?|revamp)\b", re.IGNORECASE
)
_KARAOKE_RE = re.compile(
    r"\b(karaoke)\b", re.IGNORECASE
)
_INSTRUMENTAL_RE = re.compile(
    r"\b(instrumental)\b", re.IGNORECASE
)
_ACOUSTIC_RE = re.compile(
    r"\b(acoustic|stripped)\b", re.IGNORECASE
)
_RADIO_EDIT_RE = re.compile(
    r"\b(radio edit|radio version|single edit|single version)\b",
    re.IGNORECASE,
)


def version_penalty(title: str, album: str) -> int:
    """Return a penalty for undesirable track versions.

    Penalties (cumulative):
    - Karaoke: 50 (always rejected)
    - Instrumental: 50 (always rejected)
    - Live: 20
    - Remix: 20
    - Tribute/cover: 20
    - Radio edit: 20
    - Compilation: 15
    - Acoustic/stripped: 10
    - Remaster: 10
    - Deluxe edition: 5
    """
    combined = f"{title} {album}"
    penalty = 0

    if _KARAOKE_RE.search(combined):
        penalty += 50
    if _INSTRUMENTAL_RE.search(combined):
        penalty += 50
    if _LIVE_RE.search(combined):
        penalty += 20
    if _REMIX_RE.search(combined):
        penalty += 20
    if _TRIBUTE_RE.search(combined):
        penalty += 20
    if _RADIO_EDIT_RE.search(combined):
        penalty += 20
    if _COMPILATION_RE.search(combined):
        penalty += 15
    if _ACOUSTIC_RE.search(combined):
        penalty += 10
    if _REMASTER_RE.search(combined):
        penalty += 10
    if _DELUXE_RE.search(combined):
        penalty += 5

    return penalty


def duration_penalty(
    candidate_duration: int | None,
    reference_duration: int | None = None,
    all_durations: list[int] | None = None,
) -> int:
    """Penalize tracks significantly longer OR shorter than expected.

    Returns 0-20 penalty.
    """
    if candidate_duration is None:
        return 0

    if reference_duration is None and all_durations:
        valid = [d for d in all_durations if d and d > 60]
        if valid:
            reference_duration = min(valid)

    if reference_duration is None or reference_duration < 60:
        return 0

    ratio = candidate_duration / reference_duration

    # Too long
    if ratio > 2.0:
        return 20
    if ratio > 1.6:
        return 15
    if ratio > 1.4:
        return 10

    # Too short
    if ratio < 0.5:
        return 20
    if ratio < 0.65:
        return 15
    if ratio < 0.75:
        return 10

    return 0


def duration_proximity_bonus(
    candidate_duration: int | None,
    canonical_duration: int | None,
) -> int:
    """Bonus 0-10 for duration proximity to canonical track.

    Rewards candidates whose duration closely matches what we expect.
    """
    if not candidate_duration or not canonical_duration:
        return 0
    if canonical_duration < 30:
        return 0
    diff_pct = abs(candidate_duration - canonical_duration) / canonical_duration
    if diff_pct < 0.05:
        return 10
    if diff_pct < 0.15:
        return 5
    return 0


def score_match_with_version(
    source_title: str,
    source_artist: str,
    source_album: str | None,
    result_title: str,
    result_artist: str,
    result_album: str,
    result_duration: int | None = None,
    reference_duration: int | None = None,
    all_durations: list[int] | None = None,
) -> int:
    """Score a search result with version preference applied.

    Combines similarity scoring from score_match with a penalty for
    undesirable versions (live, remix, compilation, etc.) and a duration
    penalty for extended mixes.
    """
    base = score_match(
        source_title, source_artist, source_album,
        result_title, result_artist, result_album,
    )
    penalty = version_penalty(result_title, result_album)
    dur_pen = duration_penalty(result_duration, reference_duration, all_durations)
    return max(0, min(100, base - penalty - dur_pen))


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
