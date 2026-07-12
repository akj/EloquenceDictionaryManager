# The ECI `.dic` on-disk dictionary format

Research for issue #4. Feeds three downstream decisions: editor input validation,
the Asian-language-support decision, and the migration import tool. Those three are
called out explicitly in the closing subsections.

The format is defined by the **frozen IBM ECI / ViaVoice Text-to-Speech engine**
(`ECI.DLL`). The authoritative primary source is the *IBM Text-to-Speech* API
reference manual, version 6.4.0, which ships in-tree as
`C:\Users\andrew\code\eloquence_64\tts.txt` (and identically as
`…/scratchpad/NVDA-IBMTTS-Driver/apiReference/tts.txt`). Line numbers below refer to
that file. Everything else — filenames, encodings-in-practice, which slots people
actually populate — is convention layered on top by the two driver/dictionary
communities.

Throughout, claims are tagged **[engine]** (enforced by `ECI.DLL`, per the manual or
its API), or **[convention]** (a practice observed in driver code or data files, which
the engine does not enforce). Confidence is flagged where evidence is thin.

---

## ⚠ Open questions / things to verify before building on them

1. **No Asian `.dic` files exist to inspect.** None of the three surveyed repos
   (AltIBMTTSDictionaries, IBMTTSDictionaries, NVDA-IBMTTS-Driver) contain a single
   `chs`/`jpn`/`kor` dictionary file. Every claim about Asian on-disk format below is
   derived from the **manual + engine API only**, never verified against real bytes.
   The community has evidently never shipped Asian dictionaries. (Verified: `find`
   across all repos + `eloquence_64` for any `chs|jpn|kor|chinese|japan|korea` `.dic`
   returned nothing.)

2. **Asian slots may not be loadable from a file at all in practice.** The Asian slot
   (`eciMainDictExt`) requires a per-entry *part of speech* argument that only exists
   in the `…A` API family (`eciUpdateDictA`), and there is **no documented on-disk
   representation of the part-of-speech field** for a file loaded via `eciLoadDict`.
   davidacm's driver explicitly declines to load it: *"fixme: doesn't even check for
   mainext. Character sets make that somewhat strange."*
   (`NVDA-IBMTTS-Driver/addon/synthDrivers/_ibmeci.py:604`). Whether `eciLoadDict` can
   populate `eciMainDictExt` from a plain key⇥value file — and if so, what POS it
   assumes — is **unverified and probably untestable without an Asian engine build**.

3. **Duplicate-key resolution (first-wins vs last-wins) is inferred, not documented.**
   The manual documents `eciUpdateDict` as *last-write-wins by key* (lines 3072–3076),
   and duplicate keys demonstrably exist in shipped files (23 in `ENURoot.dic`), but the
   manual never states how `eciLoadDict` resolves duplicates within one file. Last-wins
   is the strong inference; see §7. **Confidence: medium.** For our own merge/dedup we
   control this ourselves and need not rely on engine behaviour.

4. **CP1252 vs ISO-8859-1 is a toolchain choice, not byte-provable.** The high bytes
   observed in Western files (0xE0, 0xEA, 0xFC …) are identical in CP1252 and
   ISO-8859-1, so the bytes alone don't prove which. The engine manual only says
   "ANSI" (line 587). We treat Western content as **CP1252** because the existing
   Eloquence updater commits to it explicitly (`eloquence.py` writes
   `encoding="cp1252"`), which is the Windows/NVDA convention. Bytes in the
   0x80–0x9F range would disambiguate but none appear in the sampled files.

5. **Line endings are inconsistent even within one repo** (some files CRLF, some bare
   LF — see §3). The engine tolerates both; our tools must too.

---

## Sources consulted

