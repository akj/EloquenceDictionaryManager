# Spec: Eloquence Dictionaries add-on

Status: draft for review
Origin: design discussion following issue #133 (custom dictionaries should be
optional or fully disableable)

## Summary

Split Pronunciation Dictionary management out of the Eloquence NVDA Add-on into
a separate NVDA add-on ("Eloquence Dictionaries"). The dictionaries add-on owns
distribution of community dictionary sets and an editor for personal entries.
The Synth Driver keeps only a small, mechanical loading contract: discover
dictionary layers, merge them per language, and hand resolved files to the
Eloquence Host Process.

## Background and motivation

- PR #110 (shipped in v18) made language-specific Pronunciation Dictionaries
  actually load per Voice Identity. Before it, only `enu*`/generic dictionaries
  ever loaded. This surfaced long-dormant content (e.g. `espmain.dic`'s
  stressed "no" entry, reported in #133).
- The current Dictionary Update flow merges by key and never deletes:
  upstream corrections and deletions never propagate, and switching Dictionary
  Sources leaves the old set's files in place (both sets sound identical once
  either has been installed).
- Downloaded and hand-edited entries are blended into the same files, so
  nothing can safely be replaced, and `installTasks.py` must copy `.dic` files
  across Add-on Updates to avoid losing user work.
