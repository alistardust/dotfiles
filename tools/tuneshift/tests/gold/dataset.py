"""Labeled gold set for the matching engine.

Each case pairs a source track with a pool of candidate results and the
correct outcome. Cases are seeded from real failures documented in
``track-metadata-and-mapping-gaps.md`` and the overhaul design (delisted Tribe
originals, live-intent Joni Mitchell, retitled Britney single, deluxe/
compilation editions, genuinely unavailable tracks) plus structural edge cases
(CJK title, explicit/clean pair, multi-disc, in-playlist duplicate).

The pools capture the *discriminating* metadata (title/artist/album/duration),
not a full catalogue, so the current scorer can be measured and later chunks
can be scored as deltas against the recorded baseline.
"""
from __future__ import annotations

from dataclasses import dataclass, field

UNAVAILABLE = None


@dataclass(frozen=True)
class Candidate:
    """A single search result in a case's candidate pool."""

    platform_id: str
    title: str
    artist: str
    album: str
    duration_seconds: int | None = None


@dataclass(frozen=True)
class GoldCase:
    """A labeled matching scenario.

    ``expected_platform_id`` is the id the engine should choose, or
    ``UNAVAILABLE`` (None) when the correct outcome is "no acceptable match".
    ``expected_version_class`` records the intended edition (studio/live/etc.)
    for intent-fidelity scoring in later chunks.
    """

    id: str
    source_title: str
    source_artist: str
    source_album: str | None
    candidates: list[Candidate]
    expected_platform_id: str | None
    expected_version_class: str = "studio"
    source_duration_seconds: int | None = None
    note: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


