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
    prefer_classes: tuple[str, ...] = field(default_factory=tuple)
    avoid_classes: tuple[str, ...] = field(default_factory=tuple)


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
        # --- Artist-name normalization (real typographic traps) ----------
        GoldCase(
            id="artist-degree-sign-98",
            source_title="The Hardest Thing",
            source_artist="98\u00b0",
            source_album="98\u00b0 and Rising",
            candidates=[
                Candidate("98deg-right", "The Hardest Thing", "98 Degrees",
                          "98 Degrees and Rising", 273),
                Candidate("98deg-wrong", "The Hardest Thing", "The Cardigans",
                          "Gran Turismo", 228),
            ],
            expected_platform_id="98deg-right",
            source_duration_seconds=273,
            note="The degree sign in '98\u00b0' must normalize to '98 Degrees' so the "
                 "typographic variant matches.",
            tags=("artist-normalization", "unicode-symbol"),
        ),
        GoldCase(
            id="artist-asterisk-bwitched",
            source_title="C'est la Vie",
            source_artist="B*Witched",
            source_album="B*Witched",
            candidates=[
                Candidate("bw-right", "C'est la Vie", "B Witched", "B Witched", 156),
                Candidate("bw-wrong", "C'est la Vie", "Robbie Nevil", "Uptown", 210),
            ],
            expected_platform_id="bw-right",
            source_duration_seconds=156,
            note="Asterisk in 'B*Witched' is a stylized space; must match 'B Witched'.",
            tags=("artist-normalization", "asterisk"),
        ),
        GoldCase(
            id="artist-leading-asterisk-nsync",
            source_title="Bye Bye Bye",
            source_artist="*NSYNC",
            source_album="No Strings Attached",
            candidates=[
                Candidate("nsync-right", "Bye Bye Bye", "NSYNC",
                          "No Strings Attached", 200),
                Candidate("nsync-wrong", "Bye Bye Bye", "The Sugarcubes", "Life's Too Good", 190),
            ],
            expected_platform_id="nsync-right",
            source_duration_seconds=200,
            note="Leading asterisk in '*NSYNC' must not prevent matching 'NSYNC'.",
            tags=("artist-normalization", "leading-asterisk"),
        ),
        # --- Featured artist in the title, not the artist field ----------
        GoldCase(
            id="feat-in-title-dirrty",
            source_title="Dirrty (feat. Redman)",
            source_artist="Christina Aguilera",
            source_album="Stripped",
            candidates=[
                Candidate("dirrty-right", "Dirrty", "Christina Aguilera", "Stripped", 238),
                Candidate("dirrty-wrong", "Dirrty (Remix)", "Christina Aguilera",
                          "Stripped Remixes", 300),
            ],
            expected_platform_id="dirrty-right",
            source_duration_seconds=238,
            note="A feat. credit in the title must not penalize the same recording that "
                 "omits it; never prefer a remix.",
            tags=("feat-in-title", "remix-trap"),
        ),
        # --- Title corruption / normalization ----------------------------
        GoldCase(
            id="title-parenthetical-album-corruption",
            source_title="Femininomenon (The Rise and Fall of a Midwest Princess)",
            source_artist="Chappell Roan",
            source_album="The Rise and Fall of a Midwest Princess",
            candidates=[
                Candidate("femin-right", "Femininomenon", "Chappell Roan",
                          "The Rise and Fall of a Midwest Princess", 202),
                Candidate("femin-wrong", "Pink Pony Club", "Chappell Roan",
                          "The Rise and Fall of a Midwest Princess", 258),
            ],
            expected_platform_id="femin-right",
            source_duration_seconds=202,
            note="The album name wrongly appended to the title in parentheses must be "
                 "stripped before matching (Lavender Menace corruption pattern).",
            tags=("title-corruption", "parenthetical-album"),
        ),
        GoldCase(
            id="title-leading-ellipsis",
            source_title="...Baby One More Time",
            source_artist="Britney Spears",
            source_album="...Baby One More Time",
            candidates=[
                Candidate("baby-right", "...Baby One More Time", "Britney Spears",
                          "...Baby One More Time", 211),
                Candidate("baby-wrong", "Baby One More Time (Karaoke)", "Karaoke Stars",
                          "Pop Hits Karaoke", 211),
            ],
            expected_platform_id="baby-right",
            source_duration_seconds=211,
            note="A leading ellipsis must not corrupt matching; never pick karaoke.",
            tags=("title-corruption", "punctuation-heavy", "karaoke-trap"),
        ),
        GoldCase(
            id="title-leading-paren-subtitle",
            source_title="(You Drive Me) Crazy",
            source_artist="Britney Spears",
            source_album="...Baby One More Time",
            candidates=[
                Candidate("crazy-right", "(You Drive Me) Crazy", "Britney Spears",
                          "...Baby One More Time", 197),
                Candidate("crazy-wrong", "Crazy", "Gnarls Barkley", "St. Elsewhere", 178),
            ],
            expected_platform_id="crazy-right",
            source_duration_seconds=197,
            note="A leading parenthetical that is a genuine subtitle (not the album) "
                 "must be preserved, not stripped down to 'Crazy'.",
            tags=("title-corruption", "subtitle-preserved"),
        ),
        # --- Per-playlist recording preference ---------------------------
        GoldCase(
            id="avoid-live-preference",
            source_title="Yesterday",
            source_artist="The Beatles",
            source_album="Help!",
            candidates=[
                Candidate("yesterday-studio", "Yesterday", "The Beatles", "Help!", 125),
                Candidate("yesterday-live", "Yesterday (Live)", "The Beatles",
                          "Live at the BBC", 130),
            ],
            expected_platform_id="yesterday-studio",
            source_duration_seconds=125,
            note="A playlist configured to avoid live takes must hard-reject the live "
                 "recording and keep the studio cut.",
            tags=("preference", "avoid-live"),
            avoid_classes=("live",),
        ),
        # --- Track available only under a different album ----------------
        GoldCase(
            id="track-under-different-album",
            source_title="Torn",
            source_artist="Natalie Imbruglia",
            source_album="Left of the Middle",
            candidates=[
                Candidate("torn-comp", "Torn", "Natalie Imbruglia",
                          "The Best of Natalie Imbruglia", 285),
                Candidate("torn-wrong", "Torn", "Ednaswap", "Wacko Magneto", 250),
            ],
            expected_platform_id="torn-comp",
            source_duration_seconds=282,
            note="When the requested album is absent on-platform but the correct "
                 "recording exists under a compilation, that recording is valid; must "
                 "not pick the different-artist original.",
            tags=("different-album", "compilation-valid", "wrong-artist-trap"),
        ),
        # --- Per-playlist EDITION preferences (radio/single, expanded) ----
        GoldCase(
            id="oops-avoid-radio-single",
            source_title="Oops!... I Did It Again",
            source_artist="Britney Spears",
            source_album="Oops!... I Did It Again",
            candidates=[
                Candidate("2931958", "Oops!... I Did It Again", "Britney Spears",
                          "Oops!... I Did It Again", 211),
                Candidate("oops-radio", "Oops!... I Did It Again (Radio Edit)",
                          "Britney Spears", "Now That's What I Call Music!", 197),
                Candidate("oops-single", "Oops!... I Did It Again (Single Version)",
                          "Britney Spears", "Oops!... I Did It Again (Single)", 200),
            ],
            expected_platform_id="2931958",
            source_duration_seconds=211,
            note="A playlist that avoids radio/single edits must keep the album "
                 "original, not a radio or single edit.",
            tags=("preference", "edition", "avoid-radio"),
            avoid_classes=("radio", "single"),
        ),
        GoldCase(
            id="come-on-over-prefer-expanded",
            source_title="Come On Over",
            source_artist="Shania Twain",
            source_album="Come On Over",
            candidates=[
                Candidate("cono-standard", "Come On Over", "Shania Twain",
                          "Come On Over", 175),
                Candidate("12270570", "Come On Over", "Shania Twain",
                          "Come On Over (Expanded Edition)", 175),
            ],
            expected_platform_id="12270570",
            source_duration_seconds=175,
            note="A playlist that prefers the expanded edition must elevate it over "
                 "the standard release even though both are the same recording.",
            tags=("preference", "edition", "prefer-expanded"),
            prefer_classes=("expanded",),
        ),
        GoldCase(
            id="playlist-prefer-radio-edit",
            source_title="Sabotage",
            source_artist="Beastie Boys",
            source_album="Ill Communication",
            candidates=[
                Candidate("sab-album", "Sabotage", "Beastie Boys",
                          "Ill Communication", 178),
                Candidate("sab-radio", "Sabotage (Radio Edit)", "Beastie Boys",
                          "Ill Communication", 165),
            ],
            expected_platform_id="sab-radio",
            source_duration_seconds=178,
            note="A radio-programming playlist can prefer the radio edit; the "
                 "preference must elevate it over the album cut.",
            tags=("preference", "edition", "prefer-radio"),
            prefer_classes=("radio",),
        ),
        # --- Christina Aguilera retitled single (Tidal 12270106) ----------
        GoldCase(
            id="christina-come-on-over-baby",
            source_title="Come On Over Baby (All I Wanna Do)",
            source_artist="Christina Aguilera",
            source_album="Christina Aguilera",
            candidates=[
                Candidate("12270106", "Come On Over Baby (All I Wanna Do)",
                          "Christina Aguilera", "Christina Aguilera", 224),
                Candidate("cono-shania", "Come On Over", "Shania Twain",
                          "Come On Over", 175),
                Candidate("cono-karaoke", "Come On Over Baby (All I Wanna Do) (Karaoke)",
                          "Karaoke Superstars", "Pop Karaoke Hits", 224),
            ],
            expected_platform_id="12270106",
            source_duration_seconds=224,
            note="Retitled single with a parenthetical must match the correct "
                 "Christina recording, never the Shania collision or the karaoke.",
            tags=("retitle", "parenthetical", "wrong-artist-trap", "karaoke-trap"),
        ),
    ]
