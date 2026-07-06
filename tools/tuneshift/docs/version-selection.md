# Version-Selection Engine

TuneShift does not just find *a* version of a track; it selects the **right**
version (studio vs. live vs. remaster vs. Atmos vs. radio edit ...) and refuses to
guess when it cannot be sure. This document describes how selection works, the
criteria axes it evaluates, and how ambiguity surfaces for review.

The engine lives in `tuneshift/matching/`.

## Two-phase selection

`select_version()` runs in two phases (`matching/selection.py`):

1. **Phase 1, hard filter.** Candidates are eliminated if they are:
   - unavailable (`available is False`) or tier-restricted, or
   - failing any active *hard* preference (`require`/`forbid`), i.e. the
     criterion returns `HARD_REJECT`.

   The output is a set of `survivors` and a record of what was `filtered` (with
   reasons, so a rejection is always explainable).

2. **Phase 2, score survivors.** Surviving candidates are scored into `Distance`
   objects (`matching/base_scoring.py::score_signals`). *Soft* preferences
   (`prefer`/`avoid`) are **not** folded into the raw distance; they are recorded
   as separate verdict maps and resolved lexicographically by precedence
   (`matching/precedence.py`). Candidates are then ranked by distance, with tie
   and ambiguity handling on top.

If an **identity lock** is supplied, selection short-circuits before Phase 1; see
[Identity locks](locks.md).

### When Phase 1 rejects everything

If the hard filter eliminates every candidate, the outcome depends on *why*
(`matching/selection.py`):

- **All candidates hard-rejected** (e.g. a `forbid` matched, or none were
  available): selection returns `winner=None` with an empty ranked list and
  `needs_review=False`. The reconcile layer records this as `not_found`; the track
  is surfaced (never silently mapped to a wrong version) and excluded from the
  playlist until resolved.
- **Only version-mismatched candidates survive** (all were hard-capped by the
  source-aware verdict rather than dropped): one is chosen provisionally with
  `needs_review="version_mismatch"`, so a playable-but-imperfect result is offered
  for review instead of discarded.

Either way, an empty or degraded survivor set becomes a visible review item, not a
silent no-op.


## Criteria axes

Axes are registered in `matching/registry.py`. `KNOWN_AXES` is the union of the
sets below: 15 axes in total.

### Structured (metadata-derived)

| Axis | Evaluates | Source field |
|------|-----------|--------------|
| `spatial` | Spatial audio (e.g. Dolby Atmos) | `audio_modes` |
| `mix` | Mix/channel mode | `audio_modes` |
| `fidelity` | Audio quality tier (e.g. hi-res/lossless) | `media_metadata_tags` |

### Title-derived

| Axis | Evaluates |
|------|-----------|
| `performance` | Live / acoustic / studio performance class |
| `content` | Content class (e.g. karaoke, instrumental) |
| `edit` | Edit class (radio edit, single, extended, album version): the **M7** single/radio-edit-vs-album axis |
| `production` | Production/mix descriptors (e.g. remix) |

### Date

| Axis | Evaluates |
|------|-----------|
| `recording_year` | Recording date |
| `release_year` | Release date |
| `remaster_year` | Remaster year |

### Maximalist (M1-M6)

| Axis | Evaluates |
|------|-----------|
| `duration` | Per-criterion duration tolerance (M4) |
| `artist_role` | Role-aware artist-set match (M5) |
| `language` | Performance language (M6) |
| `composer` | Composer credit (M6) |
| `work` | MusicBrainz work entity (M2) |

> The **M1** DJ/continuous-mix hard-avoid is expressed through the source-aware
> recording verdict (`RecordingClass.CONTINUOUS_MIX`), and **M3** date-axis
> criteria are the `*_year` axes above wired into the AC-C6 tie-break.

## Criterion strengths

Every preference carries a strength (`matching/criteria.py::Strength`):

| Strength | Kind | Verdict when satisfied | Verdict when not |
|----------|------|------------------------|------------------|
| `require` | hard filter | `HARD_PASS` | `HARD_REJECT` |
| `forbid` | hard filter | `HARD_REJECT` | `HARD_PASS` |
| `prefer` | soft score | `SOFT_BONUS` | `SOFT_PENALTY` |
| `avoid` | soft score | `SOFT_PENALTY` | `SOFT_BONUS` |

Hard strengths (`require`/`forbid`) eliminate candidates in Phase 1. Soft
strengths (`prefer`/`avoid`) only reorder survivors in Phase 2; they never drop a
candidate, so recall is preserved.