| Source | Path | Role |
|---|---|---|
| IBM TTS 6.4.0 API manual | `eloquence_64/tts.txt` | **Authoritative** engine spec |
| Eloquence host (64-bit synth's 32-bit helper) | `eloquence_64/host_eloquence32.py` | How this repo's synth loads dicts today |
| Eloquence updater (being removed) | `eloquence_64/addon/synthDrivers/eloquence.py` | The CP1252 download/merge flow the spec kills |
| davidacm IBMTTS driver | `scratchpad/NVDA-IBMTTS-Driver/addon/synthDrivers/_ibmeci.py` | Independent ECI dict loader |
| Alt IBM TTS Dictionaries | `scratchpad/AltIBMTTSDictionaries/*.dic` + `doc/` | Real data + convention docs |
| IBM TTS Dictionaries | `scratchpad/IBMTTSDictionaries/*.dic` | Real data (`ENU`+`DEU`, main/root/abbr slots) |

---

## 1. The dictionary model: a "set" of four volumes (slots)

**[engine]** A *dictionary set* is a single in-memory object (`ECIDictHand`, created by
`eciNewDict`) that holds up to **four volumes**, each a separate key→translation store
with different rules (tts.txt:335–340):

| Slot | `ECIDictVolume` enum value | Purpose |
|---|---|---|
| Main | `eciMainDict` = **0** | Arbitrary keys → arbitrary translations (multi-word, annotations, URLs, acronyms) |
| Roots | `eciRootDict` = **1** | Single lowercase word → single word / SPR; matches all inflections of the root |
| Abbreviations | `eciAbbvDict` = **2** | Letter/period sequences → spelled-out words; period-aware |
| Main Extension | `eciMainDictExt` = **3** | **Asian only** (Chinese/Japanese/Korean); DBCS keys, requires part-of-speech |

The numeric enum ordering (main=0, root=1, abbr=2, ext=3) is authoritative from
davidacm's transcription of `eci.h`
(`_ibmeci.py:58`: `eciMainDict, eciRootDict, eciAbbvDict, eciMainDictExt = range(4)`)
and is confirmed by both drivers loading main/root/abbr at literal indices 0/1/2 —
which works in the field, so the enum can't be otherwise.
(Note: the manual's *prose* at tts.txt:337–340 lists Extension second, but that's
narrative order, not the enum value.)

**How a set is built and activated [engine, via driver code]:**
`eciNewDict(handle)` → one or more `eciLoadDict(handle, dictHandle, slotIndex, path)`
calls (one per slot, each loading a whole file) → `eciSetDict(handle, dictHandle)` to
make it the active set. (`host_eloquence32.py:288–301`; `_ibmeci.py:608–615`;
manual `eciLoadDict` tts.txt:1968–1999, `eciNewDict` :2093–2114, `eciSetDict`
:2545–2565.) **One file per slot** — `eciLoadDict` takes exactly one filename, which
is why the spec's per-key precedence must be realised by *merging* two layers into one
temp file rather than loading both (spec §"Resolution and merge").

The `.dic` path itself is passed to the engine encoded as **`mbcs`** (the OS ANSI code
page) in both drivers (`host_eloquence32.py:298`, `_ibmeci.py:610–614`) — that's the
*path* encoding; the *content* encoding is handled inside `ECI.DLL` (see §4).

---

## 2. Per-slot file naming convention

**[convention]** The engine's `eciLoadDict` takes any path; the `<code><slot>.dic`
naming is purely a driver convention for discovery. Both drivers use the same scheme:

```
<languagecode><slot>.dic
```

where `<slot>` ∈ {`main`, `root`, `abbr`} and `<languagecode>` is the 3-letter ECI
code. Concretely, the loaders build these names:

- davidacm: `langid+"main.dic"`, `langid+"root.dic"`, `langid+"abbr.dic"`
  (`_ibmeci.py:609–614`).
- Eloquence host: `f"{code}main.dic"`, `f"{code}root.dic"`, `f"{code}abbr.dic"`, with
  generic `main.dic`/`root.dic`/`abbr.dic` as an `enu`/`eng` fallback
  (`host_eloquence32.py:146–155`).

Language codes in use (`host_eloquence32.py:120–134`, `_ibmeci.py:110+`):
`enu` (US English), `eng` (British), `esp` (Castilian), `esm` (LatAm Spanish),
`fra`/`frc` (French/Canadian), `deu`, `ita`, `ptb`, `fin`, plus Asian `chs`/`jpn`/`kor`.

**Filename-case is inconsistent across repos** and matters on case-sensitive
filesystems / exact-match discovery:
- AltIBMTTSDictionaries: all-lowercase — `enumain.dic`, `enuroot.dic`, `espmain.dic`.
- IBMTTSDictionaries: mixed — `ENUmain.dic`, **`ENURoot.dic`** (capital R),
  `ENUabbr.dic`, `DEUmain.dic`, `DEURoot.dic`, `DEUabbr.dic`.

The observed slot filenames in the wild: only **main**, **root**, **abbr** ever
appear. There is **no `*ext.dic` file anywhere**, consistent with §1/open-question #2.

Aside **[convention]**: on Linux, IBM's own layout renames these to `main.dct` /
`root.dct` under `/var/opt/IBM/ibmtts/dict/<lang>/`
(`AltIBMTTSDictionaries/README.md`). Irrelevant to the NVDA add-on but confirms the
same content is engine-portable across OSes.

---

## 3. Line format: separator, values, whitespace

**[engine]** *"A dictionary file consists of ASCII text with one dictionary entry per
line. Each input line contains a key and a translation value, separated by a **tab
character**."* (tts.txt:341–342, restated for `eciLoadDict` at :1992–1994.)

Verified against bytes in every sampled file — the separator is a single **`0x09`
(TAB)**, e.g. `ni<TAB>` `00 ni`, `SNES<TAB>ess en ee ess`. `cat -A` on `espmain.dic`
shows `ni^I`00 ni^M$` — `^I` = tab, `^M$` = CRLF.

Concrete facts:

- **Key/value separator: exactly one TAB.** **[engine]** Not spaces. (Spaces *within*
  the key are illegal — see §5.)
- **Values may contain spaces** **[engine, well-attested]** — main/abbr translations
  are frequently multi-word: `Airbnb<TAB>Air bea en bea`, `WWII<TAB>world war two`,
  `AWSA<TAB>American Woman Suffrage `0 Association` (tts.txt:386). The value runs from
  the byte after the tab to the line terminator.
- **Trailing whitespace:** no evidence the engine trims it, and none appears in the
  data. Treat trailing spaces in a value as significant (they could be an authoring
  mistake). **Confidence: medium** — not documented either way.
- **Line terminator: CRLF *or* bare LF; inconsistent per file.** **[convention]**
  Authoritative byte counts (Python `count(b'\r\n')` vs bare `\n`):
  - `AltIBMTTSDictionaries/*.dic`, `IBMTTSDictionaries/ENU*.dic`: **CRLF**, all lines.
  - `IBMTTSDictionaries/DEUmain.dic`, `DEURoot.dic`, `DEUabbr.dic`: **bare LF**, all
    lines (confirmed on the committed blob via `git show HEAD:DEUmain.dic`, so it's not
    a checkout artifact).
  - All sampled files **end with a trailing newline**.
  The engine consumes both (these files are used daily on Windows and Linux). Our
  reader must accept both; our writer should pick one and normalise.
- **All content is single-byte ASCII/CP1252 per line** for Western files; every line
  is `key⇥value` (0 lines without a tab, across the files checked).

---

## 4. Encoding, per language family

**[engine]** ECI has no encoding metadata in the file — it interprets the raw bytes
using **the ANSI/"system-dependent" code page currently selected for that engine
instance** (`ECIInputText` = *"a NULL terminated string using a system-dependent
character set (currently ANSI for all platforms)"*, tts.txt:585–588). The `…A` API
note makes the rule explicit: *"The buffer contents should be in the same code page
currently selected for this speech synthesis engine instance. If a Unicode code page
is active, [they] should be in wide-character (Unicode) format with a 16-bit
terminator. Otherwise … an 8-bit, NULL-terminated C string."* (tts.txt:3124–3127).

In practice the active code page is fixed by the **language dialect** the engine was
created with (`eciNewEx(languageId)`), and each dialect has a default codeset:

| Family | Codes | Default codeset (from dialect) | Windows code page | Evidence |
|---|---|---|---|---|
| Western European | enu, eng, esp, esm, fra, frc, deu, ita, ptb, fin | **CP1252 / Latin-1** | 1252 | Bytes below; `eloquence.py` writes `cp1252` |
| Mandarin (Simplified) | chs | **GBK** | 936 | `l6.0 …with GBK support` tts.txt:3221; dialect `0x00060000` |
| Japanese | jpn | **Shift-JIS** | 932 | `l8.0 …with Shift-JIS support` tts.txt:3231; `0x00080000` |
| Korean | kor | **UHC** (superset of EUC-KR) | 949 | `StandardKoreanUHC = StandardKorean` `_ibmeci.py:94`; `0x000A0000` |
| (Taiwanese Mandarin) | — not in Eloquence LANGS | Big5 | 950 | `l6.1 …Big5` tts.txt:3224 |
| (any, "UCS" variants) | dialect `…0x0800` | **UTF-16** | — | tts.txt:3223/3232; `_ibmeci.py:82,91,95` |

**Western = CP1252 — verified against bytes:**
- `IBMTTSDictionaries/ENUmain.dic` key `t<0xEA>te-<0xE0>-t<0xEA>tes` = **tête-à-têtes**
  (0xEA=ê, 0xE0=à in CP1252).
- `IBMTTSDictionaries/DEUmain.dic` value `D<0xFC>sburg` (0xFC=ü); German umlauts
  throughout → German uses the same CP1252 as English, **not** a separate codeset.

Caveat repeated from open-question #4: these bytes are equal in CP1252 and ISO-8859-1;
the CP1252 label comes from the toolchain, not the bytes.

**Asian = the dialect's DBCS code page (GBK / Shift-JIS / UHC) — unverified against any
real file** (none exist). The current Eloquence `LANGS` table maps `chs`→`0x00060000`,
`jpn`→`0x00080000`, `kor`→`0x000A0000` (`host_eloquence32.py:131–133`), i.e. the
GBK/SJIS/UHC defaults, **not** the UCS/UTF-16 variants. So if Asian `.dic` files ever
existed they would be DBCS (GBK/SJIS/UHC) byte streams, **not** UTF-8 or UTF-16 — and
CP1252 validation would be actively wrong for them (it would reject or mangle legal
double-byte sequences).

**The removed Eloquence updater** (`eloquence.py:457–640`) is a cautionary tale: it
reads downloaded dicts trying `["utf-8","cp1252","iso-8859-1","cp437"]`, then **writes
strictly `cp1252`, stripping accents that don't fit** ("some accents may have been
stripped for compatibility", :640). That lossy normalisation is exactly what the new
editor must *not* do; it also confirms CP1252 was the assumed Western on-disk encoding.

---

## 5. Key semantics and translation validity, per slot

**[engine]** Each slot enforces different rules. This is the meat of editor validation.

### Main dictionary (`eciMainDict`, slot 0)
- **Case-sensitive** (tts.txt:362–363). Example: key `WHO`→"World Health Organization"
  does **not** affect lowercase `who`. This is why data files list capitalised
  variants as **separate entries** — e.g. `espmain.dic` carries both `no` and `No`,
  `ni`/`Ni`, `muy`/`Muy` (each its own line).
- **Key:** *"any characters other than white space, except that the final character of
  the key may not be a punctuation symbol."* (tts.txt:353–355). So digits, `@ # $ % &
  * +`, apostrophes, quotes, parens, brackets, internal punctuation are all legal;
  **no whitespace anywhere in the key**; **last char not punctuation**
  (tts.txt:367–379). Real keys: `jeb@notreal.org`, `Win32`, `486DX`, `billets-doux`.
- **Translation:** *"Anything that is legal input to the text-to-speech engine,
  including white space, punctuation, SPRs, and annotations."* (tts.txt:376–378). This
  is the **only** Western slot where SPRs and `` ` `` annotations are legal in the
  value.
- Purpose (tts.txt:356–361): multi-word expansions, keys needing annotations/SPRs,
  URLs/emails, keys with digits/symbols, acronyms.

### Roots dictionary (`eciRootDict`, slot 1)
- **NOT case-sensitive** (tts.txt:426–428) — a lowercase root still matches
  sentence-initial capitals. This is why root files are written all-lowercase.
- **Key:** *a single word in ordinary spelling, all lowercase letters.* **NO** digits,
  punctuation, whitespace, or other non-letter characters (tts.txt:440–445).
- **Translation:** a single word in ordinary spelling **OR** a valid SPR. **NO**
  digits, punctuation, non-letter chars, whitespace, **tags, or annotations**
  (tts.txt:442–447). I.e. in roots, the value may be a bare respelled word or a
  `` `[…] `` SPR, but **not** a `` `0 ``-style annotation and **not** multi-word.
- Root-matching: entering `figure` covers `figures/figuring/figured/refigure`
  (tts.txt:449). Cannot override function words like *the*/*to* (tts.txt:433–434);
  may misfire on unknown roots (tts.txt:429–432).
- Real data: `ribcage<TAB>`[r1Ib.2keJ]`, `encrypt<TAB>`[.0XG.1krIpt]` — key lowercase
  letters only, value a single SPR. This slot is where the bulk lives (`ENURoot.dic` =
  67 629 entries).

### Abbreviations dictionary (`eciAbbvDict`, slot 2)
- **Case-sensitive** (tts.txt:461–462).
- **Key:** sequences of letters, optionally separated by/ending with **periods**
  (`x.x.x.`, `xxx.`, `xxx`); upper/lower letters; **internal** apostrophes (not first/
  last). **NO** digits, non-letter symbols, whitespace, or punctuation other than
  periods (tts.txt:488–504).
- **Trailing-period semantics** **[engine]** (tts.txt:463–480): key `inv` matches both
  `inv.` and `inv`; key `sid.` matches **only** `sid.` (not bare `sid`). So a trailing
  `.` in the key is meaningful, not decoration.
- **Translation:** one or more ordinary-spelling words separated by whitespace or
  hyphen; upper/lower case. **NO** digits, punctuation, **SPRs, tags, or annotations**
  (tts.txt:499–504). Real data: `WWII<TAB>world war two`, `Ltjg<TAB>lieutenant
  junior-grade` — plain words only, no backquotes.
- **[convention]** AltIBMTTSDictionaries **refuses abbreviation entries entirely**
  ("For various reasons, including the limitations of the abbreviation dictionary
  format … abbreviation dictionary entries are not accepted for any language" —
  `README.md`). IBMTTSDictionaries *does* ship `ENUabbr.dic`. So abbr usage is real but
  contested.

### Main Extension dictionary (`eciMainDictExt`, slot 3) — Asian
See §8.

### Invalid entries fail *soft* [engine]
*"An invalid key or translation will cause the dictionary look-up to fail, and the
pronunciation of the word will be generated by the normal pronunciation rules."*
(tts.txt:342–344); an invalid SPR *"is spelled out character by character"*
(tts.txt:3793–3794). So a malformed line doesn't error the file load — it's silently
ignored at lookup time. This matters: **bad entries are invisible failures, not loud
ones**, which is the whole argument for validate-at-entry.

---

## 6. Comments and blank lines

**[engine + convention]** The format has **no comment syntax and no provision for blank
lines**. The manual defines a line as strictly `key⇥value` (tts.txt:341–342) with no
mention of comments; a blank or comment line has no tab and would simply be an "invalid
key" that fails lookup silently (§5).

Verified: across all sampled files there are **0 blank lines**, **0 lines lacking a
tab**, and **0 lines beginning with `#`, `;`, or `//`**. Nobody puts comments in these
files. `eciSaveDict` (the engine's own writer) emits pure `key⇥value` lines *"in no
particular order"* (tts.txt:2495–2497) — round-tripping through the engine would strip
anything else anyway.

Conclusion for our tools: **do not emit comments or blank lines**; if a comment feature
is ever wanted, it must live in a sidecar file, not the `.dic`.

---

## 7. Key matching & deduplication

**Case sensitivity** (from §5): main = case-sensitive, roots = case-**in**sensitive,
abbr = case-sensitive. **[engine]**

**Match scope** **[engine]**: lookup is **whole-token**, not substring. Main/abbr match
a whole word/token in the text; roots match a whole *root morpheme* (with inflectional
expansion), explicitly *not* arbitrary substrings — `prego` won't fire inside
`pregoness` (tts.txt:429–432). No slot does substring replacement.

**Duplicate keys — resolution:**
- Duplicate keys **do occur in shipped files**: `ENURoot.dic` has **23** keys appearing
  twice (e.g. `acesulfame` at lines 22759 and 64104, with *different* SPRs
  `.0sx.` vs `.0sX.`), `ENUmain.dic` has 2, `enuroot.dic` has 1. So the format does not
  forbid them and real curators haven't de-duplicated.
- **Resolution is last-wins — inferred, not documented for `eciLoadDict`.** The engine's
  key store is last-write-wins: `eciUpdateDict` *"is updated if the key already exists"*
  (tts.txt:3072–3075). If `eciLoadDict` applies entries top-to-bottom (the natural
  implementation), the **last** occurrence in the file wins. The manual never states
  this for file loading, and entries are stored "in no particular order"
  (tts.txt:2496), so a lookup can't be predicted from file order after load.
  **Confidence: medium.**

**Implication for our merge/dedup:** don't depend on engine duplicate-handling.
Deduplicate **before** writing the merged temp file — one entry per (slot, key), with
the overlay entry beating the managed entry (per spec) — so the file we hand `ECI.DLL`
has no duplicates and the outcome is deterministic regardless of the engine's internal
order. For the case-insensitive **roots** slot, dedup keys **case-insensitively**
(lowercased); for case-sensitive **main/abbr**, dedup on the exact key.

---

## 8. Asian-language differences

**[engine]** Asian support routes through a **different slot and a different API
family**, and drops one slot entirely:

- **Extra slot:** `eciMainDictExt` (slot 3) is *"used for Asian languages and provides
  support for Chinese, Japanese, and Korean"* (tts.txt:394–396). Western languages
  don't use it.
- **Roots slot is unavailable for Chinese:** *"For Chinese, Roots Dictionary
  (eciRootDict) functionality is not supported."* (tts.txt:350).
- **Different API family — the `…A` functions:** Asian maintenance must use
  `eciUpdateDictA`, `eciDictFindFirstA`, `eciDictFindNextA`, `eciDictLookupA`
  (tts.txt:347–349, 407–408).
- **Every extension entry carries a Part of Speech (POS)** — a grammatical category
  that is a *fifth argument* to `eciUpdateDictA`, absent from the Western API
  (tts.txt:405–416, 3081–3111). Valid POS values:
  - Chinese: `eciUndefinedPOS`, `eciMingCi`
  - Japanese: `eciUndefinedPOS`, `eciFutsuuMeishi`, `eciKoyuuMeishi`, `eciSahenMeishi`
  - Korean: `eciUndefinedPOS`
- **Translation rules differ:** e.g. Japanese translations are Katakana *Yomi* strings;
  *"Any other SBCS/DBCS characters except the accent mark (^) will cause an error"*
  (tts.txt:403–404). The worked example creates `eciNewEx(eciStandardJapanese)` then
  `eciUpdateDictA(…, eciMainDictExt, key, value, eciKoyuuMeishi)` (tts.txt:4822–4826).
- **Encoding:** DBCS in the dialect's code page (GBK / Shift-JIS / UHC), or UTF-16 for
  the "UCS" dialect variants — see §4.

**The gap that matters most:** there is a POS field per entry with **no documented
on-disk column** — `eciUpdateDictA` takes POS as a function argument, and the file
format documented for `eciLoadDict` is just `key⇥value` with no third field. So it is
unclear (open-question #2) whether an Asian dictionary can even be represented as a
loadable `.dic`, or whether the engine assumes `eciUndefinedPOS` for file-loaded
extension entries. Combined with **zero real Asian `.dic` files in existence**, the
on-disk Asian format is effectively **unspecified in practice**. davidacm's driver
skips the extension slot for exactly this reason (`_ibmeci.py:604`).

---

## 9. Annotation & SPR (phoneme) syntax in translation values

**[engine]** Two related notations appear in translation values, both introduced by a
**backquote `` ` ``** (0x60). Only the **main** slot (and Asian **extension**) permit
them; **roots** permit *only* a bare SPR; **abbr** permits neither (§5).

### 9a. Symbolic Phonetic Representations (SPR) — `` `[ … ] ``
An SPR is *"enclosed in square brackets `[]` and preceded by a backquote"*
(tts.txt:3786–3787). Grammar (tts.txt:3789–3822):
- **Syllable boundary:** `.` (period) starts a new syllable. Optional in most
  languages; **significant in German**.
- **Stress digit:** `1` primary, `2` secondary, `0` none — placed inside the syllable,
  left of the vowel. A multi-syllable SPR **must** carry at least one `1` or the whole
  SPR is invalid and spelled out.
- **Sound symbols:** per-language phoneme letters, **case-sensitive** (`e` ≠ `E`).
  Two-character symbols must be wrapped in **single quotes**, e.g. German
  `heim` → `` `[h'aj'm] `` (tts.txt:3820–3821).
- Invalid SPR ⇒ spelled out character-by-character, never errors the load
  (tts.txt:3793–3794, 3822).

Real examples: `ribcage<TAB>`[r1Ib.2keJ]`, `postfix<TAB>`[.1post.2fIks]`,
`WYSIWYG<TAB>`[1wI0zi0wIg]`, `UConn<TAB>`[2yu1kan]` (tts.txt:388–390, data files).
The full per-language phoneme inventories ("SPR Tables") occupy tts.txt:3837+
(American English vowels/diphthongs/consonants, then each other language) — the editor
can't cheaply validate symbol-legality without embedding those tables; realistically it
should validate *structure* (balanced `` `[ … ] ``, at least one primary stress) and
leave symbol legality to the soft-fail engine.

### 9b. Emphasis / prosody annotations — `` `0 `` … `` `4 ``, `` `l ``, `` `v ``, …
An annotation is *"a backquote (`) followed immediately by a string of characters"* and
*"must be preceded by at least one unit of white space"* (tts.txt:3184–3186). The ones
that actually appear in dictionary values are the **word-emphasis** codes
(tts.txt:3382–3388):

| Code | Meaning |
|---|---|
| `` `00 `` | Reduced emphasis (function-word level) |
| `` `0 `` | No emphasis |
| `` `1 `` | Normal emphasis (content-word default) |
| `` `2 `` | Added emphasis |
| `` `3 `` | Heavy emphasis |
| `` `4 `` | Very heavy emphasis |

These explain the Spanish `espmain.dic` data directly: `no<TAB>`1 no` (force normal
emphasis on the function word "no" — this is the very entry that surfaced in the
originating issue #133), `ni<TAB>`00 ni` (reduce it), and English
`mbox<TAB>em `0 box` (de-emphasise "box"). Many other annotations exist
(`` `l `` language, `` `v ``/`` `vs ``/`` `vb `` voice/rate/pitch, `` `a* `` tone,
pauses, filters — tts.txt:3172–3520) and are all *legal* in a main translation since
"anything that is legal input" is allowed, but emphasis codes are what curators use.

**Slot rule restated:** SPR + annotations ⇒ **main** only (Western). Roots ⇒ **bare SPR
or bare word** only (no `` `N `` emphasis, no multi-word). Abbr ⇒ **plain words** only.

---

## 10. Size / length limits and forbidden characters

- **No documented length limit** on keys or translations. **[engine]** A search of the
  manual for maximum/limit/length near dictionary terms finds only
  `ECI_VOICE_NAME_LENGTH` (voice names, tts.txt:2724) — unrelated. Real entries are
  short (words/short phrases); treat "no hard limit" as the working assumption but keep
  entries reasonable.
- **Forbidden by construction:**
  - **Tab** cannot appear inside a key or value (it *is* the separator). **[engine]**
  - **Newline** cannot appear inside an entry (one entry per line). **[engine]**
  - **Whitespace in a key:** forbidden in main and abbr; forbidden entirely in roots
    (roots keys are letters only). **[engine]**
  - **Key final character** must not be punctuation (main); abbr keys allow only
    letters/periods/internal-apostrophe; roots keys allow only letters. **[engine]**
  - **NUL (0x00):** the engine takes NULL-terminated C strings (tts.txt:585–588), so an
    embedded NUL truncates — never allow it. **[engine, by API]**
  - **Bytes outside the active code page:** for Western that's non-CP1252 bytes; the
    old updater's response was to strip them (lossy). **[convention]**

---

## Implications for **editor input validation**

1. **Slot-aware validation is mandatory** — the three Western slots have *different*
   legal keys and values (§5). The editor must know which slot an entry targets and
   apply that slot's rules:
   - *Main:* key = no whitespace, last char not punctuation; value = anything (may hold
     SPR/annotations).
   - *Roots:* key = lowercase letters only; value = a single bare word **or** one
     `` `[…] `` SPR — reject annotations, digits, punctuation, whitespace, multi-word.
   - *Abbr:* key = letters + optional periods + internal apostrophe; value = plain
     word(s) separated by space/hyphen — reject digits/punctuation/SPR/annotations.
2. **Enforce the mechanical invariants**: exactly one TAB separator; no tab/newline/NUL
   inside key or value; single-line entries. Offer to normalise line endings on save.
3. **Encoding gate = CP1252 for Western** (§4). Reject or clearly warn on characters
   outside CP1252 rather than silently stripping accents like the old updater did — the
   whole point of the editor (spec §Entry editor) is to stop Notepad-style corruption.
4. **Validate SPR structure, not full symbol legality** (§9a): require balanced
   `` `[ … ] ``, at least one primary-stress `1` for multi-syllable, single-quote
   wrapping of 2-char symbols; leave exact phoneme-symbol legality to the engine (it
   soft-fails to spell-out). Embedding the per-language SPR tables (tts.txt:3837+) would
   let you go further but is a large data lift.
5. **Remember failures are silent** (§5): an invalid entry is not rejected at load — it
   just never fires. So validation at *entry* time is the only place the user learns
   they made a mistake; make it strict and specific.
6. **Case-fold expectations:** for roots, warn if the user types uppercase or expects
   case-sensitivity (roots are case-insensitive); for main/abbr, remind that `Word` and
   `word` are distinct (the reason data files duplicate capitalised variants).

## Implications for the **Asian-language decision**

1. **Western-first is strongly supported by the evidence.** There are **zero** Asian
   `.dic` files in the entire community corpus (open-question #1), the extension slot
   needs a per-entry POS field with **no documented on-disk column** (§8,
   open-question #2), and the one independent driver that could load them **chooses not
   to** (`_ibmeci.py:604`). Shipping Western-only first (spec open-question #2) is the
   low-risk path.
2. **CP1252 validation is affirmatively wrong for Asian** (§4): Asian content would be
   GBK/Shift-JIS/UHC double-byte (or UTF-16 for UCS dialects). A CP1252 gate would
   reject legal Asian entries. So the editor's encoding rule must be **per-language**,
   not global — do not hardcode CP1252 across all languages if Asian is ever added.
3. **If Asian is pursued later**, it's a genuinely different feature, not a config
   tweak: different slot (`eciMainDictExt`), different API (`…A` family), a mandatory
   POS selector in the UI, loss of the roots slot for Chinese, and — first — an
   experiment to determine whether `eciLoadDict` can even populate the extension slot
   from a file, or whether entries must be pushed one-by-one via `eciUpdateDictA`. Until
   that experiment succeeds against a real Asian engine build, treat Asian on-disk
   format as **unknown**.

## Implications for the **import tool**

1. **Read tolerantly, dedup deterministically.** Accept both CRLF and bare-LF files
   (§3) and both filename-case conventions (§2). When reconstructing "which lines are
   hand edits vs upstream", compare **normalised** lines (canonical line ending, exact
   bytes of key+TAB+value) so a CRLF-vs-LF difference doesn't masquerade as a hand edit.
2. **Decode as CP1252 for Western** (§4). The historical blended files were written
   CP1252 by the very updater being retired (`eloquence.py`), so CP1252 is the right
   decode; don't guess-chain encodings the way that updater did.
3. **Dedup rules must match the slot** (§7): case-insensitive keys for **root** files,
   case-sensitive for **main**/**abbr**. When diffing a user's old file against the
   union of upstream historical versions (spec §Migration import tool), a root entry
   differing only in key-case is *not* a new hand edit.
4. **Duplicate keys are normal in source data** (§7) — the diff logic must handle a key
   appearing twice in an upstream file (23× in `ENURoot.dic`) without treating the
   second as a user edit.
5. **Slot inference from filename** is reliable (`<code>{main,root,abbr}.dic`, §2);
   there is no in-file slot marker, so the tool keys everything off the filename. There
   is no `*ext.dic` to worry about.
6. **Preserve, don't normalise, the value payload.** SPRs and `` `N `` annotations
   (§9) are load-bearing; the import tool should carry a hand-edited value through
   byte-for-byte (modulo line ending), never "cleaning" it — the old updater's accent
   stripping is precisely the data loss the migration is meant to recover from.