def gold_cases() -> list[GoldCase]:
    """Return the full labeled gold set."""
    return [
        # --- Delisted Tribe originals: the compilation/remix trap ---------
        GoldCase(
            id="tribe-can-i-kick-it",
            source_title="Can I Kick It?",
            source_artist="A Tribe Called Quest",
            source_album="People's Instinctive Travels and the Paths of Rhythm",
            candidates=[
                Candidate("tribe-cikit-anniv", "Can I Kick It?", "A Tribe Called Quest",
                          "People's Instinctive Travels and the Paths of Rhythm "
                          "(25th Anniversary Edition)", 251),
                Candidate("tribe-cikit-remix", "Can I Kick It? (Boilerhouse Mix)",
                          "A Tribe Called Quest", "The Anthology", 289),
                Candidate("tribe-buggin", "Buggin' Out", "A Tribe Called Quest",
                          "People's Instinctive Travels and the Paths of Rhythm "
                          "(25th Anniversary Edition)", 223),
            ],
            expected_platform_id="tribe-cikit-anniv",
            expected_version_class="studio",
            source_duration_seconds=252,
            note="Must pick the anniversary reissue of the same song, never Buggin' Out "
                 "and never the remix.",
            tags=("delisted", "compilation-trap", "wrong-track-trap"),
        ),
        GoldCase(
            id="tribe-bonita-applebum",
            source_title="Bonita Applebum",
            source_artist="A Tribe Called Quest",
            source_album="People's Instinctive Travels and the Paths of Rhythm",
            candidates=[
                Candidate("tribe-bonita-anniv", "Bonita Applebum", "A Tribe Called Quest",
                          "People's Instinctive Travels and the Paths of Rhythm "
                          "(25th Anniversary Edition)", 233),
                Candidate("tribe-bonita-hootie", "Bonita Applebum (Hootie Mix)",
                          "A Tribe Called Quest", "The Anthology", 268),
            ],
            expected_platform_id="tribe-bonita-anniv",
            expected_version_class="studio",
            source_duration_seconds=232,
            note="Reissue original over the Hootie remix.",
            tags=("delisted", "compilation-trap"),
        ),
        # --- Live-intent: Joni Mitchell at Newport -----------------------
        GoldCase(
            id="joni-big-yellow-taxi-live",
            source_title="Big Yellow Taxi (feat. Lucius)",
            source_artist="Joni Mitchell",
            source_album="Joni Mitchell at Newport (Live)",
            candidates=[
                Candidate("307298999-live", "Big Yellow Taxi (feat. Lucius)",
                          "Joni Mitchell", "Joni Mitchell at Newport (Live)", 234),
                Candidate("joni-byt-studio", "Big Yellow Taxi", "Joni Mitchell",
                          "Ladies of the Canyon", 135),
            ],
            expected_platform_id="307298999-live",
            expected_version_class="live",
            source_duration_seconds=236,
            note="Source intent is the live Newport recording; do not collapse to the "
                 "studio original.",
            tags=("live-intent", "featuring"),
        ),
        # --- Retitled single: Britney "Crazy" -> "(You Drive Me) Crazy" ---
        GoldCase(
            id="britney-crazy-retitled",
            source_title="Crazy",
            source_artist="Britney Spears",
            source_album="...Baby One More Time",
            candidates=[
                Candidate("1631746", "(You Drive Me) Crazy", "Britney Spears",
                          "...Baby One More Time", 198),
                Candidate("britney-crazy-cover", "Crazy", "Kidz Bop Kids",
                          "Kidz Bop 2", 195),
            ],
            expected_platform_id="1631746",
            expected_version_class="studio",
            source_duration_seconds=197,
            note="Retitled official single beats a same-title cover.",
            tags=("retitled", "cover-trap"),
        ),
        # --- Deluxe edition acceptable: Arlo Parks "Hope" ----------------
        GoldCase(
            id="arlo-parks-hope-deluxe",
            source_title="Hope",
            source_artist="Arlo Parks",
            source_album="Collapsed In Sunbeams",
            candidates=[
                Candidate("159990883", "Hope", "Arlo Parks",
                          "Collapsed In Sunbeams (Deluxe)", 178),
                Candidate("arlo-hope-live", "Hope (Live)", "Arlo Parks",
                          "Live at Union Chapel", 205),
            ],
            expected_platform_id="159990883",
            expected_version_class="studio",
            source_duration_seconds=178,
            note="Deluxe reissue of the studio track is an acceptable match; live is not.",
            tags=("deluxe", "edition"),
        ),
        # --- Compilation-only availability: LeAnn Rimes ------------------
        GoldCase(
            id="leann-how-do-i-live-compilation",
            source_title="How Do I Live",
            source_artist="LeAnn Rimes",
            source_album="You Light Up My Life: Inspirational Songs",
            candidates=[
                Candidate("45159417", "How Do I Live", "LeAnn Rimes",
                          "All-Time Greatest Hits", 262),
                Candidate("leann-hdil-trisha", "How Do I Live", "Trisha Yearwood",
                          "Songbook", 289),
            ],
            expected_platform_id="45159417",
            expected_version_class="studio",
            source_duration_seconds=260,
            note="Only a compilation carries the LeAnn recording; must not pick the "
                 "Trisha Yearwood version.",
            tags=("compilation-only", "wrong-artist-trap"),
        ),
        # --- Genuinely unavailable ---------------------------------------
        GoldCase(
            id="tinashe-supernova-unavailable",
            source_title="Supernova",
            source_artist="Tinashe",
            source_album="Nightride",
            candidates=[
                Candidate("nova-ansel", "Supernova", "Ansel Elgort", "Supernova", 210),
                Candidate("nova-brand", "Supernova", "Brand New Sin", "Recipe for Disaster", 240),
            ],
            expected_platform_id=UNAVAILABLE,
            expected_version_class="studio",
            source_duration_seconds=200,
            note="No Tinashe release exists on platform; same-title different-artist "
                 "results must NOT be selected.",
            tags=("unavailable", "wrong-artist-trap"),
        ),
        GoldCase(
            id="jauregui-need-you-tonight-unavailable",
            source_title="Need You Tonight",
            source_artist="Lauren Jauregui",
            source_album="Prelude",
            candidates=[
                Candidate("nyt-inxs", "Need You Tonight", "INXS", "Kick", 181),
                Candidate("nyt-bsb", "Need You Tonight", "Backstreet Boys",
                          "Backstreet Boys", 224),
            ],
            expected_platform_id=UNAVAILABLE,
            expected_version_class="studio",
            source_duration_seconds=200,
            note="No solo Lauren Jauregui release; INXS/BSB same-title must not match.",
            tags=("unavailable", "wrong-artist-trap"),
        ),
        # --- CJK title normalization -------------------------------------
        GoldCase(
            id="cjk-title",
            source_title="夜に駆ける",
            source_artist="YOASOBI",
            source_album="THE BOOK",
            candidates=[
                Candidate("yoasobi-yoruni", "夜に駆ける", "YOASOBI", "THE BOOK", 261),
                Candidate("yoasobi-cover", "夜に駆ける (Cover)", "Various Artists",
                          "J-Pop Covers", 250),
            ],
            expected_platform_id="yoasobi-yoruni",
            expected_version_class="studio",
            source_duration_seconds=262,
            note="Non-Latin script must normalize and match; reject the cover.",
            tags=("i18n", "cjk", "cover-trap"),
        ),
        # --- Explicit source should not match a clean edition ------------
        GoldCase(
            id="explicit-source-prefers-explicit",
            source_title="HUMBLE.",
            source_artist="Kendrick Lamar",
            source_album="DAMN.",
            candidates=[
                Candidate("humble-explicit", "HUMBLE.", "Kendrick Lamar", "DAMN.", 177),
                Candidate("humble-clean", "HUMBLE. (Clean)", "Kendrick Lamar",
                          "DAMN. (Clean)", 177),
            ],
            expected_platform_id="humble-explicit",
            expected_version_class="explicit",
            source_duration_seconds=177,
            note="Explicit source should resolve to the explicit master, not the clean edit.",
            tags=("explicit", "clean-trap"),
        ),
        # --- Multi-disc album track --------------------------------------
        GoldCase(
            id="multi-disc-track",
            source_title="Another Brick in the Wall, Pt. 2",
            source_artist="Pink Floyd",
            source_album="The Wall",
            candidates=[
                Candidate("wall-pt3", "Another Brick in the Wall, Pt. 3",
                          "Pink Floyd", "The Wall", 78),
                Candidate("wall-pt2", "Another Brick in the Wall, Pt. 2",
                          "Pink Floyd", "The Wall", 239),
            ],
            expected_platform_id="wall-pt2",
            expected_version_class="studio",
            source_duration_seconds=239,
            note="Multi-disc set: Pt. 2 must not collapse to Pt. 3 (title near-duplicate).",
            tags=("multi-disc", "part-number"),
        ),
        # --- In-playlist duplicate distinguished by duration -------------
        GoldCase(
            id="in-playlist-duplicate-radio-vs-album",
            source_title="Marquee Moon",
            source_artist="Television",
            source_album="Marquee Moon",
            candidates=[
                Candidate("marquee-radio", "Marquee Moon (Single Edit)", "Television",
                          "Marquee Moon", 189),
                Candidate("marquee-album", "Marquee Moon", "Television",
                          "Marquee Moon", 583),
            ],
            expected_platform_id="marquee-album",
            expected_version_class="studio",
            source_duration_seconds=583,
            note="Long album version distinguished from the single edit by duration.",
            tags=("duplicate", "duration-discriminator"),
        ),
        # --- Karaoke / "in the style of" trap ----------------------------
        GoldCase(
            id="karaoke-made-famous-by",
            source_title="Rolling in the Deep",
            source_artist="Adele",
            source_album="21",
            candidates=[
                Candidate("adele-ritd", "Rolling in the Deep", "Adele", "21", 228),
                Candidate("ritd-karaoke", "Rolling in the Deep (Karaoke Version)",
                          "Karaoke Universe", "Karaoke Hits", 231),
                Candidate("ritd-madefamous", "Rolling in the Deep "
                          "(Made Famous by Adele)", "The Karaoke Crew",
                          "Pop Karaoke Vol. 3", 226),
            ],
            expected_platform_id="adele-ritd",
            expected_version_class="studio",
            source_duration_seconds=228,
            note="Must pick the real Adele master, never a karaoke / "
                 "'made famous by' impostor.",
            tags=("karaoke", "tribute-trap", "wrong-artist-trap"),
        ),
        # --- Sped-up / TikTok edit trap ----------------------------------
        GoldCase(
            id="sped-up-edit-trap",
            source_title="Cornelia Street",
            source_artist="Taylor Swift",
            source_album="Lover",
            candidates=[
                Candidate("cornelia-orig", "Cornelia Street", "Taylor Swift",
                          "Lover", 288),
                Candidate("cornelia-sped", "Cornelia Street (Sped Up)",
                          "Taylor Swift", "Cornelia Street (Sped Up)", 233),
            ],
            expected_platform_id="cornelia-orig",
            expected_version_class="studio",
            source_duration_seconds=288,
            note="Original album cut, not the sped-up edit, when the source is the "
                 "studio version.",
            tags=("sped-up", "edit-trap"),
        ),
        # --- Instrumental trap -------------------------------------------
        GoldCase(
            id="instrumental-trap",
            source_title="Clocks",
            source_artist="Coldplay",
            source_album="A Rush of Blood to the Head",
            candidates=[
                Candidate("clocks-orig", "Clocks", "Coldplay",
                          "A Rush of Blood to the Head", 307),
                Candidate("clocks-instr", "Clocks (Instrumental)",
                          "Piano Tribute Players", "Instrumental Tributes", 300),
            ],
            expected_platform_id="clocks-orig",
            expected_version_class="studio",
            source_duration_seconds=307,
            note="Vocal source must not resolve to an instrumental cover.",
            tags=("instrumental", "tribute-trap"),
        ),
        # --- Remix present but original available ------------------------
        GoldCase(
            id="remix-when-original-available",
            source_title="Sorry",
            source_artist="Justin Bieber",
            source_album="Purpose",
            candidates=[
                Candidate("sorry-orig", "Sorry", "Justin Bieber", "Purpose", 200),
                Candidate("sorry-latino", "Sorry (Latino Remix)", "Justin Bieber",
                          "Sorry (Remixes)", 194),
                Candidate("sorry-vs", "Sorry (BOXINLION Remix)", "Justin Bieber",
                          "Sorry (Remixes)", 215),
            ],
            expected_platform_id="sorry-orig",
            expected_version_class="studio",
            source_duration_seconds=200,
            note="Original beats any remix when the source is the studio version.",
            tags=("remix", "edit-trap"),
        ),
        # --- Remaster of the same recording is acceptable ----------------
        GoldCase(
            id="remaster-acceptable",
            source_title="Bohemian Rhapsody",
            source_artist="Queen",
            source_album="A Night at the Opera",
            candidates=[
                Candidate("bohemian-remaster", "Bohemian Rhapsody (2011 Remaster)",
                          "Queen", "A Night at the Opera (2011 Remaster)", 355),
                Candidate("bohemian-live", "Bohemian Rhapsody (Live at Wembley '86)",
                          "Queen", "Live at Wembley '86", 358),
            ],
            expected_platform_id="bohemian-remaster",
            expected_version_class="studio",
            source_duration_seconds=354,
            note="A remaster of the same studio recording is an acceptable match; "
                 "the live version is not.",
            tags=("remaster", "edition", "live-trap"),
        ),
        # --- feat. credit variant is the same recording ------------------
        GoldCase(
            id="feat-credit-same-recording",
            source_title="Uptown Funk",
            source_artist="Mark Ronson",
            source_album="Uptown Special",
            candidates=[
                Candidate("uptown-feat", "Uptown Funk (feat. Bruno Mars)",
                          "Mark Ronson", "Uptown Special", 270),
                Candidate("uptown-cover", "Uptown Funk", "The Cover Kings",
                          "Party Hits 2015", 268),
            ],
            expected_platform_id="uptown-feat",
            expected_version_class="studio",
            source_duration_seconds=270,
            note="A '(feat. X)' credit on the same recording is the correct match "
                 "over a same-title cover.",
            tags=("feat-credit", "cover-trap"),
        ),
        # --- Live-intent source must pick the live recording -------------
        GoldCase(
            id="live-intent-prefers-live",
            source_title="Hurt (Live)",
            source_artist="Johnny Cash",
            source_album="Unearthed",
            candidates=[
                Candidate("hurt-studio", "Hurt", "Johnny Cash",
                          "American IV: The Man Comes Around", 218),
                Candidate("hurt-live", "Hurt (Live)", "Johnny Cash", "Unearthed", 232),
            ],
            expected_platform_id="hurt-live",
            expected_version_class="live",
            source_duration_seconds=232,
            note="When the source is explicitly a live take, the live recording is "
                 "the intended match, not the studio cut.",
            tags=("live", "intent-fidelity"),
        ),
    ]
