# Spec: Eloquence Dictionary Manager add-on

Status: implementation-ready v1 spec assembled from the
[wayfinder map (issue #1)](https://github.com/akj/EloquenceDictionaryManager/issues/1),
2026-07-18

The former working name was **Eloquence Dictionaries**.

## Summary

Eloquence Dictionary Manager (EDM) is an NVDA add-on that distributes a
versioned community pronunciation dictionary set, edits a shared personal
dictionary overlay, exchanges personal entries, and recovers hand edits from
older Eloquence installations. It is a provider and editor, not a synth.

Consuming ECI synths discover EDM's installed static content through a small,
consumer-neutral directory contract. Each synth owns runtime set activation,
overlay enablement, language fallback, and the mechanics needed to load the
resolved files into the engine.

## Background and motivation

Eloquence issue
[#133](https://github.com/fastfinge/eloquence_64/issues/133) exposed pronunciation
content that users could not disable without deleting files. The old update
flow also merged upstream content and hand edits into the same files, never
propagated upstream deletions, and left stale content behind when sources
changed.

Dictionary content and synth-driver code belong on different release clocks.
EDM can replace managed content wholesale while preserving personal entries in
NVDA configuration. The seam is stable: ECI `.dic` files plus a versioned
directory layout. The separate package also keeps the data usable by other ECI
synths without making them depend on EDM's executable code.

## Scope and responsibility boundary

EDM v1:

- publishes eligible Managed Dictionary Sets as static add-on content;
- presents provenance and licensing details for those sets;
- edits the Personal Dictionary Overlay;
- imports and exports personal entries; and
- reconstructs likely hand edits from old blended Eloquence files.

EDM has no NVDA Settings panel and no active-set setting. Each consuming synth
selects its active Managed Dictionary Set, decides whether to use the Personal
Dictionary Overlay, and owns language fallback policy. Eloquence consumption is
required for v1. NVDA-IBMTTS-Driver consumption remains deliberately possible,
but is not a v1 acceptance criterion.

## Dictionary architecture and precedence

The effective pronunciation for a language has three layers:

1. **Engine baseline**: Eloquence's built-in pronunciation rules and lexicon.
2. **Managed Dictionary Sets**: one or more sets the consuming synth turns on
   for the language, in an order the synth chooses. Later sets override earlier
   ones per key.
3. **Personal Dictionary Overlay**: user-owned entries shared by compatible
   synths from the active NVDA configuration.

Precedence is per language, slot, and key: Personal overrides every Managed
set, whatever order the synth uses for them, and Managed overrides the engine
baseline. An overlay entry replaces only the matching key;
it never selects a whole replacement file. Root keys compare case-insensitively;
main and abbreviation keys compare exactly. The ECI engine accepts one file per
slot, so the consumer must realize this precedence before loading.

Main and root entries also interact across slots. When a word has both a main
entry and a root entry, the engine speaks it with the main entry, whatever
order the files were stacked in. This holds on the proprietary `ECI.DLL`,
openevv and ReLoq C
([engine tests](https://github.com/fastfinge/eloquence_64/issues/173#issuecomment-6731338267)).
Merging each slot separately would therefore let an earlier layer's main entry
beat a later layer's root entry, and a personal root entry would lose to a
set's main entry. A consumer applies this cross-type rule when it merges:

- The layers are the Managed Dictionary Sets in the consumer's order, then the
  Personal Dictionary Overlay.
- When a later layer has a word in root, the consumer drops that word from
  main in every earlier layer. It compares the words without case, the way
  root keys compare, so a root entry for `foo` drops main entries for `foo`,
  `Foo` and `FOO`.
- A later layer's main entry already beats an earlier layer's root entry, so
  that direction needs nothing.
- Within one layer, whether one set or the overlay, nothing is dropped: both
  entries are loaded and main beats root, as in the engine.

Every contract version 1 consumer applies this rule, so each one reads the same
overlay the same way. It changes nothing a provider ships, so it needs no new
contract version. Other details of a particular driver's merge implementation
are outside this spec.

Managed files are never edited in place. Updating EDM replaces them wholesale,
so upstream corrections and deletions propagate. The personal overlay survives
EDM and synth updates or uninstallations.

The engine format has one `key<TAB>value` entry per line, no comments or blank
lines, and one file per slot. Main, root, and abbreviation slots have different
key and value rules. See
[ECI `.dic` format](../research/eci-dic-format.md) for the authoritative format,
deduplication, and validation detail.

## Directory contract v1

This section is the complete provider/consumer contract resolved in
[ticket #5](https://github.com/akj/EloquenceDictionaryManager/issues/5), with
the additive amendments from
[ticket #8](https://github.com/akj/EloquenceDictionaryManager/issues/8) and
[ticket #13](https://github.com/akj/EloquenceDictionaryManager/issues/13), and
the consumer rules agreed with the Eloquence maintainers on
[fastfinge/eloquence_64#173](https://github.com/fastfinge/eloquence_64/issues/173).

### Purpose and discovery

`contract.ini` is a provider/consumer handshake marker, not user
configuration. Consumers scan fully installed add-ons with
`addonHandler.getAvailableAddons()` and recognize compatible providers by a
valid marker. A provider need not be enabled or running: disabling EDM removes
its executable UI while its installed static dictionary data remains available.

EDM's frozen manifest ID is `eloquenceDictionaryManager`. It is also the NVDA
install-directory name that the Eloquence driver matches while locating EDM.
That known location is only a discovery aid: the contract marker, not the
manifest ID, establishes provider compatibility, preserving consumer-neutral
discovery and allowing other providers.

A missing, malformed, pending-installation, or unsupported provider is ignored
with diagnostic logging.

### Provider layout

```text
<installed provider add-on>/
  dictionaries/
    contract.ini
    sets/
      <set-id>/
        set.ini
        <voice-code>main.dic
        <voice-code>root.dic
        <voice-code>abbr.dic
```

Dictionary filenames are canonical lowercase ASCII: a lowercase three-letter
ECI voice code, the lowercase slot name, and `.dic`, for example
`enumain.dic`, `enuroot.dic`, and `enuabbr.dic`. The refresh process normalizes
upstream filename casing without altering dictionary contents. Generic
unprefixed filenames are not part of the contract; language fallback is
consumer policy.

Consumers must ignore unrecognized files in a set directory. This permits an
additive future file such as `<voice-code>ext.dic` without breaking contract v1
consumers.

### Contract marker and versioning

```ini
[contract]
format = eci-dictionary-sets
version = 1
```

`contract.ini` contains no active set, provider identity, absolute paths, or
duplicated set inventory. `version` is a major-only integer schema generation,
independent of the EDM release version. Content changes, set additions or
removals, and additive optional metadata retain version 1. Required path,
filename, field, or slot-semantic changes that an older consumer cannot safely
interpret require a new version. Consumers accept only explicitly supported
versions and ignore unknown optional fields.

### Managed Dictionary Set identity and metadata

A Managed Dictionary Set ID identifies an upstream dataset globally. It is
lowercase, origin-qualified ASCII, immutable across repository renames,
transfers, and provider changes, and never reused. A materially divergent fork
gets a new ID.

The v1 dataset IDs are:

- `github.eigencrow.ibmtts-dictionaries`
- `github.mohamed00.alt-ibmtts-dictionaries`

Only the first is eligible for and included in the v1 package. The second ID is
retained as the stable identity used by migration history and for a possible
future licensed package.

A synth that downloads a GitHub repository as a set derives its ID with these
rules, so every synth gives the same repository the same ID and a download
matches an installed copy of the same dataset. See
[ADR 0003](../adr/0003-set-ids-for-downloaded-repositories.md).

1. The two repositories above keep their registered IDs:
   `eigencrow/IBMTTSDictionaries` is `github.eigencrow.ibmtts-dictionaries`,
   and `Mohamed00/AltIBMTTSDictionaries` is
   `github.mohamed00.alt-ibmtts-dictionaries`.
2. Any other repository gets `github.<owner>.<repo>`, with the owner and the
   repository name each encoded as described below.
3. A synth that offers a sub-folder of dictionary files as a separate set, such
   as the `IBMTTS 6.7` folder in AltIBMTTSDictionaries, appends `..` and the
   encoded folder path to the repository's ID, registered or not. The
   repository's top-level files keep the ID without a folder.

To encode a name, lowercase its ASCII letters and keep `a`–`z`, `0`–`9`, and
`-`. Replace every other character with `.` followed by the two lowercase hex
digits of each of its UTF-8 bytes. This is percent-encoding with `.` in place of
`%`. A nested folder path joins its folders with `/` before encoding. GitHub
owner names contain only letters, digits, and hyphens, so an encoded owner is
the owner lowercased. For example:

- `fastfinge/eloquence_64` is `github.fastfinge.eloquence.5f64`.
- `example/dict.js` is `github.example.dict.2ejs`, and `example/dict-js` is
  `github.example.dict-js`.
- `example/.github` is `github.example..2egithub`.
- The `IBMTTS 6.7` folder in AltIBMTTSDictionaries is
  `github.mohamed00.alt-ibmtts-dictionaries..ibmtts.206.2e7`.
- A `British/v2` folder in `example/dicts` is
  `github.example.dicts..british.2fv2`.

An owner contains no `.`, and an encoded name uses `.` only before two hex
digits, so an ID can be read back into its owner, repository, and folder.
Different repositories and folders therefore never share an ID. Folder paths
that differ only in the case of ASCII letters are the same folder, as they are
on Windows.

Rule 2 must never produce a registered ID. The repositories
`eigencrow/ibmtts-dictionaries` and `mohamed00/alt-ibmtts-dictionaries` would
get exactly the registered IDs, so they get no ID, and a synth doesn't offer
them as sets. Any set EDM registers later takes the ID that rule 2 gives its
repository, so the two above remain the only exceptions.

Each included set is self-describing. Its `set.ini` declares the same ID as its
directory and contains:

```ini
[set]
id = <immutable set ID>
name = <canonical upstream project name / English gettext message ID>
source_url = <upstream project URL>
source_version = <upstream release tag>
source_revision = <full commit SHA>
attribution = <source-owned credit/provenance text>
license = <SPDX expression or specific permission reference>
license_url = <license or permission evidence URL>
```

A synth's own downloaded copy needs fewer fields; see
[Missing sets and consumer expectations](#missing-sets-and-consumer-expectations).

Language and slot availability are inferred from the `.dic` files rather than
duplicated in metadata. Consumers persist `id` and display `name`. The editor
shows managed provenance as `Managed — <name> (<source_version>)`. A read-only
Set Details action for a selected managed row exposes attribution, source and
license links, and the exact revision; full SHAs stay out of routine lists and
speech.

Metadata validation fails closed per set, not per provider. A missing required
field, ID/directory mismatch, invalid ID, or unsupported encoding ignores only
that set with diagnostic logging. Valid sibling sets remain available. Unknown
optional fields are ignored.

### Personal Dictionary Overlay

All compatible synths share the user-owned overlay:

```text
<active NVDA configuration>/
  eciDictionaries/
    personal/
      <voice-code>main.dic
      <voice-code>root.dic
      <voice-code>abbr.dic
```

Each synth independently decides whether to apply it. Resolving from the active
configuration also keeps secure or portable configurations isolated.

### Missing sets and consumer expectations

If a selected Managed Dictionary Set is unavailable, the synth must not silently
substitute another set. It retains the selected ID, leaves out only that set,
keeps applying its other selected sets and the personal overlay when enabled,
and reports the unavailable
selection in its UI or diagnostic log. The set resumes automatically if the same
ID returns. Engine pronunciation is the safety net.

Synths do not bundle duplicate community sets. A synth may download a set for
the user at runtime; that copy is the user's choice and is not covered by
EDM's licensing or review. A downloaded copy uses the set's Managed Dictionary
Set ID and the same `.dic` file layout as an installed copy, and the synth
treats it like an installed set once downloaded. EDM's redistribution
requirements, such as license metadata in `set.ini`, do not apply to it.

A downloaded copy's `set.ini` needs only these fields:

```ini
[set]
id = <ID from the rules in Managed Dictionary Set identity and metadata>
name = <repository name, followed by /<folder path> for a sub-folder set>
source_url = <repository URL>
source_revision = <full commit SHA, if known>
source_version = <release tag, only if the copy came from one>
```

`id`, `name`, and `source_url` are required. `source_revision` and
`source_version` are optional. A downloaded copy isn't redistributed, so its
`set.ini` has no `attribution`, `license`, or `license_url`. A download of
`/archive/HEAD.zip` has no release tag, so it has no `source_version`. GitHub
stores the full commit SHA as the zip file's comment, and also in the name of
the archive's top folder, `<repo>-<SHA>/`. A synth records the comment as
`source_revision` when it is 40 lowercase hex digits.

A synth's reader applies these rules only to its own downloaded copies, which it
keeps in its own folder rather than finding through `contract.ini`. A set that a
provider ships still needs every field listed in
[Managed Dictionary Set identity and metadata](#managed-dictionary-set-identity-and-metadata),
and a provider set that lacks one is still ignored. Where a synth shows
`source_version` after a set's name, as in `Managed — <name> (<source_version>)`,
it shows a copy without one by name alone, for example
`Managed — AltIBMTTSDictionaries/IBMTTS 6.7`. It shows no empty parentheses,
and no SHA in place of the version.

These rules and the ID rules change nothing that a provider ships or that a
version 1 consumer reads from a provider, so they stay within contract
version 1.

When an installed provider and a synth's own download both supply the same
set ID, the synth shows one row for that set and uses the installed
provider's copy. The two copies are the same dataset, so stacking both would
apply it twice. See
[ADR 0001](../adr/0001-one-row-per-set-id-provider-copy-wins.md).

Consumers are expected to apply a change to the Personal Dictionary Overlay
without the user restarting NVDA or the synth, after EDM's **OK** writes it.

Whether a newly discovered set starts turned on is each consumer's choice:

- The Eloquence driver turns a provider's set on the first time it discovers
  the set's ID, for each language that has no Managed Dictionary Set turned on
  yet, and remembers that the ID has been seen so that turning it off sticks.
- A consumer whose engine carries its own dictionary may leave sets off, or
  skip a set for a language its own dictionary already covers. OpenEVV starts
  with no set chosen and never applies `github.eigencrow.ibmtts-dictionaries`
  to US English, because its built-in US English dictionary began as that set
  and has been corrected since.

EDM never calls into a synth to apply a change or turn a set on. The one call it
makes is the optional preview method described under [Preview](#preview). Driver
settings, temp-file merge mechanics, change detection, host commands, and language-fallback
implementation belong in each consumer repository, not here.

### Eloquence migration backup path

When the Eloquence driver migrates Old Eloquence Dictionary Files, it writes
one backup copy to:

```text
<active NVDA configuration>/
  eciDictionaries/
    legacy/
      eloquence/
```

Eloquence writes this folder once and never modifies it afterwards. It lives
in the configuration rather than in the Eloquence add-on folder because NVDA
replaces an add-on's folder on every update (see
[ADR 0002](../adr/0002-legacy-backup-in-nvda-configuration.md)). EDM only
reads this location; it
never writes, modifies, or deletes the old files. The consumer repository owns
creation of the backup and the removal of legacy loading behavior.

## Bundled content, licensing, and refresh

The v1 package bundles only
`github.eigencrow.ibmtts-dictionaries`, sourced from
`eigencrow/IBMTTSDictionaries` under `CC0-1.0`.

`github.mohamed00.alt-ibmtts-dictionaries`, sourced from
`mohamed00/AltIBMTTSDictionaries`, has no license grant and is not bundled.
Licensing fails closed: public repository visibility is not redistribution
permission. The permission task
[#10](https://github.com/akj/EloquenceDictionaryManager/issues/10) was closed as
out of scope for v1, so this set is ineligible until an explicit license or
auditable rights-holder permission covers its existing content and
contributions. It is not a pending v1 dependency.

The policy resolved in
[ticket #6](https://github.com/akj/EloquenceDictionaryManager/issues/6) is:

- project-produced dictionary data defaults to `CC0-1.0`, separately from the
  add-on software license;
- contributors explicitly confirm they control their contribution and apply
  CC0 to it;
- third-party sets require auditable rights to copy, modify, package, and
  redistribute, including commercial use;
- CC0 is preferred; `CC-BY-4.0` is acceptable when attribution is required;
  NC, ND, SA, and bespoke terms are avoided for new sets;
- source, attribution, license/permission evidence, notices, version, and
  revision stay with each set; and
- missing, unknown, incompatible, or unverifiable permission blocks that set
  from release.

Commercial use must remain allowed. See
[Licensing managed dictionary sets](../research/dictionary-set-licensing.md) for
the evidence and policy rationale.

Bundled content is refreshed only by a pinned maintainer-run workflow:

1. A source lock records the upstream release tag and exact commit SHA.
2. A maintainer explicitly runs the fetch tool.
3. The tool fetches that revision, validates licensing and dictionary format,
   normalizes filenames, generates `set.ini`, and updates vendored content.
4. Generated files are committed and reviewed as an ordinary diff.
5. Normal builds are offline and deterministic; CI verifies content against
   the lock.

This is not a git-submodule, runtime-download, or ordinary-build download flow.
New upstream releases never auto-merge or auto-publish. An EDM release may
legitimately retain an older pinned source version. Because a provider's copy
takes precedence over a synth's download of the same set, EDM aims to publish
a refresh for each upstream release tag, so the curators' tags set the pace at
which their corrections reach users.

## Western-language scope

V1 supports exactly ten Western ECI voice codes:

| Voice code | Encoding |
| --- | --- |
| `enu` | CP1252 |
| `eng` | CP1252 |
| `esp` | CP1252 |
| `esm` | CP1252 |
| `fra` | CP1252 |
| `frc` | CP1252 |
| `deu` | CP1252 |
| `ita` | CP1252 |
| `ptb` | CP1252 |
| `fin` | CP1252 |

The editor's language list contains exactly these ten codes. Encoding is a
per-language property, even though every v1 language maps to CP1252. There is no
global CP1252 gate.

`chs`, `jpn`, and `kor` never appear in the editor, including as disabled
choices. Users of an Asian Eloquence voice can still benefit from English
personal entries through the driver's existing `chs`→`enu` fallback; EDM adds
no UI special case.

Asian dictionary editing and validation are non-goals. The gate for future work
is to prove that `eciLoadDict` can populate `eciMainDictExt` against a real Asian
engine build. Asian support would also require language-specific encodings,
part-of-speech handling, and different slot rules.

## Entry editor

The editor design was approved through the runnable
[`prototype/entry-editor-ux`](https://github.com/akj/EloquenceDictionaryManager/tree/prototype/entry-editor-ux)
branch in
[ticket #7](https://github.com/akj/EloquenceDictionaryManager/issues/7). It is
the UX reference. Current NVDA source remains the implementation reference; see
[NVDA editor UX and speech APIs](../research/nvda-editor-ux-and-speech-apis.md).

### Placement and working-copy contract

EDM adds a standalone, resizable `SettingsDialog` under NVDA menu →
Preferences → **Eloquence &dictionaries...**, beside NVDA's speech dictionary
editors. It also exposes an initially unassigned, rebindable input gesture. EDM
does not add an NVDA Settings category.

The dialog edits a working copy. **OK** validates and commits it to the Personal
Dictionary Overlay; **Cancel** discards every change made since opening,
including imports. Managed files remain read-only.

### Effective-entry list

The editor presents one virtual merged list with columns:

```text
Word | Pronunciation | Type | Source
```

Above the list, a **Managed set** choice selects which read-only Managed
Dictionary Set to compose into the view, with a **None (personal entries
only)** choice. This viewing choice is not persisted: each time the editor
opens, it defaults to the first Managed Dictionary Set by display name, or to
the personal-entries-only view when no Managed Dictionary Set is available. It
does not select an edit or save target; all changes remain changes to the
Personal Dictionary Overlay. It is not an active-set setting, and does not
change the Managed Dictionary Set used by any synth.

The text filter matches word prefixes and pronunciation substrings,
case-insensitively, with exact word matches ordered first. A separate **Show**
filter has **All**, **Personal**, **Overrides**, and **Managed** choices. Source
values are `Managed — <name> (<version>)`, `Personal`, and `Personal — overrides
<name>`.

The list shows what a consumer will load, under the cross-type rule in
[Dictionary architecture and precedence](#dictionary-architecture-and-precedence).
A personal root entry overrides the viewed set's main entries for the same word,
compared without case, as well as its root entry. Those main entries are not
listed, and the personal root entry's Source is `Personal — overrides <name>`.
Within the viewed set, or within the overlay, a main entry and a root entry for
the same word are both listed.

Editing a managed row is **Customize**: copy it into the overlay, then edit the
copy. Removing an override restores the managed default immediately and without
a separate confirmation; the row changes back to Managed under focus. When a
personal root entry hid only the set's main entries, those entries are listed
again and focus moves to the first of them. Removing
a personal-only entry deletes it from the working copy. Managed entries cannot
be deleted in v1 because the overlay has no tombstones.

An editor action group contains:

- **Import...**
- **Export...**
- **Import from old Eloquence dictionary files...**
- **Remove all personal entries for <language>**

The label names the currently viewed language and updates as the user
switches languages. **Remove all personal entries for <language>** is
language-scoped: it removes Personal Dictionary Overlay entries only for that
language. Personal entries for other languages and managed entries are
unaffected.

Per-row **Add**, **Edit**/**Customize**, and **Remove** actions remain separate.

### Entry sub-dialog

The modal sub-dialog contains:

- **Word** and **Pronunciation** fields;
- a **Type** radio group: **Exact word**, **Word root**, or
  **Abbreviation**; the type is disabled while editing or customizing;
- tab-reachable, read-only **Rules** guidance that changes with the type; and
- **Play current** and **Play new** buttons.

There is no comment field because `.dic` has no comment representation.

### Validation

Validation is strict, slot-aware, and performed before an entry enters the
working copy. Failures show a specific message and return focus to the invalid
field. Characters that cannot encode in the selected language's code page are
rejected loudly and are never stripped.

The minimum validation contract is:

- every entry is one nonempty key and value; tab, newline, and NUL are forbidden
  inside either field;
- a key is at most 128 bytes and a value at most 512 bytes, measured after
  encoding in the language's code page. These limits were agreed with the
  Eloquence add-on
  ([fastfinge/eloquence_64#173](https://github.com/fastfinge/eloquence_64/issues/173)),
  which rejects a whole file that has an entry over them;
- **Exact word** keys contain no whitespace and do not end in punctuation;
  values may contain ordinary text and three kinds of backquote code (see
  below);
- every backquote in a value must begin one of these three forms. Any other
  backquote makes the entry invalid (`annotationInvalid`), whatever the slot:
  - an SPR, `` `[ `` … `]`, at the start of the value or after whitespace;
  - an emphasis code, `` `00 `` or one digit `` `0 `` to `` `4 `` not followed
    by another digit, at the start of the value or after whitespace, and
    followed by whitespace; and
  - a spelling-mode code, `` `ts0 `` to `` `ts3 ``, not followed by another
    digit. Text may follow it directly, as in `` `ts1AOK `ts0 ``. A `` `ts0 ``
    must start the value or follow whitespace, because the engines ignore one
    glued to the text before it. A value that turns spelling on with
    `` `ts1 `` to `` `ts3 `` must turn it off with `` `ts0 `` before it ends
    (`spellingModeUnclosed`).

  The engine accepts any annotation in an Exact word value, and it reads a
  dictionary value's codes whatever a synth's backquote voice tags setting
  says: that setting changes only spoken text. The ECI manual describes a pause
  code that can last about 330 seconds, voice, volume and speed codes that stay
  in effect until changed or the program restarts, and spelling modes that stay
  on until `` `ts0 `` (`tts.txt` in fastfinge/eloquence_64, lines 376, 3336–3338,
  3446–3447 and 3500–3510). Engine tests confirm it for dictionary values: a
  volume code turns the rest of the sentence down and can carry into the next
  utterance, a pause code pauses, and a spelling mode left on spells what
  follows (see `docs/research/eci-dic-format.md` §9d). A shared
  `.edm-dict` file, a downloaded set, or a bad upstream commit could carry such a
  code, so the definition of a valid entry allows only the three forms. Every
  Exact word value in the bundled set, in the Community and Alt repositories,
  and in OpenEVV's built-in dictionary uses only these forms, in these
  positions;
- **Word root** keys contain letters, with apostrophes allowed inside the word
  (`j'accuse`), and are stored lowercase; values are one bare word or one bare
  SPR, with no annotation or multi-word value. The manual allows letters only,
  but the IBMTTSDictionaries curators report that apostrophe keys work, and the
  bundled set relies on them;
- **Abbreviation** keys contain letters, meaningful periods, and permitted
  internal apostrophes, plus a hyphen straight after a period that joins two
  words (`Dipl.-Ing.`); values contain plain words separated by spaces or
  hyphens, with no SPR or annotation. The manual allows no hyphen, but the
  German curators and engine tests on #173 confirm that these keys work. English
  (`enu` and `eng`) keys can also join two words with a hyphen, slash, or
  ampersand (`AT&T`, `km/h`), because the engine loads them; they carry the
  warning below. Other hyphens, slashes, and ampersands stay invalid; and
- SPR structure is validated. Per-language phoneme-symbol legality (for
  example, rejecting lowercase `j` in American English) is planned follow-up
  work using the manual's SPR tables
  ([#64](https://github.com/akj/EloquenceDictionaryManager/issues/64)), and
  does not block consumer integration.

A **warning** marks an entry that is valid and loads, but that the engine never
applies. The one warning today is an English (`enu` or `eng`) abbreviation key
with a hyphen, slash, or ampersand: engine tests show US English loads it but
never matches it, and
British English is assumed to behave the same. The entry dialog does not save a
warned entry: it shows the warning as it would a failure and returns focus to
the Word field. Import and migration skip a warned entry as they skip an
invalid one.

The exact user-facing validation catalog and Rules copy are frozen by the
prototype walkthrough; the engine rationale and edge cases are in
[ECI `.dic` format](../research/eci-dic-format.md).

Synths that validate dictionary files share this definition of a valid entry
through the format document and a shared set of example valid, invalid, and
warned lines that each validator tests against
([#63](https://github.com/akj/EloquenceDictionaryManager/issues/63)). They do not import EDM's code at
runtime, because EDM may be disabled or removed.

### Preview

Preview bypasses NVDA's speech-dictionary and symbol-processing pipeline.
**Play current** runs only through synths that read EDM's managed sets and
personal overlay: Eloquence (`eloquence`) and OpenEVV (`openevv`). When one of
them is active, it calls `speech.cancelSpeech()` and then
`synthDriverHandler.getSynth().speak()` with the word.

**Play new** works in this order:

1. It checks the Word and Pronunciation as **OK** would. If the pronunciation
   is invalid, it announces the validation message and speaks nothing.
   Problems with the Word are ignored, so a pronunciation can be heard before
   the Word is typed.
2. If the loaded synth driver has the preview method below, Play new cancels
   speech and calls it with the pronunciation.
3. Otherwise, with Eloquence or OpenEVV, it reads the synth's backquote voice
   tags setting: `backquoteVoiceTags` on Eloquence and `voiceTags` on OpenEVV.
   Both default to off, and while it is off the synth turns every backquote in
   spoken text into a space, so a phonetic string would be read as letters. If
   the pronunciation contains a backquote and the setting is off, Play new
   announces "To hear pronunciations with phonetic strings or other backquote
   codes, turn on backquote voice tags in Voice settings." and speaks nothing.
   Otherwise it cancels speech and calls `speak()` with the pronunciation.
4. With any other synth, it announces the explanation below.

EDM reads a synth's voice tags setting and never changes it. The
pronunciation's codes are previewed correctly with the setting off only when
the synth implements the preview method.

Both Play buttons stay enabled and in the tab order when no synth can preview.
Activating one then speaks the translatable explanation: "Preview unavailable:
switch to Eloquence or OpenEVV to hear pronunciations." It does not cancel
speech first. EDM never previews through a synth that does not read its entries
or implement the preview method, and never switches synths temporarily.

#### Preview method

The preview method is an optional part of directory contract version 1. A
synth that supports it lets EDM preview a pronunciation exactly as a dictionary
entry would say it, without the user turning on backquote voice tags. No synth
implements it yet.

- The synth driver object has a callable attribute `previewEciPronunciation`
  that takes one `str`: a pronunciation exactly as it appears after the tab in
  a dictionary file. EDM detects it with `getattr`. Having the method is the
  opt-in, whatever the synth's name.
- The synth speaks the pronunciation once, in the current voice and language,
  through its normal text pipeline, so its crash-word filters still run.
- Any add-on can call the method, so the synth applies the same rule as
  [Validation](#validation) itself: SPRs, emphasis codes and spelling-mode
  codes in the permitted positions are honoured for this utterance only, and
  every other backquote becomes a space.
- Afterwards, no setting or engine state has changed, and spelling mode is off.

## Overlay export and import

Personal-entry sharing, backup, and transfer use the same `.edm-dict` artifact,
as resolved in
[ticket #12](https://github.com/akj/EloquenceDictionaryManager/issues/12).

### Export

**Export...** acts on the working copy and includes personal entries only. A
scope dialog chooses **shown language only** (default) or **all languages**, then
opens a save picker in Documents. The default filename is:

```text
Eloquence dictionary entries - <language | all languages> - <YYYY-MM-DD>.edm-dict
```

The artifact is a zip with the `.edm-dict` extension. It contains canonical
lowercase `<voice-code><slot>.dic` files verbatim in CP1252 plus `manifest.ini`.
The manifest records a format ID, major-only integer format version, exporting
EDM version, and language list. There is no sender-notes or attribution field.

### Import

The open picker filters to `*.edm-dict` with an All-files fallback. After file
selection, one dialog chooses **Add to your entries** (merge, default) or
**Replace your entries for the languages in the file**. Import changes the
working copy, where rows are immediately reviewable.

In merge mode, a collision is the same language, slot, and word. One summary
prompt reports the total and chooses **Keep my entries** (default) or
**Use the imported entries** for every collision. Nonconflicting entries always
merge.

Entries that fail the editor validation catalog are skipped and counted in the
completion summary. An unreadable artifact, an invalid `.edm-dict`, or an
artifact declaring a newer format version is rejected whole with a clear
message. **Cancel** on the editor undoes the complete import.

## Migration import tool

The migration tool recovers likely hand edits from old blended dictionary files
without copying upstream content into the overlay. Its behavior is resolved in
[ticket #13](https://github.com/akj/EloquenceDictionaryManager/issues/13).

### Historical-union artifact

At build time, the pinned offline refresh workflow builds hashed line sets for
each `(language, slot)` from every historical revision of both upstream
repositories. After source bytes are decoded and a line is parsed, normalization
omits the line ending, removes leading tabs from the value, and case-folds root
keys alone; all other key and value text remains exact. The resulting
`key<TAB>value` text is re-encoded as UTF-8 before SHA-256 hashing, as recorded by
`normalized_line_encoding = utf-8` in `historicalUnion.lock.ini`. Hashes are not
redistribution, so the artifact includes the full
AltIBMTTSDictionaries history even though that set is not bundled.

The old Eloquence repository never tracked `.dic` files; the two upstream git
histories are therefore the complete known provenance of non-hand-edited lines.
An unmatched exotic-source line simply appears as a candidate.

The scanner decodes CP1252, tolerates CRLF and LF plus both filename-case
conventions, handles duplicate upstream keys, and preserves candidate values
byte-for-byte. It scans only the ten Western voice codes and ignores other
files.

### Discovery and entry points

The tool auto-scans the backup at `eciDictionaries/legacy/eloquence/` in the
active NVDA configuration first, then the live `synthDrivers/eloquence/`
directory inside an installed Eloquence add-on that predates the migration.
A folder picker covers portable and unusual setups.

The dedicated editor button is always present and opens the picker if nothing
is auto-detected. When the editor opens with undismissed old files present, it
offers one non-startup nudge:

> Old dictionary files from before this add-on were found. Review and import
> your hand edits now?

The choices are **Yes**, **Later**, and **Don't ask again**. EDM stores dismissal
state in its configuration. The tool never modifies or deletes old files.

### Review and commit

One modal NVDA-style checkable list shows:

```text
Word | Pronunciation | Type | Language | Status
```

Likely hand edits are pre-checked and can be unchecked. Invalid candidates are
shown unchecked and uncheckable, with the validation reason in **Status**; users
can recover them by manually adding a corrected entry. The review list has no
per-row Play or Edit action; refinement belongs in the main editor.

Entries identical to existing personal entries are omitted, making repeated
imports idempotent. A candidate with the same language, slot, and word but a
different personal value is listed unchecked with status "Differs from your
current entry for this word"; checking it replaces the current entry. Migration
conflicts are resolved in this list, not by the `.edm-dict` summary prompt.

**Import checked entries** adds candidates to the editor working copy. They are
immediately visible for refinement; **OK** commits them and **Cancel** undoes the
whole migration import.

### Limitation: deletions are not migrated

Absence from the historical union proves nothing, and the overlay has no
tombstones. A deletion that a user made to old managed content is not migrated;
that managed entry returns.

## Secure screens and availability

All EDM GUI surfaces are unavailable on secure screens. Menu items are not
created when `globalVars.appArgs.secure`, following NVDA's speech-dictionary
precedent. Every script and handler is also decorated with
`@blockAction.when(blockAction.Context.SECURE_MODE)`, which supplies NVDA's
standard translatable secure-context message.

The gate covers the entry editor, Set Details, overlay import/export, migration
tool, file and folder pickers, and the rebindable gesture. There is no read-only
secure-screen surface.

No surface is gated on Eloquence being installed, enabled, or active. EDM owns
files and supports prepare-ahead and migration workflows independently of the
consumer. Only Play changes behavior based on the active synth, as specified
above.

## Packaging, store, and maintainership

EDM is built on `nvaccess/AddonTemplate` as resolved in
[ticket #2](https://github.com/akj/EloquenceDictionaryManager/issues/2).
Manifest compatibility is fixed for v1:

```text
minimumNVDAVersion = 2026.1.0
lastTestedNVDAVersion = 2026.3.0
```

The display name and frozen manifest/store ID are those in
[ticket #9](https://github.com/akj/EloquenceDictionaryManager/issues/9):
**Eloquence Dictionary Manager** and `eloquenceDictionaryManager`.
The store description leads with the bundled dictionary content users receive.

Submission uses the `nvaccess/addon-datastore` **Add-on registration** issue
form. The package must pass its compatibility, metadata, SHA256, and VirusTotal
checks and include source, software-license, and bundled-content provenance.
The approved-submitter process can add lead time. Follow the concrete checklist
in [add-on template and store research](../research/addon-template-and-store.md).

Andrew is the v1 manifest author and store publisher and publishes and maintains
v1 under his account. Bundled credits identify the upstream curators. A post-v1
handoff to one or more dictionary curators is welcome if they choose it, but no
handoff is promised or required.

## Internationalization

Every Python module with user-visible strings calls
`addonHandler.initTranslation()`. Strings use `_()`, `ngettext`, or `pgettext`
as appropriate, and every string is immediately preceded by a
`# Translators:` comment. Manifest metadata and documentation use the template's
gettext pipeline.

Each set's English `name` is a gettext message ID extracted into the provider's
catalog with a translator comment. Consumers read it through the provider add-on
object's translation instance even while that provider is disabled. Proper names,
URLs, SPDX identifiers, and verbatim legal notices remain exact; surrounding UI
labels are translatable.

## Non-goals

- A manager-owned active-set selector or any EDM settings panel.
- Editing managed set files or maintaining per-user forks of whole sets.
- Managed-entry deletion or overlay tombstones.
- Asian dictionary editing, validation, import, or packaging before the named
  engine experiment succeeds.
- Integration with NVDA speech pronunciation dictionaries, which operate at a
  different text-substitution layer.
- New dictionary formats, non-ECI synths, or runtime downloads by EDM. Synths
  may still download sets for the user, as described under the directory
  contract.
- Specifying an individual synth driver's settings UI, merge implementation,
  host protocol, legacy backup writer, or removal plan beyond this contract.