See [Preferences](preferences.md) for how users express these.

## Source-aware recording verdict

The heart of "right version" is comparing a candidate's **recording class** to the
*source's* class, not judging it in isolation (`matching/version.py`).

**Recording classes** (`RecordingClass`): `studio`, `live`, `karaoke`,
`instrumental`, `remix`, `acoustic`, `tribute`, `altered` (sped-up / slowed /
nightcore), `continuous_mix`.

**Verdicts** (`VersionVerdict`) from `compare_version()`:

| Source -> candidate | Verdict |
|--------------------|---------|
| Same recording class | `MATCH` |
| Candidate is the preferred class (via prefs) | `MATCH` |
| Studio source -> distinct non-studio candidate | `REJECT` (score floored to 0) |
| Non-studio source -> studio candidate | `SUBSTITUTE` (down-ranked, never auto-selected) |
| Two *different* non-studio classes | `REJECT` |
| Explicit source -> clean candidate | `REJECT` |
| Clean source -> explicit candidate (otherwise a match) | `SUBSTITUTE` |
| Remaster of an otherwise-matching recording | `SOFT` |

`source_aware_version_signals()` (`matching/penalties.py`) emits one of
`version:match` / `version:soft` / `version:substitute` / `version:reject`, which
feeds the engine's score cap.

> The legacy candidate-only `version_penalty` / `version_signals` are retained only
> for byte-parity golden tests; the live path uses these source-aware signals.

## Confidence tiers

Identity resolution assigns a confidence tier (`identity/models.py`):

| Tier | Score threshold |
|------|-----------------|
| `VERIFIED` | `>= 0.95` |
| `CONFIRMED` | `>= 0.80` |
| `PROBABLE` | `>= 0.60` |
| `UNCERTAIN` | `< 0.60` |

The resolver uses `CONFIRMED_THRESHOLD = 0.80` and `VERIFIED_THRESHOLD = 0.95`
(`identity/resolver.py`). Tracks below `CONFIRMED` are candidates for `resolve
--upgrade`.

## Deterministic tie-breaks

When distance and soft-preference precedence cannot separate two candidates, a
deterministic tie-break runs in a fixed order (`matching/tiebreak.py`):

1. **release-year**: earliest *original* release wins (`None` treated as newest).
2. **availability**: higher availability rank wins.
3. **stable-id**: lexicographically smallest platform id wins (last-resort, fully
   arbitrary tiebreaker).

This guarantees the same input always yields the same winner (AC-C6).

## Ambiguity surfacing

Two candidates within `AMBIGUITY_DELTA` distance are a near-tie
(`matching/selection.py`). `AMBIGUITY_DELTA` is a fixed module-level constant
(`= 0.05` at `selection.py:61`), not user-configurable. Resolution proceeds:

1. Soft preferences resolve first, by precedence.
2. If still tied, the deterministic tie-break runs.
3. **If only the arbitrary `stable-id` tier separated them**, the winner is *not*
   trusted: the result is flagged `needs_review=True`,
   `review_reason="ambiguous"`, and `decided_by=None`.

Ambiguous results surface via `tuneshift triage` and can be resolved by locking the
correct version. This is the guiding rule of the engine: **a "we can't be sure" is
always a visible review item, never a silent wrong guess.** See
[Matching known limits](matching-known-limits.md) for the full register of what
is deliberately surfaced rather than auto-resolved.

## Inspecting a decision

```bash
tuneshift explain <track-id> [playlist]   # criteria, breakdown, decisive signal, tie-break
tuneshift explain <track-id> --live       # reconcile now instead of reading stored decision
tuneshift triage                          # everything currently needing review
```

A stored decision for a cleanly-matched track looks like this (abbreviated):

```
Track #353: A Woman Oversees - Brandi Carlile [Returning To Myself]

  tidal: exact version available
    reason: clear match [matched]
    chosen: 467491659 (score 100)
```

A track pinned by a user lock reports the lock as the deciding factor:

```
Track #337: Big Yellow Taxi (feat. Lucius) - Joni Mitchell [Joni Mitchell at Newport (Live)]
  ISRC: USRH12302406

  tidal: exact version available
    reason: a durable lock decided this [locked]
    locked: yes (durable user lock)
    chosen: 307238999 (score 80)
```

When no decision has been stored yet, `explain` says so and points you at `--live`
(reconcile now), `sync`, or `doctor`. With `--live`, it prints the full per-candidate
score breakdown and rejection reasons for the current reconcile.

