# Preferences

Preferences steer the [version-selection engine](version-selection.md): they tell
TuneShift which version of a track you want when more than one is playable. They
are **typed**, **multi-target**, and resolved across three **scopes**.

Preferences live in `matching/preferences.py` and the `prefs` command
(`commands/prefs_cmd.py`), and are persisted in the `playlist_track_prefs` table.

## The typed model

A preference is a triple:

```
(criterion, strength, target)
```

- **criterion**: one of the [criteria axes](version-selection.md#criteria-axes)
  (`spatial`, `mix`, `fidelity`, `performance`, `content`, `edit`, `production`,
  `recording_year`, `release_year`, `remaster_year`, `duration`, `artist_role`,
  `language`, `composer`, `work`). Validated against `KNOWN_AXES`.
- **strength**: `require` | `prefer` | `avoid` | `forbid`
  (hard/soft semantics in [Criterion strengths](version-selection.md#criterion-strengths)).
- **target**: the token the strength applies to. Examples:
  - structured audio: `atmos` / `Dolby Atmos` / `dolby_atmos` (canonicalized via a
    token whitelist),
  - duration: `5%`, `3s`, `3`,
  - edit: `album_version`, `radio_edit`, `single_version`, `extended`,
  - language: a code or name like `en`.

The canonical list of accepted tokens and their aliases lives in
`matching/token_whitelist.yaml`; that file is the source of truth for what each
axis will canonicalize.

```bash
tuneshift prefs set spatial prefer atmos
tuneshift prefs set --playlist "Focus" content avoid karaoke
tuneshift prefs set --playlist "Focus" content avoid instrumental
tuneshift prefs set --playlist "Live 2024" performance require live
```

## Scopes and precedence

Preferences can be set at three (effectively four) scopes:

| Scope | Flags | Applies to |
|-------|-------|------------|
| **global** | *(default, or `--global`)* | every track everywhere |
| **playlist** | `--playlist NAME` | every track in one playlist |
| **track** | `--track ID` | one track everywhere |
| **playlist-track** | `--playlist NAME --track ID` | one track in one playlist |

Precedence is **most-specific-wins**:

```
global  <  playlist  <  track  <  playlist-track
```

`resolve_scoped_specs()` (`matching/registry.py`) collapses preferences by
`(axis, canonical target)`, keeping the most specific scope's value. `prefs show`
and `prefs list` render the effective set with this precedence applied.

### Inspecting the effective cascade for one track

To see exactly what applies to a specific track in a specific playlist after
precedence resolution, pass both scope flags to `prefs show`:

```bash
tuneshift prefs show --playlist "Focus" --track 4021   # effective cascade for track 4021 in Focus
```

Note the caveat: `--track` takes an integer **track id**, not a title (it is
`type=int` in the parser). Get the id from `list`, `status`, or the `Track #<id>`
header printed by `explain`. Combine `--playlist NAME --track ID` for the
playlist-track scope; drop `--playlist` to inspect the track-everywhere scope.


## Multi-target axes

A single axis can carry **multiple targets simultaneously** at the same scope. This
is the FL3 fix: the earlier model overwrote one pref per axis.

```bash
# Both are kept; they do not overwrite each other:
tuneshift prefs set --playlist "Focus" content avoid karaoke
tuneshift prefs set --playlist "Focus" content avoid instrumental
```

This is enforced by the DB unique index, which keys on
`(scope, criterion, target)` rather than `(scope, criterion)`:

```sql
CREATE UNIQUE INDEX idx_playlist_track_prefs_scope
    ON playlist_track_prefs(
        COALESCE(playlist_id, -1), track_id, criterion, COALESCE(target, '')
    );
```

The write path de-dupes by `(criterion, canonical target)`, and
`resolve_scoped_specs()` collapses only identical `(axis, target)` rows, so
distinct targets on one axis coexist.

## Commands

```bash
tuneshift prefs set <criterion> <strength> <target>   # add/replace a typed pref
tuneshift prefs unset <criterion> [target]            # remove a typed pref
tuneshift prefs list                                  # list typed prefs w/ precedence
tuneshift prefs show                                  # typed + legacy keyword prefs
tuneshift prefs clear                                 # clear legacy keyword prefs only
```

All accept `--global` / `--playlist NAME` / `--track ID` scope flags (combine
`--playlist` + `--track` for playlist-track scope).

## Legacy keyword model

> **Deprecated.** The legacy keyword model (`version.prefer`, `version.avoid`,
> `version.tiebreak_order`, `version.duration_tolerance_percent`,
> `version.min_lead`) is scheduled for removal. Use the typed
> `(criterion, strength, target)` model for all new work.

`show` and `clear` still reference an older keyword model for backward
compatibility (`commands/prefs_cmd.py`):

- `version.prefer`
- `version.avoid`
- `version.tiebreak_order`
- `version.duration_tolerance_percent`
- `version.min_lead`

`prefs show` prints both the typed prefs and these legacy keyword prefs at the
global/playlist scopes. `prefs clear` removes **only** the legacy keys and
preserves the typed `criteria` blob. Prefer the typed model for all new work.
