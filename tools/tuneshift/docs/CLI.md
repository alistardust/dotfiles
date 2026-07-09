# CLI Reference

Complete reference for every `tuneshift` subcommand. For conceptual detail see the
feature guides linked from the [README](../README.md).

## Global options

```
tuneshift [--db PATH] [-v | -q] [--print-completion {bash,zsh,tcsh}] <command> ...
```

| Option | Effect |
|--------|--------|
| `--db PATH` | Use an alternate database file |
| `-v` / `-q` | Verbose / quiet logging (to stderr) |
| `--version` | Print version |
| `--print-completion {bash,zsh,tcsh}` | Emit shell-completion script |

---

## Library

### `add`
`add <playlist> <title> <artist> [--album ALBUM] [--replace TITLE]`
Add a track (playlist created if new). `--replace` swaps a track by title,
inheriting its position and pins. Enqueues async resolution (library-first).

### `rm`
`rm <playlist> <target>`: remove a track by position number or title substring.

### `edit`
`edit <track_id> [--title] [--artist] [--album] [--energy 0-1] [--valence 0-1] [--strip-album-from-title] [--playlist NAME] [--dry-run]`
Edit canonical track metadata. `--energy`/`--valence` are manual sequencer
overrides. `--strip-album-from-title` removes a trailing parenthetical repeating the
album name (batchable with `--playlist`).

### `import-text`
`import-text <file> [--name NAME] [--force]`: import a playlist from a text file;
each track is enqueued for resolution.

### `ingest`
`ingest {tidal,spotify,ytmusic} <playlist_id>`: one-time import of a platform
playlist into the canonical library (the only read-from-platform path).

### `list`
`list`: list all playlists.

### `status`
`status [playlist]`: show sync status for a playlist (all if omitted).

### `merge`
`merge <sources...> --into TARGET [--plan] [--delete-sources]`: merge playlists.
`--plan` produces a plan without changing anything.

---

## Resolution & enrichment

See [Resolution & enrichment](resolution-enrichment.md).

### `resolve`
`resolve [playlist] [--track TITLE ARTIST] [--all] [--platform PLATFORM] [--upgrade] [--force] [--status] [-v] [--throttle OPS_PER_SEC]`
Resolve tracks to platform candidates and hydrate metadata (ISRC, duration, album).
`--upgrade` re-resolves below-CONFIRMED tracks; `--force` re-resolves resolved ones;
`--status` shows coverage/quarantine stats; `--throttle N` caps resolve to N
operations/second for local resource pacing (default 3.0). Only one `resolve`
run may execute at a time: a concurrent run refuses (PID lock at
`.tuneshift/resolve.lock`), which prevents the concurrent-writer corruption that
SQLite cannot arbitrate.

