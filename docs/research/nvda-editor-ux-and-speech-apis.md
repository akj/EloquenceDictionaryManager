# NVDA editor UX idioms and speech APIs (for the entry editor + settings)

Research for issue #3. Studies the local NVDA source at `../nvda` (read-only) to answer:
what UX idioms does NVDA use for dictionary-like editors and settings, and what APIs can
an add-on use to speak preview text through the active synth?

All citations are `source/...` paths plus the symbol; line numbers are omitted because the
tree moves. Verified against the NVDA checkout present on 2026-07-12.

---

## Flags: surprises and idioms in flux (read first)

- **The speech-dictionary dialogs were recently refactored and are the closest analogue to
  our editor.** `DictionaryDialog` now subclasses `SettingsDialog` (a *resizeable standalone*
  dialog), not a category panel, and entry data moved into a typed model:
  `speechDictHandler.types` (`EntryType`, `DictionaryType`, `SpeechDict`, `SpeechDictEntry`)
  with `speechDictHandler.definitions._getDictionaryDefinition(...)`. If we mirror this code,
  copy the *current* shape, not older tutorials. (`source/gui/speechDict.py`.)

- **Two different editor idioms coexist in NVDA and we must choose deliberately.** The speech
  dictionary uses a **modal add/edit sub-dialog** (list + Add/Edit/Remove buttons →
  `DictionaryEntryDialog`). The symbol-pronunciation dialog uses **edit-in-place** (a
  virtual list on top, and "Change selected symbol" controls below that write back live as
  you move the selection). They are genuinely different UX, not two spellings of one pattern.
  (`source/gui/speechDict.py` `DictionaryDialog`; `source/gui/settingsDialogs.py`
  `SpeechSymbolsDialog`.)

- **GUI state persistence is new (2025) and used very narrowly.** NVDA only just wired up
  `wx.lib.agw.persist` (`source/gui/persistenceHandler.py`, `guiStateFile` in
  `source/gui/__init__.py` `initialize`). It currently persists only a couple of `wx.Choice`
  selections in the Remote dialogs. Dialog size, position, and list column widths are **not**
  generally persisted — the speech-dict dialog hardcodes its size and only preserves column
  widths *within a session*. Don't assume a framework will remember our window. (Details in
  the persistence section.)

- **`hasApplyButton=` is deprecated** in `SettingsDialog.__init__`; use
  `buttons={wx.OK, wx.CANCEL, ...}` instead. (`source/gui/settingsDialogs.py` `SettingsDialog`.)

- **Speaking text the normal way applies NVDA's *own* speech dictionaries and symbol
  processing.** `speech.speak()` runs every string through `processText()` →
  `speechDictHandler.processText()` before it reaches the synth
  (`source/speech/speech.py` `speak`, `processText`). For a faithful preview of what the
  *Eloquence engine* will say from a `.dic` entry, that extra layer is exactly what we do
  **not** want — call the synth driver directly to bypass it. See "Speaking preview text".

