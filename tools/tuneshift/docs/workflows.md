# Common Workflows

End-to-end recipes for the real user journeys. Each assumes you have authenticated
(`tuneshift login tidal` etc.) and are running from `tools/tuneshift/`. For the
full flag reference see [CLI.md](CLI.md); for concepts see the linked guides.

## I added tracks and they are not mapped yet

`add` and `import-text` are library-first: they create the track and **enqueue**
resolution rather than blocking on the network (see
[resolution-enrichment.md](resolution-enrichment.md)). Drain the queue with
`resolve`:

```bash
tuneshift add "Road Trip" "Heroes" "David Bowie" --album "\"Heroes\""
tuneshift resolve "Road Trip" --all     # resolve every pending track in the playlist
tuneshift resolve --status              # coverage %, resolved/pending/quarantined counts
```

`resolve` is resumable and idempotent: if it is interrupted, just run it again and
it picks up where it left off. `--platform` defaults to `tidal`.

Tip: a full-library `resolve --all` can take hours (MusicBrainz rate-limits to
about 1 request/second). Keep the machine awake:

```bash
caffeinate -i tuneshift resolve --all --platform tidal
```

## Triage says a track is ambiguous

When the engine cannot be sure which version is right, it does not guess: it flags
the track for review. Inspect and resolve it:

```bash
tuneshift triage                         # cluster tracks needing review
tuneshift explain <track-id>             # why the current decision was made
tuneshift explain <track-id> --live      # reconcile now and show the full breakdown
tuneshift lock "Road Trip" "Heroes" --tidal 12345678   # pin the correct version
```

Locking records a durable "this is the right version" decision that survives
re-syncs and re-matches (see [locks.md](locks.md)). If triage surfaced a track that
simply needs a manual mapping, use `map` instead of `lock`:

```bash
tuneshift map "Road Trip" "Heroes" --tidal 12345678
```

## I want all my Atmos playlists to prefer Atmos versions

Set a typed preference at the playlist scope, then re-match so existing mappings are
re-evaluated against the new preference:

```bash
tuneshift prefs set --playlist "Atmos Nights" spatial prefer atmos
tuneshift plan rematch "Atmos Nights"    # build a plan (changes nothing yet)
tuneshift plan show <plan-id>            # review the proposed remaps
tuneshift plan apply <plan-id>           # apply
```

`prefer` is a soft preference: it reorders candidates but never drops a track that
has no Atmos version, so recall is preserved. To inspect what actually applies to a
specific track after precedence resolution:

```bash
tuneshift prefs show --playlist "Atmos Nights" --track 4021   # --track takes a track ID
```

See [preferences.md](preferences.md) for the full scope/precedence model.

## A locked track disappeared from Tidal

When a locked platform ID no longer resolves, the lock is **dead**. `plan heal`
detects dead locks and proposes a rebind to an equivalent recording, routed through
plan/apply so nothing changes until you apply it:

```bash
tuneshift plan heal "Road Trip"          # produce a heal plan
tuneshift plan show <plan-id>            # review the rebind/hold
tuneshift plan apply <plan-id>           # rebind (or hold as unavailable)
```

Heal only proposes a change when the locked ID is confirmed gone. A global lock with
no equivalent is held as unavailable; a playlist-override lock is surfaced for
review. See [locks.md](locks.md).

## I want to pin a specific album version for one playlist only

Use a playlist-scoped lock so the choice applies to that playlist without changing
the track everywhere else:

```bash
tuneshift lock "Acoustic Set" "Heroes" --tidal 87654321 --scope playlist
tuneshift lock "Acoustic Set" --list     # show effective locks for this playlist
```

A playlist override wins over the global default lock only when it is approved and
carries a platform ID (see the precedence rules in [locks.md](locks.md)).

## How do I resume a long-running resolve?

Just run the same command again. The resolution worker drains a durable queue
(`resolution_queue`) and is idempotent: already-resolved rows are left untouched,
pending rows continue, and quarantined rows stay quarantined until you re-open them.
There is no separate "resume" flag.

```bash
tuneshift resolve --all                  # re-running continues from where it stopped
tuneshift resolve --status               # check remaining pending/quarantined counts
```

To retry only the uncertain matches after a matching improvement, use `--upgrade`
(re-resolves tracks below the CONFIRMED tier); to re-resolve everything from
scratch, use `--force`. See [resolution-enrichment.md](resolution-enrichment.md).
