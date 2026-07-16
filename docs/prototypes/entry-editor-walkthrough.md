# PROTOTYPE — Entry editor UX walkthrough

> **Throwaway design artifact** for wayfinder ticket
> [#7 Entry editor UX](https://github.com/akj/EloquenceDictionaryManager/issues/7).
> This is a proposal to react to, not an implementation-ready spec. It lives on a
> prototype branch, out of `main`; validated decisions get folded into
> `docs/specs/dictionaries-addon.md` when the ticket resolves.

Medium call: **textual walkthrough**, not a runnable wx dialog. The product is a
speech-first, keyboard-first NVDA dialog; what needs judging is focus order, spoken
feedback, and flow — none of which a wx dialog running outside NVDA can demonstrate.

Every quoted label and message below is a user-visible string: in implementation each
is wrapped `_( "..." )` with a `# Translators:` comment. Names use the add-on's working
name; final naming is ticket [#9](https://github.com/akj/EloquenceDictionaryManager/issues/9).
Western languages only, per the pending Asian-stance ticket
[#8](https://github.com/akj/EloquenceDictionaryManager/issues/8).

## Inputs honored (closed decisions)

- The manager has **no runtime active-set selector** — each synth chooses its set. The
  editor may *browse* a managed set, but that choice activates nothing.
  ([Contract v1](https://github.com/akj/EloquenceDictionaryManager/issues/5))
- Browse provenance renders as `Managed — <name> (<source_version>)`; full SHAs and
  legal text live on a read-only Set Details surface.
  ([Set metadata](https://github.com/akj/EloquenceDictionaryManager/issues/6))
- The editor writes **only** the Personal Dictionary Overlay
  (`<config>/eciDictionaries/personal/<code><slot>.dic`); managed files are never edited.
- Validation is slot-aware and strict at entry time, because the engine fails
  *silently* on bad entries (research: [ECI .dic format](../research/eci-dic-format.md)).
- UI idiom is NVDA's speech-dictionary dialog family
  (research: [NVDA editor UX](../research/nvda-editor-ux-and-speech-apis.md)).

---

## 1. Entry points

- **NVDA menu → Preferences → "Eloquence &dictionaries..."** — opens the editor.
  Preferences (not Tools) is NVDA's own precedent for dictionary editors; the item sits
  as a sibling of "Speech dictionaries". Ellipsis because a menu item opens a dialog.
- **An unassigned gesture** — a global-plugin script, category "Eloquence
  Dictionaries", description "Opens the personal pronunciation dictionary editor",
  rebindable via Input Gestures.
- **No NVDA Settings panel in v1.** Since the contract moved set activation to the
  synths, the manager has nothing left to configure — its whole UI is this editor plus
  Set Details. (Design point 8.)
- Secure-screen gating of the menu item is ticket
  [#11](https://github.com/akj/EloquenceDictionaryManager/issues/11)'s call, not made here.

## 2. The editor dialog

`SettingsDialog` subclass (standalone, resizeable, single-instance), title
**"Eloquence Dictionary Entries"**. Inherited keyboard behavior: **Enter = OK from
anywhere including the list**, Escape = Cancel. Working-copy semantics: all edits act
on an in-memory copy of the overlay; **OK writes the overlay files, Cancel discards
everything** — this is the safety net that lets Remove act without confirmation.

Tab order:

1. **"&Language:"** — `wx.Choice` of Western ECI languages, e.g. "Spanish (Castilian)".
   Lists every language with content in the viewed set or the overlay, plus all known
   Western codes (so you can add entries for a language with no managed content yet).
   Defaults to the active Eloquence voice's language when Eloquence is the current
   synth, else US English.
2. **"Managed &set:"** — `wx.Choice`: one item per bundled set by metadata `name`, plus
   "None (personal entries only)". *Viewing* only. A static line directly below reads:
   **"Viewing only — the set your synthesizer uses is chosen in the synthesizer's
   settings."** Defaults to the only bundled set when there is exactly one.
3. **"Set &details"** — button, opens a read-only modal: set name, version, source URL,
   exact revision, attribution, license (the Set Details surface from the metadata
   decision).
4. **"&Filter by:"** — text field, live filtering as you type. Matches from the start
   of the word, plus anywhere in the pronunciation; exact word matches sort first.
   (Substring-anywhere over 67k roots makes short filters useless — "no" would match
   every "…no…".)
5. **"Sho&w:"** — `wx.Choice`: "All entries" / "Personal only" / "Personal overrides
   only" / "Managed only". Finds your handful of entries inside tens of thousands of
   managed ones.
6. **"Dictionary &entries"** — virtual `AutoWidthColumnListCtrl` (report,
   single-select; virtual because ENURoot alone is 67 629 rows). Columns:
   **Word | Pronunciation | Type | Source**. Sorted by word (case-insensitive), then
   type. Focus lands here when the dialog opens.
   - **Type** column values: "Exact word" / "Word root" / "Abbreviation".
   - **Source** column values: `Managed — <name> (<version>)` / `Personal` /
     `Personal — overrides <name>`.
   - The list shows the **effective** view: managed entries of the viewed set, overlay
     entries, and overlay-over-managed collisions collapsed into one row marked as an
     override. Duplicate keys *within* a managed file are collapsed last-wins (matching
     the engine's inferred behavior).
7. **"&Add"**, **"&Edit"**, **"&Remove"**, *(spacer)*, **"Remove all personal
   entries"** — button row, speech-dict style (no ellipses on in-dialog list buttons).
   - **Edit** enabled with exactly one row selected. On a managed row it opens as
     *Customize* (§3, scenario A).
   - **Remove** enabled only when the selected row has a personal component (pure
     personal or override). Managed rows: disabled — NVDA speaks "Remove button
     unavailable". Managed entries cannot be deleted in v1; the contract has no
     tombstone mechanism, only per-key override (design point 3).
   - **"Remove all personal entries"** clears the overlay for the shown language, after
     a Yes/No confirmation (No default): *"Remove all 12 of your personal entries for
     Spanish (Castilian)? Managed entries are not affected."*
8. **OK / Cancel** (separated by a rule).

After every Add/Edit/Remove, focus returns to the list with the affected row selected
and focused — the speech-dict idiom, and the mechanism by which the user *hears* what
changed (see scenarios).

## 3. The entry sub-dialog

Modal `wx.Dialog`. Title: **"Add Dictionary Entry"** / **"Edit Dictionary Entry"** /
**"Customize Dictionary Entry"** (editing a managed entry). Controls:

1. **"&Word"** — single-line text. Initial focus.
2. **"&Pronunciation"** — single-line text.
3. **"&Type"** — `wx.RadioBox`, vertical: **"Exact word"** / **"Word root (matches all
   word forms)"** / **"Abbreviation"**. Default "Exact word" when adding. **Disabled
   when editing or customizing** — an entry's identity is its word + type; changing
   type is remove-and-re-add.
4. **"Rule&s"** — read-only multiline text, tab-reachable so screen-reader users arrow
   through it. Content swaps with the Type selection (full copy in §6).
5. **"Play c&urrent"** — speaks the Word field through the active synth *directly*
   (`getSynth().speak()`, after `cancelSpeech()`), bypassing NVDA's own speech
   dictionaries: you hear how the engine says it **today**, under its currently loaded
   dictionaries.
6. **"Play &new"** — speaks the Pronunciation field the same way: since a main-slot
   value is by definition legal engine input (words, SPRs, annotations), speaking it
   verbatim *is* the candidate pronunciation. No save, no reload — this is the whole
   edit-listen-iterate loop, inside the dialog.
   - When the active synth is not Eloquence, both Play buttons are **disabled** and a
     static line above them reads: **"Preview requires Eloquence to be the active
     synthesizer."** (Buttons stay in the tab order; NVDA announces them
     "unavailable".)
   - Direct synth calls skip NVDA's speech manager: no braille echo, and preview speaks
     even in speech-off mode. Accepted for a one-shot preview.
7. **OK / Cancel** (separated). All validation runs in `onOk` (§5); an error shows a
   message box, keeps the dialog open, and refocuses the offending field.

No Comment field: the `.dic` format has no comment syntax — anything we invented would
need a sidecar file the contract doesn't define. Deferred (design point 4).

---

## 4. Scenarios (with what NVDA speaks)

Notation: `NVDA: "…"` is the spoken feedback. Keystrokes are literal.

### A. Fix the stressed Spanish "no" (the issue-#133 story)

Marta reads Spanish with Eloquence and is fed up with the emphasized "no".

1. NVDA menu → Preferences → "Eloquence dictionaries...".
   `NVDA: "Eloquence Dictionary Entries dialog. Dictionary entries list. a; … "`
   (language already "Spanish (Castilian)" — her active voice; focus in the list on the
   first row).
2. `Shift+Tab` ×2 to the filter. `NVDA: "Filter by: edit"` — types `no`.
3. `Tab` ×2 back to the list; exact match sorts first:
   `NVDA: "no; \`1 no; Exact word; Managed — Alternative IBM TTS Dictionaries (2025.03)"`
4. `Alt+E` (Edit). Because the row is managed, the dialog opens as:
   `NVDA: "Customize Dictionary Entry dialog. Word edit, no"` — Word and Pronunciation
   are pre-filled (`no` / `` `1 no ``); Type shows "Exact word", disabled.
5. She tabs to **Play new**, presses it: hears the stressed "no" (the current managed
   value). Tabs back, changes Pronunciation to `` `0 no ``, presses **Play new** again:
   hears it flat. Good.
6. `Enter` (OK). Back in the editor, focus on the same row:
   `NVDA: "no; \`0 no; Exact word; Personal — overrides Alternative IBM TTS Dictionaries"`
7. `Enter` (OK) — overlay written. Nothing was downloaded, no managed file touched;
   every other Spanish entry still comes from the managed set.

*(AltIBMTTSDictionaries is used illustratively; bundling it is gated on
[#10](https://github.com/akj/EloquenceDictionaryManager/issues/10).)*

### B. Add a word root, guided out of a mistake

Sam wants "quinoa" and its forms said as "keen-wah".

1. In the editor, `Alt+A`. `NVDA: "Add Dictionary Entry dialog. Word edit"`.
2. Types `Quinoa`, tabs, types `keenwah`, tabs to Type, arrows to
   `NVDA: "Word root, matches all word forms, radio button checked"`.
3. Tabs once more: `NVDA: "Rules read-only edit. Matches a word and all of its forms —
   'figure' also covers figures, figured, figuring — ignoring capitalization. …"`
4. **Play new** → hears "keenwah". `Enter`.
5. The uppercase Q is not an error: roots are case-insensitive, so the entry is stored
   lowercase (the Rules text says so; no scolding dialog — design point 5). Back in the
   list: `NVDA: "quinoa; keenwah; Word root; Personal"`.

Contrast — Sam later tries to add `Win32` as a word root:

6. On OK: `NVDA: "Dictionary Entry Error dialog. Word roots can contain only letters.
   'Win32' cannot be a word root — for words with digits or symbols, use an Exact word
   entry. OK button"`. Dismisses; focus returns to the Word field; he flips Type to
   "Exact word" and OK succeeds.

### C. An abbreviation, and what the trailing period means

1. `Alt+A`, Word `approx.`, Pronunciation `approximately`, Type → "Abbreviation".
2. Rules text (read in passing):
   `NVDA: "… A trailing period is meaningful: 'approx.' matches only 'approx.' — write
   'approx' without the period to match both 'approx' and 'approx.'. …"`
3. Realizing she wants both forms covered, she removes the period from the Word field.
   OK. `NVDA: "approx; approximately; Abbreviation; Personal"`.

### D. Restore a managed default

Marta decides the override from scenario A should go.

1. Filter to the row: `NVDA: "no; \`0 no; Exact word; Personal — overrides …"`.
2. `Alt+R` (Remove). No confirmation — Cancel-discards-everything is the safety net.
   The override is deleted from the working copy and the managed entry *resurfaces in
   the same row*, which keeps focus:
   `NVDA: "no; \`1 no; Exact word; Managed — Alternative IBM TTS Dictionaries (2025.03)"`
   Hearing the row flip from Personal back to Managed *is* the confirmation.
3. On a pure personal row, Remove deletes the row and focus moves to the next one.

### E. Preview with the wrong synthesizer

Alex runs eSpeak day-to-day and opens the entry dialog:

- Tab reaches: `NVDA: "Preview requires Eloquence to be the active synthesizer."`,
  then `NVDA: "Play current button unavailable"`.
- Everything else works — entries can be added, validated, and saved; they'll be heard
  next time Eloquence is active.

---

## 5. Validation catalog (all in `onOk`, strict, specific)

Order: emptiness → mechanical invariants → slot rules → encoding → SPR structure →
duplicates. First failure wins; message box title **"Dictionary Entry Error"**
(`wx.OK | wx.ICON_WARNING`), then refocus the offending field. Messages name the
offending text — the engine would otherwise drop the entry *silently*.

| Check | Message (proposed exact string) |
|---|---|
| Empty word | "A word is required." |
| Empty pronunciation | "A pronunciation is required." |
| Exact word: contains whitespace | "The word cannot contain spaces. Dictionary entries match one word at a time." |
| Exact word: ends in punctuation | "The word cannot end with punctuation (\"win!\" ends with \"!\")." |
| Word root: non-letters in key | "Word roots can contain only letters. \"Win32\" cannot be a word root — for words with digits or symbols, use an Exact word entry." |
| Word root: multi-word / annotated value | "A word root pronunciation must be a single word or one phonetic string (\`[...]) — no spaces, digits, or emphasis codes." |
| Abbreviation: illegal key chars | "An abbreviation can contain only letters and periods, with apostrophes inside the word — for example \"Dr.\" or \"e.g.\"." |
| Abbreviation: illegal value | "An abbreviation expansion must be plain words separated by spaces or hyphens — no digits, punctuation, or phonetic symbols." |
| Any: character outside CP1252 | "The character \"ē\" cannot be saved in an Eloquence dictionary (Western encoding only)." — never silently stripped; that's the corruption this editor exists to stop. |
| SPR: unbalanced | "The phonetic string is not closed — expected \"]\" after \"\`[\"." |
| SPR: no primary stress | "A phonetic string with more than one syllable needs a primary stress marker \"1\", for example \`[.1kwi.0nwa]." |
| Duplicate personal key (same type; case-insensitive for roots) | Yes/No: "You already have a personal entry for \"no\" (Exact word). Replace it?" |

Not validated: exact phoneme-symbol legality inside an SPR (would mean embedding the
per-language SPR tables; the engine soft-fails a bad symbol to spell-out, which the
Play-new button makes audible anyway). Tabs/newlines can't be typed into single-line
fields; pasted control characters are stripped before validation. Saved files are
written CP1252 with CRLF line endings, deduplicated, no comments or blank lines.

## 6. Slot guidance — the "Rules" copy

- **Exact word**: "Matches the word exactly as written — capitalization counts, so
  \"NASA\" and \"nasa\" are separate entries. The word cannot contain spaces or end
  with punctuation. The pronunciation may be words, phonetic strings like
  \`[.1kwi.0nwa], or emphasis codes \`0 (flat) through \`4 (strongest)."
- **Word root**: "Matches a word and all of its forms — \"figure\" also covers
  figures, figured, figuring — ignoring capitalization. Roots are stored in lowercase
  and can contain only letters. The pronunciation must be a single word or one
  phonetic string (\`[...])."
- **Abbreviation**: "Matches an abbreviation written with letters and periods —
  capitalization counts. A trailing period is meaningful: \"approx.\" matches only
  \"approx.\", while \"approx\" matches both \"approx\" and \"approx.\". The expansion
  must be plain words."

## 7. Design points to react to

1. **One merged list** (Type as a column, effective view across slots) rather than
   three per-slot lists or a slot switcher — "what affects this word?" in one place.
2. **Remove doubles as restore-default** on override rows, no confirmation, feedback
   via the row flipping back to Managed under focus. Alternative: a dynamically
   relabeled "Restore default" button.
3. **Managed entries cannot be deleted** in v1 — the contract merge is
   override-per-key with no tombstone. A user who wants a managed entry *gone* can only
   override it with something else. Acceptable, or does the contract need tombstones?
4. **No comment field** — the on-disk format has none; a sidecar is deferred.
5. **Root keys silently lowercased** (rules text explains) instead of erroring.
6. **Play current / Play new** button pair; both disabled with an explanatory static
   line when Eloquence isn't the active synth.
7. **Fixed field labels** ("Word" / "Pronunciation") across all three types, vs.
   type-dependent labels ("Abbreviation" / "Expansion").
8. **No NVDA Settings panel at all** — with set activation moved to the synths, the
   manager's entire surface is this dialog (+ Set Details). Menu item under
   Preferences only.
9. **Filter matches word-prefix** (plus pronunciation substring), exact match first —
   tuned for 67k-row sets.
10. **Slot names for humans**: "Exact word" / "Word root" / "Abbreviation" (the manual
    says main/roots/abbreviation). Naming reactions welcome.

## 8. Out of scope here

- Overlay export/backup placement (map fog — likely a button in this dialog later).
- Import tool flow (separate fog patch).
- How the running Eloquence driver notices a saved overlay change (driver-side;
  the in-dialog preview deliberately doesn't depend on it).
- Secure-screen behavior (ticket #11), Asian languages (ticket #8), final names
  (ticket #9).
