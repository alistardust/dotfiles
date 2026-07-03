# Matching — Known Limits

The matching engine is built to be best-in-class: high recall, correct
version by default, order-independent, and durable. This document is the
honest register of what it deliberately does **not** attempt to solve
automatically, and how each limit surfaces to the user. Each entry states the
limit, why it exists, and the observable behaviour — so a "we can't be sure
here" is always a visible review item, never a silent wrong guess.

## 1. Classical / long-form disambiguation

**Limit.** Works are not disambiguated by movement, conductor, orchestra,
soloist, cadenza, or recording session. "Symphony No. 5 in C minor, Op. 67:
I. Allegro con brio" under two different conductors is treated as the same
piece by title/artist similarity.

**Why.** Reliable classical disambiguation needs a structured work/recording
graph (composer → work → movement → performance) that the consumer streaming
APIs do not expose consistently. Guessing between performances would produce
confident wrong matches — exactly the failure mode this engine exists to
avoid.

**Behaviour.** When multiple credible performances exist, the candidates land
in the **ambiguous** availability state and are surfaced for review (`triage`),
never auto-resolved. Recall is preserved (a playable version is found); the
user picks and can lock it.

## 2. No acoustic fingerprinting

**Limit.** Matching is metadata-only (title, artist, album, duration, ISRC,
platform availability signals). There is no audio fingerprint (Chromaprint /
AcoustID-style) comparison.

**Why.** Fingerprinting requires the audio bytes, an external service, and a
fundamentally different pipeline. It is out of scope for a metadata
reconciliation tool and would add a heavy dependency for marginal gain on the
mainstream catalogue this tool targets.

**Behaviour.** Where metadata is genuinely ambiguous and only audio could
break the tie, the match degrades to **ambiguous** and is surfaced for review
rather than guessed.

## 3. Re-records ("Taylor's Version" and friends) are surfaced, not auto-resolved

**Limit.** Artist re-recordings (e.g. "(Taylor's Version)") are a distinct
master, not a remaster of the original. The engine does not silently swap a
re-record for the original or vice versa.

**Why.** Which master the user wants is a genuine preference, not a defect:
some listeners want the re-record, some the original. Auto-resolving either
way is a wrong guess for half of users. This is a **control** decision, not a
recall one.

**Behaviour.** Both the original and the re-record are legitimate results.
When the requested master is not the obvious best available, the alternative
is surfaced for review, and the user can express a durable preference
(`version.prefer` / `version.avoid`) and lock the chosen master so re-syncs
never overwrite it.

## 4. Multi-disc / disc-and-track ordering

**Limit.** The engine does not reconstruct disc numbers or intra-disc track
positions from platform metadata.

**Why.** None of the target platforms (Tidal, Spotify, YouTube Music) emit
reliable disc/track-number fields through their search and playlist APIs.
Building disc-aware ordering on top of data that is never returned would be
inert scaffolding that could not be exercised or trusted.

**Behaviour.** Playlist order is preserved exactly as authored (deliberate
order and intentional duplicates are retained through matching, repair, and
re-sync). Album-internal disc/track ordering is simply not a dimension the
engine claims to reconstruct.

## 5. Platforms that cannot express `exact_unavailable`

**Limit.** The availability verdict depends on the signal a platform exposes.
Tidal (`allowStreaming`) and Spotify (`is_playable` / `available_markets`)
expose a per-track availability signal, so a found-but-blocked track can be
classified `exact_unavailable`. YouTube Music does **not** expose a
pre-add availability signal — unavailability is only discovered at add time
(e.g. a 404 for a removed video).

**Why.** The engine only classifies what the platform actually tells it.
`TrackResult.available = None` means "unknown", never "blocked" — inventing a
blocked verdict from silence would be a confident wrong guess.

**Behaviour.** On a platform without an availability signal, a track that
cannot be confidently matched degrades to **ambiguous** (or **not_found** only
when trusted lookups all miss), and is surfaced for review rather than falsely
reported as unavailable. Availability-driven sequencing uses **Tidal as the
source of truth**; tracks Tidal reports as unavailable are excluded from the
arc and appended at the end (never dropped).

---

## 6. Descriptive-subtitle retitles vs. genuinely different songs

**Limit.** Some tracks are the *same recording* released under a different
trailing descriptive subtitle across regions or editions — e.g. Christina
Aguilera's "Come On Over Baby **(All I Wanna Do)**" vs. the retail title
"Come On Over Baby **(All I Want Is You)**". A naive title comparison scores
these as divergent and can drop a correct match below the auto threshold.

**Why.** Title *similarity* answers "same song?" while the source-aware version
axis answers "same version?". Trailing descriptive subtitles are neither a
version marker nor part of the base song name, so they must not dominate the
"same song?" judgement.

**Behaviour.** The version-aware scorers compute a **blended title similarity**:
the version-stripped titles are scored as-is, then again on their *base titles*
(trailing descriptive subtitles removed via `base_title`), and the stronger of
the two is kept minus a small residual penalty. This rescues true retitles while
keeping a gap below an identical-title match, so two genuinely different songs
that merely share a base title (e.g. "Untitled (How Does It Feel)" vs. "Untitled
(Rise)") are **not** merged — album, artist, duration and ISRC remain the
tiebreakers. Only *trailing* parentheticals are collapsed; integral leading
parentheticals ("(You Drive Me) Crazy") are preserved.

**Related — tempo-altered edits.** "Sped up", "slowed"/"slowed down" and
"nightcore" edits are a distinct recording class (`RecordingClass.ALTERED`), not
a descriptive subtitle. A studio source therefore **rejects** a tempo-altered
candidate (it is a different recording), and the marker is handled on the version
axis rather than being collapsed into the base title.

---

## How limits surface (summary)

| Situation | Availability verdict | User sees |
| --- | --- | --- |
| Genuinely ambiguous best match | `ambiguous` | Review item (`triage`); can lock |
| Found but platform reports blocked | `exact_unavailable` | Excluded from arc, appended at end |
| Trusted lookups all miss | `not_found` | Review item; never a silent drop |
| Re-record vs original | (both valid) | Surfaced; preference + lock available |

The guiding rule: **a "we can't be sure" is always a visible review item,
never a silent wrong guess.**