- **Preview only reflects our dictionaries if the active synth is Eloquence.** Our `.dic`
  entries affect the ECI engine only. If the user's active synth is something else, a preview
  through "the active synth" won't demonstrate the entry. This is a product decision to make
  explicit (preview disabled / warned when the active synth isn't Eloquence), not an API gap.

---

## 1. The pattern to copy for our dictionary-entry editor

Recommended: **mirror the speech-dictionary dialog** — a resizeable standalone dialog with a
report-style list and Add / Edit / Remove buttons, plus a modal entry sub-dialog. It is the
most NVDA-idiomatic match for "browse a list of entries, add/edit one at a time," and it is
fully keyboard-driven. Reference: `source/gui/speechDict.py`.

### 1a. The list-and-buttons container (`DictionaryDialog`)

`DictionaryDialog(SettingsDialog, metaclass=guiHelper.SIPABCMeta)` —
`source/gui/speechDict.py`:

- Subclasses `SettingsDialog` and is constructed `super().__init__(parent, resizeable=True)`,
  then `self.SetSize(576, 502)` and `self.CentreOnScreen()`. So it is a **standalone
  resizeable dialog**, opened on demand, not a page inside NVDA Settings.
- Builds its body in `makeSettings(self, settingsSizer)` (required override of
  `SettingsDialog`). It wraps the passed-in sizer:
  `sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)`.
- **The list** is a labeled `wx.ListCtrl` in report + single-select mode:
  `self.dictList = sHelper.addLabeledControl(_("&Dictionary entries"), wx.ListCtrl,
  style=wx.LC_REPORT | wx.LC_SINGLE_SEL)`. Columns are added with `AppendColumn(...)`
  (`_("Comment")`, `_("Pattern")`, `_("Replacement")`, `_("case")`, `_("Type")` with explicit
  pixel widths). Rows are `dictList.Append((...))` tuples.
- **The buttons** are grouped with `guiHelper.ButtonHelper(orientation=wx.HORIZONTAL)`; each
  `bHelper.addButton(parent=self, label=_("&Add"))` immediately `.Bind(wx.EVT_BUTTON, handler)`.
  Buttons: `_("&Add")`, `_("&Edit")`, `_("&Remove")`, then `bHelper.sizer.AddStretchSpacer()`,
  then `_("Remove all")`. The whole group is added with
  `sHelper.addItem(bHelper, flag=wx.EXPAND)`.
- **Focus handling.** `postInit(self)` sets `self.dictList.SetFocus()` (the list gets focus on
  open). After Add, the code deselects any prior selection, selects+focuses the new last row,
  and returns focus to the list (`onAddClick`). After Edit/Remove/Remove-all it also returns
  focus to the list. This "keep focus on the list and move the selection to the affected row"
  behavior is the idiom to copy for screen-reader usability.
- **Edit gating.** `onEditClick` no-ops unless exactly one row is selected
  (`GetSelectedItemCount() != 1`). `onRemoveClick` walks `GetFirstSelected()` /
  `GetNextSelected()` and deletes from both the list and the backing model.
- **Working copy + save-on-OK.** It edits a `tempSpeechDict` copy; `onOk` only writes back if
  `tempSpeechDict != speechDict`, then `speechDict.save()`. `onCancel`/`onOk` also toggle
  `globalVars.speechDictionaryProcessing`. We should adopt the same "edit a copy, commit on
  OK, discard on Cancel" contract.
- **Remove-all confirmation** uses `gui.messageBox(..., style=wx.YES | wx.NO | wx.NO_DEFAULT)`
  and deletes row-by-row deliberately "in order to avoid recreation of the columns eventually
  loosing their manually changed widths" — i.e. column widths are only session-stable, and
  clearing the list would reset them.
- The concrete dialogs are thin subclasses that supply title + backing dict:
  `DefaultDictionaryDialog`, `VoiceDictionaryDialog`, `TemporaryDictionaryDialog`, each calling
  `speechDictHandler.definitions._getDictionaryDefinition(DictionaryType.X)`.

### 1b. The modal entry sub-dialog (`DictionaryEntryDialog`)

`DictionaryEntryDialog(gui.contextHelp.ContextHelpMixin, wx.Dialog)` —
`source/gui/speechDict.py`. This is the shape to copy for editing one entry:

- Plain `wx.Dialog` (not a `SettingsDialog`). Title defaults to `_("Edit Dictionary Entry")`;
  the caller passes `_("Add Dictionary Entry")` when adding.
- Body built with `mainSizer = wx.BoxSizer(wx.VERTICAL)` +
  `sHelper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)`.
- **Fields**, each via `sHelper.addLabeledControl(labelText, wx.TextCtrl)`:
  - `_("&Pattern")` → `patternTextCtrl`
  - `_("&Replacement")` → `replacementTextCtrl`
  - `_("&Comment")` → `commentTextCtrl`
  - `_("Case &sensitive")` → a `wx.CheckBox` added with `sHelper.addItem(wx.CheckBox(...))`
  - `_("&Type")` → a `wx.RadioBox(self, label=typeText, choices=typeChoices,
    style=wx.RA_SPECIFY_ROWS)` (type as a radio group, not a dropdown). Choice labels come
    from `EntryType._displayStringLabels` in a fixed `TYPE_LABELS_ORDERING` tuple.
- **Dismiss buttons**: `sHelper.addDialogDismissButtons(wx.OK | wx.CANCEL, separated=True)`
  (`separated=True` draws a horizontal rule above OK/Cancel — the convention for anything that
  isn't a bare message dialog).
- Standard tail: `mainSizer.Add(sHelper.sizer, border=guiHelper.BORDER_FOR_DIALOGS,
  flag=wx.ALL)`, `mainSizer.Fit(self)`, `self.SetSizer(mainSizer)`, `self.CentreOnParent()`,
  then set initial control values and `self.patternTextCtrl.SetFocus()` (focus the first
  field).
- **Validation happens in `onOk(self, evt)`**, and this is directly transferable to our
  CP1252/annotation validation need:
  - Empty pattern → `gui.messageBox(_("A pattern is required."),
    _("Dictionary Entry Error"), wx.OK | wx.ICON_WARNING, self)`, refocus the field, `return`
    (do **not** `evt.Skip()`, which is what keeps the dialog open).
  - On success it constructs the model object and calls `evt.Skip()` to let the dialog close.
  - Regex validation is shown as the model pattern to imitate: try to build the entry, catch
    the error, show a message box with the specific error, refocus the offending field,
    `return`. We would swap in ECI `.dic` validation (tab structure, CP1252-encodability,
    phoneme/annotation syntax) in the same slot.

### 1c. The edit-in-place alternative (`SpeechSymbolsDialog`)

If we prefer no modal sub-dialog (edit fields live under the list, changes apply live), copy
`SpeechSymbolsDialog(SettingsDialog)` in `source/gui/settingsDialogs.py`:

- A `_("&Filter by:")` text field (`pgettext("speechSymbols", "&Filter by:")`) bound to
  `wx.EVT_TEXT` → live filter. Filtering is case-insensitive substring match over display
  name and replacement, preserving the current selection where possible (`filter`).
- A **virtual** list: `nvdaControls.AutoWidthColumnListCtrl(..., autoSizeColumn=2,
  itemTextCallable=self.getItemTextForList, style=wx.LC_REPORT | wx.LC_SINGLE_SEL |
  wx.LC_VIRTUAL)`. Virtual + `ItemCount` + a text callback is the idiom for **large** lists
  (thousands of rows) — directly relevant to us, since a merged managed+overlay dictionary can
  be large. `AutoWidthColumnListCtrl` auto-sizes one column to fill width.
- A grouped editor below the list built with
  `wx.StaticBoxSizer(wx.VERTICAL, self, label=_("Change selected symbol"))` wrapped in a
  `guiHelper.BoxSizerHelper` and added via `sHelper.addItem(...)`: a `_("&Replacement")`
  text field, a `_("&Level")` `wx.Choice`, a `_("&Send actual symbol to synthesizer")`
  `wx.Choice`.
- **Live write-back**: `onListItemFocused` loads the focused row's values into the editor
  controls (using `ChangeValue`/`Selection` so no change event fires), enables the controls,
  and enables Remove only for non-builtin symbols. The editor controls are bound to a
  `skipEventAndCall(self.onSymbolEdited)` wrapper that writes edits straight back into the
  model for the currently-editing item. `onOk` flushes pending edits/removals and saves.
- Buttons here are only `_("&Add")` and `_("Re&move")` (Remove disabled until a row is
  focused). Add opens a tiny `AddSymbolDialog` (single `_("&Symbol:")` field).

**Recommendation for us:** the spec wants provenance display (managed vs overlay, override
visible), slot guidance (main/root/abbr), and live preview. The speech-dict **modal
add/edit** pattern (1a+1b) is the better base because per-entry editing with validation and a
preview button fits a focused sub-dialog, and our list needs multiple provenance/slot columns.
But borrow the symbol dialog's **virtual `AutoWidthColumnListCtrl` + filter** for the browse
list if the effective entry set is large.

---

## 2. Settings placement: Panel vs Dialog vs standalone

Three patterns exist in `source/gui/settingsDialogs.py`; pick by longevity and multiplicity.

- **`SettingsPanel`** — one page of the multi-category NVDA Settings dialog. Override
  `makeSettings(sizer)` + `onSave()`; optional `isValid()`, `postSave()`, `onDiscard()`,
  `onPanelActivated()`/`onPanelDeactivated()`, `panelDescription`. It is a `wx.Panel`, has no
  buttons of its own (the parent owns OK/Cancel/Apply), and its `title` shows in the category
  list. **This is where persistent add-on settings belong** (e.g. our "active managed set"
  dropdown and the enable toggles).

- **`MultiCategorySettingsDialog`** — the container: a category `ListCtrl` on the left, a
  scrolled panel on the right, and OK/Cancel/**Apply**. It builds panels lazily from
  `categoryClasses: list[type[SettingsPanel]]`, supports Control+Tab / Control+Shift+Tab to
  cycle categories (`onCharHook`), and wraps at the ends. `NVDASettingsDialog` is the concrete
  instance; its `categoryClasses` is a plain class list that platform checks append to at import
  (`categoryClasses.append(AddonStorePanel)` etc.). **Add-ons extend NVDA Settings by appending
  their `SettingsPanel` subclass to `NVDASettingsDialog.categoryClasses`** (see §5).

- **`SettingsDialog`** — a standalone dialog with its own OK/Cancel (and optional Apply/Close
  via `buttons={...}`). Override `makeSettings(sizer)`; optional `postInit()` for focus, and
  extend `onOk`/`onCancel`/`onApply`. Key mechanics to know:
  - Only **one instance per subclass** may exist at a time (`__new__` enforces it via
    `_instances`, raising `MultiInstanceError`); `multiInstanceAllowed=True` overrides.
  - `_enterActivatesOk_ctrlSActivatesApply` char hook: **Enter triggers OK even when a list
    has focus** (works around wx #3725 where Enter would otherwise be eaten by the list), and
    **Control+S triggers Apply**. Cancel/Escape is wx-native. Good keyboard behavior we get
    for free by subclassing.
  - `shouldSuspendConfigProfileTriggers = True` by default.
  - This is the base for **tools that open on demand** — the speech-dict and symbol dialogs
    both use it. Our **entry editor** (a task, opened from a menu item, not a settings page)
    should be a `SettingsDialog` subclass, exactly like `DictionaryDialog`.

**Placement decision for us:**
- Add-on configuration (active set dropdown, enable-managed / enable-overlay toggles,
  per-language toggles) → a **`SettingsPanel`** registered into `NVDASettingsDialog`
  (Preferences → NVDA Settings → our category).
- The **entry editor** (browse/add/edit/preview) → a **standalone `SettingsDialog`** opened
  from its own menu item, mirroring `DictionaryDialog`.

---

## 3. guiHelper conventions (`source/gui/guiHelper.py`)

Idiomatic NVDA dialog code composes these helpers rather than hand-managing spacing:

- **Spacing constants** (module-level `Final`s): `BORDER_FOR_DIALOGS = 10` (border around all
  dialog content), `SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS = 10`,
  `SPACE_BETWEEN_BUTTONS_HORIZONTAL = 7`, `SPACE_BETWEEN_BUTTONS_VERTICAL = 5`,
  `SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL = 10`,
  `SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL = 3`, and `COMPLEX_DIALOG_WIDTH = 600`. Use the
  constants; never hardcode pixel gaps.

- **`BoxSizerHelper(parent, orientation=... | sizer=...)`** — the workhorse. Pass either an
  `orientation` (it creates the sizer) or an existing `sizer` (the `SettingsDialog` case:
  `BoxSizerHelper(self, sizer=settingsSizer)`). Methods:
  - `addItem(item, **kw)` — adds with correct inter-item spacing; understands `ButtonHelper`
    (adds its `.sizer` with a 5px border and no extra spacer), nested `BoxSizerHelper`,
    `PathSelectionHelper`, `wx.CheckBox`, and `StaticBoxSizer`/`ScrolledPanel` (auto-`EXPAND`).
  - `addLabeledControl(labelText, wxCtrlClass, **ctrlKwargs)` — creates a `LabeledControlHelper`
    and returns the **control**. List/tree/listbox controls are added `flag=wx.EXPAND,
    proportion=1` (they grow); others get the standard label+control layout. This is how nearly
    every field in the dictionary/symbol dialogs is built.
  - `addDialogDismissButtons(buttons, separated=False)` — must be **last**; asserts nothing is
    added after it. `buttons` can be a bit-OR of `wx.OK|wx.CANCEL|wx.APPLY|wx.CLOSE|...` or a
    `ButtonHelper`/`wx.Button`. `separated=True` inserts a `wx.StaticLine` above the buttons —
    use it for anything richer than a message/single-input dialog.

- **`ButtonHelper(orientation)`** — groups action buttons with correct spacing. `addButton(
  parent=..., label=...)` returns the `wx.Button` so you can `.Bind(...)` inline. Use for the
  Add/Edit/Remove cluster; a lone button can go straight into `addItem`.

- **`LabeledControlHelper` / `associateElements`** — pair a `wx.StaticText` with a control and
  choose layout automatically (label-left for text/choice/button/slider/spin; control-first
  for checkboxes; label-above for list/listbox/tree). It also keeps the label enabled/shown in
  sync with the control. You rarely call this directly — `addLabeledControl` wraps it.

- **`PathSelectionHelper`** — textbox + Browse button + `wx.DirDialog`; relevant if the
  migration/import tool needs a folder picker.

- **`SIPABCMeta`** — metaclass to combine wx's sip wrapper type with `ABCMeta`; required when a
  wx dialog subclass has `@abstractmethod`s (both `DictionaryDialog` and `SettingsDialog` use
  it). If our base classes mix wx + abstract methods, use this metaclass.

- **Threading helpers**: `wxCallOnMain(func, ...)` (blocking call onto the GUI thread with
  return value) and `@alwaysCallAfter` (fire-and-forget onto GUI thread). Useful if a
  background validation/preview ever touches wx from a worker thread.

Canonical standalone-dialog skeleton (from the module docstring and `DictionaryEntryDialog`):

```python
mainSizer = wx.BoxSizer(wx.VERTICAL)
sHelper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
ctrl = sHelper.addLabeledControl(_("&Label"), wx.TextCtrl)
sHelper.addDialogDismissButtons(wx.OK | wx.CANCEL, separated=True)
mainSizer.Add(sHelper.sizer, border=guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL)
mainSizer.Fit(self); self.SetSizer(mainSizer); self.CentreOnParent()
```

---

## 4. Wording and label conventions

Drawn from `source/gui/speechDict.py`, `source/gui/settingsDialogs.py`, and
`source/gui/__init__.py`. These are the exact conventions to match.

- **Accelerators (`&`).** Every actionable label carries an ampersand mnemonic: `_("&Add")`,
  `_("&Edit")`, `_("&Remove")`, `_("&Pattern")`, `_("&Replacement")`, `_("&Comment")`,
  `_("&Type")`, `_("Case &sensitive")`, `_("&Dictionary entries")`. The `&` can be **mid-word**
  to avoid collisions within a dialog: `_("Re&move")` and `_("Case &sensitive")` and
  `_("I&nput gestures...")`. Keep accelerators unique per dialog. Note `DictionaryDialog`
  strips ampersands for the type column labels: `{t: l.replace("&", "") ...}`.

- **Capitalization.** **Title case for dialog/window titles and group boxes**:
  `_("Edit Dictionary Entry")`, `_("Add Dictionary Entry")`, `_("Add Symbol")`,
  `_("Dictionary Entry Error")`, `_("Symbol Pronunciation (%s)")`. **Sentence case for field
  labels, checkboxes, and menu-ish text**: `_("&Pattern")`, `_("Case &sensitive")`,
  `_("Remove all")`, `_("&Send actual symbol to synthesizer")`. Column headers are terse and
  inconsistent about case (`_("Comment")`, `_("Pattern")`, but `_("case")`, `_("off")`,
  `_("on")`) — short and lowercase for status-like columns is acceptable.

- **Ellipsis = "opens another dialog / needs more input."** Menu items and buttons that open a
  further dialog end in `...`: `_("&Settings...")`, `_("&Punctuation/symbol pronunciation...")`,
  `_("I&nput gestures...")`, `_("&Default dictionary...")`, `_("Connect...")`. Buttons that act
  immediately (`_("&Add")`, `_("&Edit")`, `_("&Remove")`, `_("Remove all")`) get **no**
  ellipsis. Note the speech-dict Add/Edit buttons have no ellipsis even though they open a
  modal sub-dialog — NVDA is not fully consistent here, but the safe rule is: menu items and
  "launch settings" buttons get `...`; in-dialog list-management buttons don't.

- **`# Translators:` comments are mandatory and immediately precede the string.** Every
  user-visible string is wrapped in `_()` (or `pgettext`/`ngettext`) and has a
  `# Translators: <what this is>` comment on the line(s) directly above it, describing the
  string's role for the .pot. Multi-line strings put the comment above and may split the string
  across lines. This matches our AGENTS.md rule (`addonHandler.initTranslation()` per module,
  `_()` wrapping, `# Translators:` comments).

- **`pgettext(context, msg)`** is used to disambiguate identical source strings by context
  (e.g. `pgettext("speechSymbols", "&Filter by:")`, `pgettext("remote", ...)`). Use it when a
  short word would otherwise collide across features.

- **Error dialogs** use `gui.messageBox(message, caption, style)` with
  `wx.OK | wx.ICON_WARNING` (validation) or `wx.OK | wx.ICON_ERROR` (hard error); confirmations
  use `wx.YES | wx.NO | wx.NO_DEFAULT`. Titles are title-case (`_("Dictionary Entry Error")`,
  `_("Error")`).

---

## 5. Where tools live, and how add-ons register

### The NVDA menu (built in `SysTrayIcon.__init__`, `source/gui/__init__.py`)

The system-tray menu is `gui.mainFrame.sysTrayIcon.menu`, with two public submenus an add-on
targets:

- **`sysTrayIcon.preferencesMenu`** ("&Preferences" submenu). Contains `_("&Settings...")`
  (opens `NVDASettingsDialog` via `frame.onNVDASettingsCommand`), then — gated on
  `not globalVars.appArgs.secure` — the `_("Speech &dictionaries")` submenu (built by
  `_createSpeechDictsSubMenu`: `_("&Default dictionary...")`, `_("&Voice dictionary...")`,
  `_("&Temporary dictionary...")`, each `popupSettingsDialog(...)`), then
  `_("&Punctuation/symbol pronunciation...")` and `_("I&nput gestures...")`.
- **`sysTrayIcon.toolsMenu`** ("&Tools" submenu): View log, Speech/Braille viewer toggles,
  Add-on store, Python console, etc.

So NVDA's own precedent puts **dictionary and symbol editors under Preferences**, next to
Settings — not under Tools. Tools is for viewers/console/portable-copy style utilities. For us:
our **settings** go in NVDA Settings (Preferences), and our **entry editor** most naturally
sits under **Preferences** as a sibling of the speech-dictionary items (it is a
dictionary editor), though Tools is defensible if we frame it as a utility. Follow the
Preferences precedent unless there's a reason not to.

Dialogs are launched via `mainFrame.popupSettingsDialog(DialogClass[, initialCategoryPanel])`
(`source/gui/__init__.py`), which handles pre/post-popup bookkeeping and the single-instance
error. Menu handlers are thin: e.g. `onSpeechSymbolsCommand → popupSettingsDialog(
SpeechSymbolsDialog)`. Several are decorated `@blockAction.when(blockAction.Context.SECURE_MODE)`
to disable them on secure screens — relevant given our Secure Screen concerns.

### How an add-on registers (the idiomatic pattern)

- **Settings category (a `SettingsPanel`):** in a `GlobalPlugin`, append the panel class to the
  shared list and remove it on teardown:
  ```python
  import gui
  from gui.settingsDialogs import NVDASettingsDialog
  # in __init__:
  NVDASettingsDialog.categoryClasses.append(MyAddonSettingsPanel)
  # in terminate():
  NVDASettingsDialog.categoryClasses.remove(MyAddonSettingsPanel)
  ```
  `categoryClasses` is a plain class-level `list[type[SettingsPanel]]` on
  `MultiCategorySettingsDialog`/`NVDASettingsDialog` (`source/gui/settingsDialogs.py`); NVDA
  itself mutates it the same way at import (`categoryClasses.append(AddonStorePanel)` etc.).
  Our panel gets its own row in the NVDA Settings category list.

- **A menu item:** grab `gui.mainFrame.sysTrayIcon.toolsMenu` (or `.preferencesMenu`),
  `Append(...)`, and `Bind(wx.EVT_MENU, handler, item)`; on teardown `Remove(item.Id)` and
  `item.Destroy()`. The clean, real-world reference is `RemoteMenu` in
  `source/_remoteClient/menu.py`: it captures `sysTrayIcon.toolsMenu`, appends a submenu
  (`toolsMenu.AppendSubMenu(self, _("R&emote Access"), tooltip)`), binds each item on
  `sysTrayIcon`, and in `terminate()` removes and `Destroy()`s every item and the submenu. Copy
  this add/cleanup discipline so nothing leaks when the add-on is disabled.

- **Scripts / gestures:** a `GlobalPlugin` exposes `script_*` methods with a
  `__gestures` mapping (or `@script(...)` decorator) for keyboard entry points — e.g. a gesture
  to open the entry editor. (General add-on mechanism; see `source/globalPluginHandler.py` and
  existing add-ons. Gestures are user-rebindable via the Input Gestures dialog if given a
  category + description.)

---

## 6. Speaking preview text through the active synth

Goal: speak a candidate word so the user hears the pronunciation and iterates. Two API levels,
with a crucial difference in what gets processed.

### The public speech API (`source/speech/__init__.py`, re-exporting `source/speech/speech.py`)

- `speech.speakText(text, symbolLevel=None, priority=None)` — speak a message. Internally
  `_getSpeakMessageSpeech(text)` → `speak(seq, ...)`.
- `speech.speakMessage(text, priority=None)` — same idea; used by `ui.message`.
- `speech.speak(sequence, symbolLevel=None, priority=Spri.NORMAL)` — the core; takes a
  `SpeechSequence` (mix of `str` and `SpeechCommand`s).
- `speech.speakSpelling(text, locale=None, ...)` — spell it out (not what we want for a word
  preview, but available).
- `speech.cancelSpeech()` — stop current speech immediately (call before a preview so repeats
  don't queue up).
- Priorities: `from speech.priorities import Spri` → `Spri.NORMAL`, `Spri.NEXT`, `Spri.NOW`.
  `Spri.NOW` interrupts lower-priority speech and resumes it afterward
  (`source/speech/priorities.py`).
- `ui.message(text, speechPriority=None, brailleText=None)` (`source/ui.py`) — speaks **and**
  brailles; it just calls `speech.speakMessage` + `braille.handler.message`. Fine for status
  announcements, but see the caveat below for preview fidelity.

**Caveat — this path applies NVDA's own text pipeline.** `speech.speak()` runs every string
through `processText(curLanguage, item, symbolLevel, ...)`
(`source/speech/speech.py` `speak`), and `processText` calls
`speechDictHandler.processText(text)` (`source/speech/speech.py` `processText`) **plus** NVDA
symbol/character processing at the configured symbol level. So a preview via
`speakText`/`speakMessage`/`ui.message` reflects the user's **NVDA** speech dictionaries and
symbol settings, not purely what the Eloquence engine would produce from a `.dic` entry.

### Bypassing NVDA's text layer (recommended for a faithful engine preview)

Call the active synth driver directly:

```python
import synthDriverHandler, speech
synth = synthDriverHandler.getSynth()          # active SynthDriver or None
if synth is not None:
    speech.cancelSpeech()                       # or synth.cancel()
    synth.speak([word])                         # SpeechSequence: str + SynthCommand objects
```

- `synthDriverHandler.getSynth() -> SynthDriver | None` returns the active driver
  (`source/synthDriverHandler.py`).
- `SynthDriver.speak(self, speechSequence)` takes "a list of text strings and `SynthCommand`
  objects (such as index and parameter changes)" and speaks it **without** NVDA's speech-dict
  or symbol processing (`source/synthDriverHandler.py`). This is exactly the manager's final
  call — `speech.manager` ends with `getSynth().speak(seq)`
  (`source/speech/manager.py`). `SynthDriver.cancel()` silences immediately.
- You can shape the utterance with `SpeechCommand`s from `speech.commands`
  (`source/speech/commands.py`): `LangChangeCommand(lang)` to force a language,
  `CharacterModeCommand(bool)`, `PitchCommand`/prosody, `IndexCommand`/`CallbackCommand` for
  "finished speaking" callbacks. For Eloquence, a bare `[word]` (optionally with a
  `LangChangeCommand` for the target voice code) is the minimal preview.

**Trade-offs.** Going direct to `synth.speak` bypasses NVDA's speech dictionaries and symbol
processing (what we want — the preview should show the *engine's* rendering), but it also
bypasses the speech **manager**: no priority queueing, no speech-viewer echo, no braille. For a
one-shot "speak this word now" preview that's acceptable; call `speech.cancelSpeech()` (or
`synth.cancel()`) first so successive previews interrupt rather than stack.

**Other caveats:**
- **Asynchrony:** speech is asynchronous; `speak`/`synth.speak` return immediately. To react to
  completion, insert an `IndexCommand`/`CallbackCommand` rather than sleeping.
- **Active synth may not be Eloquence** (flagged at top): our `.dic` entries only affect the
  ECI engine, so preview fidelity depends on Eloquence being the active synth. Detect this
  (`getSynth().name`) and disable/label the preview when it isn't, or offer to preview through a
  transient Eloquence instance if we decide to support that.
- **Speech mode / on-demand:** the manager path honors `SpeechMode` (off/beeps/onDemand); a
  direct `synth.speak` does not, so a direct preview will speak even if NVDA speech is set to
  off. Consider checking mode if that matters.
- **Thread safety:** synth calls should be made from the GUI thread (they are, from a button
  handler); use `guiHelper.wxCallOnMain` / `@alwaysCallAfter` if ever driven from a worker.

---

## 7. Persisting per-dialog state (size, position, column widths)

Short answer: **NVDA mostly does not persist this, and there's no turnkey framework to lean
on.**

- The speech-dict dialog **hardcodes** its initial size (`self.SetSize(576, 502)` in
  `DictionaryDialog.__init__`) with a comment explaining the value came from the historical
  `dictList` size (#6287), and it deliberately avoids clearing the list so **column widths the
  user dragged survive within the session** (the `onRemoveAll` loop comment: clearing "would
  eventually [lose] their manually changed widths"). Nothing is written to disk — reopen the
  dialog and it's back to defaults. (`source/gui/speechDict.py`.)
- `MultiCategorySettingsDialog` sets a fixed `INITIAL_SIZE = (800, 480)` / `MIN_SIZE =
  (470, 240)` and re-centers; not persisted either. (`source/gui/settingsDialogs.py`.)
- A real persistence mechanism exists but is **new and narrowly used**:
  `wx.lib.agw.persist` via `PersistenceManager`, initialized in `source/gui/__init__.py`
  `initialize()` (`SetPersistenceFile(NVDAState.WritePaths.guiStateFile)`; saving disabled when
  `not shouldWriteToDisk()`), with a custom handler
  `gui.persistenceHandler.EnumeratedChoiceHandler` for `wx.Choice`. The **only** current
  consumer is the Remote dialogs (`source/_remoteClient/dialogs.py`): they
  `persistenceManager.Register(control, ...)` / `.Restore(control)` on show and `.Save()` /
  `.Unregister()` on close, persisting a couple of `wx.Choice` selections — not window geometry.

**Implication for us:** if we want the entry editor to remember size/position or column widths
across sessions, we implement it ourselves (either the `wx.lib.agw.persist` route, registering
named controls like the Remote dialogs do, or by saving to our add-on config on close and
restoring in `postInit`). Don't expect `SettingsDialog`/`DictionaryDialog` to do it for us.
Matching NVDA's own behavior (hardcoded sensible default size, session-only column widths) is
the low-effort, idiomatic baseline; persisted geometry would be a deliberate enhancement.
