"""Normalization primitives and version-keyword regexes.

This module holds the string-normalization functions (`normalize_title`,
`normalize_artist`, `is_remaster`) and every compiled regex used by the
matching layer: the edition/feat-stripping patterns consumed by normalization
and the version-keyword patterns (live/remix/karaoke/...) consumed by the
scorers in `track.py`. Keeping the patterns in one place prevents the
"four copies of edition knowledge" drift the overhaul is undoing.
"""
import re
import unicodedata

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