### `enrich`
`enrich [playlist] [--all] [--catalog] [--platform PLATFORM] [--classify] [--reclassify] [--model MODEL] [--max-retries N] [--refresh] [--dry-run]`
Fetch platform/audio metadata and/or run LLM classification. See the
[enrich flag table](resolution-enrichment.md#the-enrich-command).

### `map` / `unmap`
`map [playlist] [title] [--track-id ID] [--tidal ID] [--ytmusic ID] [--verify] [--dry-run]`
Manually map a canonical track to a platform ID (auto-captures Tidal catalog
metadata). `unmap <playlist> <title> [--tidal] [--ytmusic]` removes a mapping.

### `alias`
`alias {list,show,add,remove}`: manage artist-alias equivalence classes
(e.g. Ke$ha / Kesha). `add` needs >=2 members.

---

## Version control (matching)

See [Version-selection engine](version-selection.md), [Preferences](preferences.md),
and [Identity locks](locks.md).

### `prefs`
`prefs {show,set,unset,list,clear} [key] [value] [target] [--global | --playlist NAME | --track ID]`
Manage typed version preferences at global / playlist / track / playlist-track
scope. See [Preferences](preferences.md).

### `lock` / `unlock`
`lock [playlist] [title] [--track-id ID] [--tidal ID] [--ytmusic ID] [--scope {global,playlist}] [--list] [--apply] [--interactive]`
Lock a track to a specific release (routed via plan/apply; `--list` shows effective
locks with precedence). `unlock` releases a lock with the same scoping.

### `explain`
`explain <track_id> [playlist] [--platform {spotify,tidal,ytmusic}] [--live]`
Explain a match decision: criteria, score breakdown, decisive signal, tie-break,
and per-candidate rejection reasons. `--live` reconciles now instead of reading the
stored decision. (`why` is a deprecated alias.)

### `triage`
`triage [playlist] [--platform {spotify,tidal,ytmusic}]`: cluster tracks needing
review and show the review burden.

---

## Plan / apply

See [Plan / apply](plan-apply.md).

### `plan`
`plan {sync,rematch,migrate,heal,list,show,reject,apply,rollback} ...`
Generate, inspect, apply, or roll back plans.

### `sync`
`sync [playlist] [platform] [--all] [--reconcile] [--apply] [--interactive]`
Plan (default) or apply a routed push. Default writes a plan and pushes nothing
(AC-P1); `--apply` builds and pushes; `--interactive` steps through each push.

### `diff`
`diff <playlist> [platform]`: show what would change on sync.

### `batch`
`batch [playlist] [flags]` performs multiple playlist mutations under the
plan/apply model. Flags group into three kinds:

| Kind | Flags |
|------|-------|
| **Mutation** | `--dedupe` / `--cap N`, `--rm-artist NAME`, `--rm 'Title - Artist'` (repeatable), `--add 'Title - Artist'` (repeatable), `--sweep-banned`, `--review-findings` |
| **Structural** | `--split NAME` / `--filter EXPR` (repeatable), `--rebuild` / `--count N` / `--fresh`, `--structure` / `--narrative-file FILE` |
| **Plan control** | `--plan`, `--plan-file FILE`, `--from-stdin`, `--show-plan`, `--apply`, `--discard`, `--undo` / `--id N`, `--history`, `--interactive` |

`--dedupe` caps tracks per artist (`--cap`, default 1); `--filter` accepts
`artist:X`, `vibe:X`, or `energy:<0.4` expressions; `--rebuild` targets `--count`
tracks (default 50) and `--fresh` clears the playlist first.

---

## Sequencing

See the [Sequencer section of CLAUDE.md](../CLAUDE.md).

### `order`
`order <playlist> [--arc ARC] [--weights WEIGHTS] [--dry-run] [--no-sync] [--auto-on] [--auto-off]`
Reorder by energy arc (default `wave`). `--auto-on`/`--auto-off` toggle reorder on
sync.

### `pin`
`pin <playlist> [--opener T] [--closer T] [--position INDEX T] [--adjacent T...] [--group NAME] [--moment T] [--remove T] [--list]`
Pin tracks as openers/closers, to a fixed position, as an adjacency group, or as a
narrative moment (placed at climax).

### `narrative`
`narrative <playlist> [text] [-f FILE] [--clear]`: set/show/clear the intended
narrative arc.

### `weights`
`weights {list,set,show} [playlist] [values...] [--preset PRESET]`: manage
sequencing weight presets (`dimension=value` pairs).

### `goal`
`goal <playlist> [text] [--clear]`: set/show/clear a playlist goal.

### `concept`
`concept <playlist> [--theme THEME] [--require RULE] [--prefer RULE] [--show] [--clear]`
Set/show a playlist concept with hard (`--require`) and soft (`--prefer`) rules.

---

## Curation

### `curate`
`curate <playlist> {trim,analyze,fill} [--dry-run] [--strategy {quick,hybrid,deep}] [--target-tracks N] [--hard-limit N]`
Curate a playlist (trim to size, analyze, or fill gaps).

### `compose`
`compose <playlist> [--analyze] [--reorder] [--fill-gaps] [--dry-run] [--apply]`
Narrative-driven composition (gap report, reorder, candidate fill).

### `review`
`review <playlist> [--fix]`: review a playlist against its concept rules;
`--fix` removes hard-rule violators.

### `analyze`
`analyze <playlist>`: analyze playlist metadata.

### `audit`
`audit [playlist] [--matching-only] [--vibes-only] [--concept-only] [--fix]`
Full playlist health audit; `--fix` generates a batch plan from findings.

### `ban`
`ban [artist] [--reason R] [--list] [--remove ARTIST]`: manage the global banned
artist list.

---

## Organization

### `tag` / `untag`
`tag {track,query,derive,list-tags} ...`: tag tracks/playlists, query by tag,
auto-derive tags from metadata, or list tags with counts.
`untag <playlist> <collection>` removes a collection tag.

### `collections`
`collections [collection] [--create NAME] [--delete NAME]`: manage playlist
collections.

### `folders`
`folders {list,import,create,rename,delete,move,unassign,sync,pull,status} ...`
Manage Tidal folder structure and mirror it locally.

### `link`
`link {tidal,spotify,ytmusic} [name] [url] [--quiet]`: link platform playlist IDs
(auto-discover or manual).

### `share`
`share <name> [--format {plain,markdown,slack,discord,urls}]`: generate shareable
links for a playlist.

---

## Platform / config

### `login`
`login {tidal,spotify,ytmusic}`: authenticate with a platform.

### `export`
`export <playlist> [-f {text,csv,json,soundiiz,tunemymusic}] [-o OUTPUT]`
Export a playlist to a file or stdout.

### `import-json`
`import-json <file> [--into NAME]`
Restore a playlist from a JSON snapshot produced by `export --format json`. This
is the recovery path for the concurrent-DB hazard (a playlist clobbered by a
last-writer-wins DB overwrite). Restore is DB-only and canonical-first: it
recreates the playlist (or, with `--into`, under a different name) and its track
membership, then enqueues each track for resolution; it never pushes to a
platform (a later `sync` distributes). Idempotent: tracks already present are
skipped, so re-running restores nothing new.

### `doctor`
`doctor [playlist] [--all] [--apply] [--only ITEM_ID] [--override ITEM_ID=TIDAL_ID] [--no-sync] [--dry-run] [--max-retries N] [-y] [--quiet] [--orphans] [--enqueue-orphans]`
Scan playlists for mapping issues and apply fixes (plan/apply model). `--apply`
applies the previously written plan; `--override` remaps a specific item.
`--orphans` lists orphaned tracks (no platform mapping, no resolution-queue
entry, and not quarantined) that are invisible to `triage` and never resolve on
their own; `--enqueue-orphans` queues them so a later `resolve` picks them up.
Orphan detection is read-only and needs no platform login.

> `doctor` vs `plan heal`: `doctor` scans broadly for broken or missing platform
> mappings and proposes remaps; `plan heal` specifically fixes **dead locks**
> (locked platform IDs that no longer resolve on the platform). See
> [Plan / apply](plan-apply.md) and [Identity locks](locks.md).

### `config`
`config [key] [value] [--show]`: configure settings (e.g. `anthropic-key`,
`openai-key`, `llm-backend`).