- There is no way to disable dictionaries short of deleting files by hand
  (the actual request in #133).

Why a separate add-on rather than fixing this in place:

- The two responsibilities answer to different actors on different clocks:
  the Synth Driver changes with NVDA/host/engine concerns; dictionary content
  changes word-by-word with community curation.
- The seam between them is the ECI `.dic` file format plus a directory
  convention. The format is defined by the frozen Eloquence Engine and will
  never change — the safest possible contract to split across.
- NVDA add-on installs already provide the packaging semantics we want:
  wholesale replace on update, install = available, uninstall = gone.
- The same dictionary sets are consumed by other ECI drivers (e.g. davidacm's
  NVDA-IBMTTS-Driver). A standalone add-on can serve them, and its
  maintainership can eventually move to the dictionary curators themselves.

## Architecture: three dictionary layers

Per language (Voice Code), the effective dictionary content is resolved from
up to two layers; the Synth Driver ships none of its own.

1. **Managed Dictionary Layer** — dictionary sets bundled inside the
   Eloquence Dictionaries add-on's install directory. Content is replaced
   wholesale whenever that add-on updates, so upstream corrections and
   deletions propagate. Both known sets are bundled:
   - Alternative IBM TTS Dictionaries (mohamed00/AltIBMTTSDictionaries)
   - IBM TTS Dictionaries (eigencrow/IBMTTSDictionaries)

   Exactly one set (or none) is active at a time, selected in the
   dictionaries add-on's settings. Bundling both makes switching a dropdown
   rather than an uninstall/reinstall and avoids two-add-ons-installed
   conflicts. The sets are small text files; size is not a concern.

2. **User Dictionary Overlay** — per-language `.dic` files containing the
   user's personal entries. Lives in NVDA user configuration (neutral
   territory owned by neither add-on's installer), so it survives updates and
   uninstalls of both add-ons with no preservation hooks. Starts empty.

3. Synth fallback — none. With neither layer present, no dictionaries load
   (already the shipped default today).

### Precedence

Resolution is **per key within a language**, not wholesale per file: the
overlay overrides exactly the words it names and inherits everything else from
the managed set. A user fixing one Spanish word keeps the other thousands of
managed Spanish entries. Wholesale per-language selection is explicitly
rejected.

## The loading contract (Synth Driver side, this repo)

The Synth Driver must never depend on the dictionaries add-on — only discover
it. Dictionaries remain fully optional.

### Discovery

- The Synth Driver scans installed, enabled add-ons for the dictionaries
  add-on (match by add-on name; a marker file in its dictionary directory
  declares the contract version).
- Dictionary directory layout is the public API between the add-ons:

  ```
  <dictionaries add-on>/dictionaries/
      contract.ini            # contract version, active set name
      <set-id>/
          <code>main.dic
          <code>root.dic
          <code>abbr.dic
  ```

- The User Dictionary Overlay lives at
  `<NVDA user config>/eloquenceDicts/<code>{main,root,abbr}.dic`. Resolve it
  relative to the *active* configuration root so Secure Screens (which run
  from the System Configuration Copy) degrade gracefully rather than reaching
  into an unavailable user profile.

### Resolution and merge

- The Synth Driver (64-bit side, not the host) resolves, per Voice Code and
  per slot (main / root / abbreviation):
  1. the active managed set's file, if the dictionaries add-on is present,
     the managed layer is enabled, and the file exists;
  2. the overlay file, if user dictionaries are enabled for that language.
- Language fallbacks (`eng`→`enu`, `esm`→`esp`, `frc`→`fra`, `chs`→`enu`)
  become driver-side policy, applied during resolution. The host's candidate
  search is removed.
- When both layers contribute to a slot, the driver writes a merged temp file:
  entries deduplicated by key, overlay entry winning. Merging is required
  because `eciLoadDict` accepts exactly one file per slot — precedence cannot
  be expressed by loading two files. Determinism comes from the merge, never
  from engine lookup-order behavior.
- The Host Command for dictionary loading changes to carry **explicit file
  paths per slot**. The Eloquence Host Process becomes purely mechanical: load
  the given files, no searching, no fallback policy. (Encoding of paths and
  content handling in the host is unchanged.)

### Settings (Synth Driver panel)

- **Use downloaded dictionaries** (managed layer) — global on/off. Off is the
  #133 fix: managed content stops applying without deleting anything.
- **Use my dictionary entries** (overlay) — global on/off, plus per-language
  toggles. Per-key merge means presence of entries already scopes the effect;
  the per-language toggles are an A/B affordance ("does Spanish sound better
  with my edits?") and cost nothing since resolution is per-language anyway.
- A pointer to the dictionaries add-on (add-on store link) replaces the
  current download buttons.
- The existing `ABRDICT` engine toggle (abbreviation processing) is unrelated
  and stays as-is.

### Removals from this repo

- The Dictionary Update download/merge code in `eloquence.py`
  (zip fetch, CP1252 munging, key-merge) — superseded by the managed layer.
- `installTasks.py` dictionary preservation — nothing user-owned lives in the
  add-on directory anymore.
- Host-side dictionary candidate search and `DICTIONARY_LANGUAGE_FALLBACKS`
  — policy moves to the driver.

## The dictionaries add-on

Working name: **Eloquence Dictionaries**. New repository; standard NVDA add-on
scaffolding (buildVars/manifest/SCons or the add-on template).

### Set management

- Both sets bundled as add-on content; updates to set content ship as add-on
  releases through the add-on store — no custom download code anywhere.
- Settings panel: active set dropdown (Alternative / IBM TTS / None).
- Refreshing bundled content from the upstream repos is a build-time step of
  this add-on (submodules or a fetch script), not a runtime feature.

### Entry editor

Writes **only** to the User Dictionary Overlay; managed files are never
edited. "Customize a managed entry" copies it into the overlay; "restore
default" removes the overlay entry. The editor is justified over hand-editing
by three concrete capabilities:

1. **Validation at entry time** — the format is tab-separated, strictly
   CP1252, with arcane annotation/phoneme syntax; the dialog rejects or
   normalizes what Notepad would silently corrupt.
2. **Live preview** — speak the candidate entry through the active synth and
   iterate, replacing the edit-file / reload-synth / listen loop.
3. **Accessible slot guidance** — an explicit, screen-reader-friendly UI for
   choosing main vs. root vs. abbreviation and browsing effective entries
   (managed + overlay, with override provenance visible).

### Migration import tool

One-time helper for users upgrading from the blended-file era:

- The old blended files mix set content with hand edits, but the set side is
  reconstructible: diff the user's old files against the union of all
  historical versions of both upstream sets (from their git history). Lines
  matching no known upstream version are almost certainly hand edits.
- Present those leftovers as pre-checked import candidates for the overlay.

## Migration (Synth Driver side)

On first run of the new Synth Driver version:

- Back up any existing `.dic` files from `synthDrivers/eloquence/` to a
  sibling backup folder, then stop loading from that location.
- Start clean: managed layer (if the dictionaries add-on is installed) plus an
  empty overlay. Users who never hand-edited get identical-or-better content
  with working updates; hand-editors are pointed at the import tool.
- Old files are **not** auto-imported into the overlay — that would shadow the
  entire managed set with stale content and recreate the pinning bug this
  design removes. The behavior change for hand-editors is visible and
  recoverable (backup + import), never silent.

## Non-goals

- Editing managed set files in place, or per-user forks of whole sets.
- Any integration with NVDA's speech pronunciation dictionaries — different
  layer (text substitution vs. engine phoneme/root control), different scope
  (per-user preference vs. shared content).
- New dictionary formats or non-ECI synths.
- Automatic runtime downloads of any kind.

## Open questions

1. Migration UX wording and default (needs fastfinge's read on the user base).
2. Asian-language dictionaries: slots and encodings for `chs`/`jpn`/`kor`
   files are untested; CP1252 validation is wrong for them. Ship Western-only
   first?
3. Exact discovery mechanism (addonHandler scan vs. a small shared-state file)
   and behavior when the dictionaries add-on is installed but disabled.
4. Whether NVDA-IBMTTS-Driver consumption is a stated goal for v1 of the
   contract or just kept possible.
5. Add-on store listing name/id, and eventual maintainership handoff to the
   dictionary curators.
6. CONTEXT.md updates: "Dictionary Source" and "Dictionary Update" describe
   the superseded flow; new terms (Managed Dictionary Layer, User Dictionary
   Overlay) should be added when implementation starts.
