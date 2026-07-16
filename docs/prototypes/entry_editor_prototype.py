# PROTOTYPE — throwaway wx mock of the Eloquence Dictionaries entry editor.
# Companion to entry-editor-walkthrough.md (wayfinder ticket #7). Not production code:
# no NVDA, no real .dic files, no translation marking. Sample data is in memory only.
#
# Run:  python entry_editor_prototype.py   (requires wxPython: pip install wxPython)
#
# What is real here: dialog layout, tab order, labels/accelerators, list columns,
# provenance display, add/edit/customize/remove flows, focus handling, the full
# validation catalog, and the per-type Rules guidance text.
# What is simulated: speech preview speaks through Windows SAPI (a stand-in for the
# real getSynth().speak(), since there is no Eloquence engine outside NVDA); the
# "[Prototype harness]" checkbox stands in for which synth is active.

import string
import subprocess
import wx

# ---------------------------------------------------------------- sample data

SETS = {
    "github.eigencrow.ibmtts-dictionaries": {
        "name": "IBM TTS Dictionaries",
        "version": "v1.1",
        "url": "https://github.com/eigencrow/IBMTTSDictionaries",
        "revision": "d3adb33f" + "0" * 32,
        "license": "CC0-1.0",
        "attribution": "Compiled by eigencrow and contributors.",
    },
    "github.mohamed00.alt-ibmtts-dictionaries": {
        "name": "Alternative IBM TTS Dictionaries",
        "version": "2025.03",
        "url": "https://github.com/Mohamed00/AltIBMTTSDictionaries",
        "revision": "c0ffee12" + "0" * 32,
        "license": "(permission pending — illustrative only)",
        "attribution": "Compiled by Mohamed00 and contributors.",
    },
}

LANGUAGES = [
    ("esp", "Spanish (Castilian)"),
    ("enu", "English (US)"),
    ("deu", "German"),
]

SLOT_LABELS = {"main": "Exact word", "root": "Word root", "abbr": "Abbreviation"}
SLOT_ORDER = ["main", "root", "abbr"]

# (set_id) -> {(lang, slot, key): value}
MANAGED = {
    "github.mohamed00.alt-ibmtts-dictionaries": {
        ("esp", "main", "no"): "`1 no",
        ("esp", "main", "No"): "`1 No",
        ("esp", "main", "ni"): "`00 ni",
        ("esp", "main", "muy"): "`1 muy",
        ("esp", "root", "madrid"): "`[ma.1DRid]",
        ("enu", "main", "mbox"): "em `0 box",
        ("enu", "root", "encrypt"): "`[.0XG.1krIpt]",
        ("enu", "root", "ribcage"): "`[r1Ib.2keJ]",
    },
    "github.eigencrow.ibmtts-dictionaries": {
        ("enu", "main", "WYSIWYG"): "`[1wI0zi0wIg]",
        ("enu", "main", "UConn"): "`[2yu1kan]",
        ("enu", "main", "tête-à-têtes"): "tet ah tets",
        ("enu", "root", "encrypt"): "`[.0XG.1krIpt]",
        ("enu", "root", "postfix"): "`[.1post.2fIks]",
        ("enu", "abbr", "WWII"): "world war two",
        ("enu", "abbr", "Ltjg"): "lieutenant junior-grade",
        ("deu", "main", "Düsburg"): "`[d1YsbUrk]",
    },
}

# The committed personal overlay; the dialog edits a working copy of this.
OVERLAY = {
    ("enu", "root", "quinoa"): "keenwah",
}

RULES = {
    "main": (
        'Matches the word exactly as written — capitalization counts, so "NASA" '
        'and "nasa" are separate entries. The word cannot contain spaces or end with '
        "punctuation. The pronunciation may be words, phonetic strings like "
        "`[.1kwi.0nwa], or emphasis codes `0 (flat) through `4 (strongest)."
    ),
    "root": (
        'Matches a word and all of its forms — "figure" also covers figures, '
        "figured, figuring — ignoring capitalization. Roots are stored in "
        "lowercase and can contain only letters. The pronunciation must be a single "
        "word or one phonetic string (`[...])."
    ),
    "abbr": (
        "Matches an abbreviation written with letters and periods — "
        'capitalization counts. A trailing period is meaningful: "approx." matches '
        'only "approx.", while "approx" matches both "approx" and "approx.". '
        "The expansion must be plain words."
    ),
}

# ---------------------------------------------------------------- validation


def identity_key(lang, slot, key):
    """Entry identity: roots match case-insensitively, so store them lowercased."""
    return (lang, slot, key.lower() if slot == "root" else key)


def find_non_cp1252(text):
    for ch in text:
        try:
            ch.encode("cp1252")
        except UnicodeEncodeError:
            return ch
    return None


def check_spr_structure(value):
    """Validate structure of any `[...] phonetic strings; returns error or None."""
    i = 0
    while True:
        i = value.find("`[", i)
        if i == -1:
            return None
        end = value.find("]", i)
        if end == -1:
            return 'The phonetic string is not closed — expected "]" after "`[".'
        spr = value[i + 2 : end]
        syllables = spr.count(".") + 1
        if syllables > 1 and "1" not in spr:
            return (
                "A phonetic string with more than one syllable needs a primary "
                'stress marker "1", for example `[.1kwi.0nwa].'
            )
        i = end + 1


def is_single_spr(value):
    return value.startswith("`[") and value.endswith("]") and value.count("`[") == 1


def validate(slot, word, pron):
    """Return an error message, or None. Order mirrors the walkthrough catalog."""
    if not word:
        return "A word is required."
    if not pron:
        return "A pronunciation is required."
    if slot == "main":
        if any(c.isspace() for c in word):
            return (
                "The word cannot contain spaces. Dictionary entries match one "
                "word at a time."
            )
        if word[-1] in string.punctuation:
            return (
                'The word cannot end with punctuation ("%s" ends with "%s").'
                % (word, word[-1])
            )
    elif slot == "root":
        if not word.isalpha():
            return (
                'Word roots can contain only letters. "%s" cannot be a word root '
                "— for words with digits or symbols, use an Exact word entry."
                % word
            )
        if not (is_single_spr(pron) or pron.isalpha()):
            return (
                "A word root pronunciation must be a single word or one phonetic "
                "string (`[...]) — no spaces, digits, or emphasis codes."
            )
    elif slot == "abbr":
        stripped = word.replace(".", "").replace("'", "")
        if (
            not stripped.isalpha()
            or word[0] in ".'"
            or word[-1] == "'"
            or "''" in word
        ):
            return (
                "An abbreviation can contain only letters and periods, with "
                'apostrophes inside the word — for example "Dr." or "e.g.".'
            )
        if not all(
            part.isalpha() for part in pron.replace("-", " ").split()
        ) or not pron.strip():
            return (
                "An abbreviation expansion must be plain words separated by spaces "
                "or hyphens — no digits, punctuation, or phonetic symbols."
            )
    for text in (word, pron):
        bad = find_non_cp1252(text)
        if bad:
            return (
                'The character "%s" cannot be saved in an Eloquence dictionary '
                "(Western encoding only)." % bad
            )
    if slot != "abbr":
        err = check_spr_structure(pron)
        if err:
            return err
    return None


# ---------------------------------------------------------------- entry dialog


class EntryDialog(wx.Dialog):
    """Add / Edit / Customize Dictionary Entry."""

    def __init__(self, parent, title, lang, slot="main", word="", pron="",
                 lock_type=False, lock_word=False, eloquence_active=True):
        super().__init__(parent, title=title)
        self.lang = lang
        self.result = None
        self._speechProc = None

        outer = wx.BoxSizer(wx.VERTICAL)
        body = wx.BoxSizer(wx.VERTICAL)

        grid = wx.FlexGridSizer(2, 2, 5, 10)
        grid.AddGrowableCol(1)
        grid.Add(wx.StaticText(self, label="&Word:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.wordCtrl = wx.TextCtrl(self, value=word, size=(300, -1))
        self.wordCtrl.Enable(not lock_word)
        grid.Add(self.wordCtrl, 1, wx.EXPAND)
        grid.Add(wx.StaticText(self, label="&Pronunciation:"), 0,
                 wx.ALIGN_CENTER_VERTICAL)
        self.pronCtrl = wx.TextCtrl(self, value=pron, size=(300, -1))
        grid.Add(self.pronCtrl, 1, wx.EXPAND)
        body.Add(grid, 0, wx.EXPAND | wx.BOTTOM, 10)

        self.typeBox = wx.RadioBox(
            self, label="&Type",
            choices=["Exact word", "Word root (matches all word forms)",
                     "Abbreviation"],
            majorDimension=1, style=wx.RA_SPECIFY_COLS,
        )
        self.typeBox.SetSelection(SLOT_ORDER.index(slot))
        self.typeBox.Enable(not lock_type)
        self.typeBox.Bind(wx.EVT_RADIOBOX, self.onTypeChanged)
        body.Add(self.typeBox, 0, wx.EXPAND | wx.BOTTOM, 10)

        body.Add(wx.StaticText(self, label="Rule&s:"), 0)
        self.rulesCtrl = wx.TextCtrl(
            self, value=RULES[slot], size=(440, 80),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_BESTWRAP,
        )
        body.Add(self.rulesCtrl, 0, wx.EXPAND | wx.BOTTOM, 10)

        if not eloquence_active:
            note = wx.StaticText(
                self, label="Preview requires Eloquence to be the active synthesizer.")
            body.Add(note, 0, wx.BOTTOM, 5)
        btnRow = wx.BoxSizer(wx.HORIZONTAL)
        self.playCurrent = wx.Button(self, label="Play c&urrent")
        self.playNew = wx.Button(self, label="Play &new")
        self.playCurrent.Bind(wx.EVT_BUTTON, self.onPlayCurrent)
        self.playNew.Bind(wx.EVT_BUTTON, self.onPlayNew)
        self.playCurrent.Enable(eloquence_active)
        self.playNew.Enable(eloquence_active)
        btnRow.Add(self.playCurrent, 0, wx.RIGHT, 7)
        btnRow.Add(self.playNew, 0)
        body.Add(btnRow, 0, wx.BOTTOM, 10)

        outer.Add(body, 1, wx.EXPAND | wx.ALL, 10)
        outer.Add(wx.StaticLine(self), 0, wx.EXPAND)
        outer.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0,
                  wx.EXPAND | wx.ALL, 10)
        self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
        self.SetSizerAndFit(outer)
        self.CentreOnParent()
        self.wordCtrl.SetFocus()

    def slot(self):
        return SLOT_ORDER[self.typeBox.GetSelection()]

    def onTypeChanged(self, evt):
        self.rulesCtrl.SetValue(RULES[self.slot()])

    def _speak(self, text):
        # Real add-on: speech.cancelSpeech(); getSynth().speak([text]) — speaks
        # directly, no dialog. PROTOTYPE stands that in with Windows SAPI, launched
        # detached so speech is async and successive previews interrupt (SAPIF_PURGE).
        text = (text or "").strip()
        if not text:
            return
        if self._speechProc and self._speechProc.poll() is None:
            self._speechProc.terminate()  # stands in for cancelSpeech()
        ps = (
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            "$s.Speak([Console]::In.ReadToEnd())"
        )
        try:
            self._speechProc = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, text=True)
            self._speechProc.stdin.write(text)
            self._speechProc.stdin.close()
        except OSError:
            pass  # prototype: no voice available, just stay silent

    def onPlayCurrent(self, evt):
        self._speak(self.wordCtrl.GetValue())

    def onPlayNew(self, evt):
        self._speak(self.pronCtrl.GetValue())

    def onOk(self, evt):
        word = self.wordCtrl.GetValue().strip()
        pron = self.pronCtrl.GetValue().strip()
        slot = self.slot()
        err = validate(slot, word, pron)
        if err:
            wx.MessageBox(err, "Dictionary Entry Error",
                          wx.OK | wx.ICON_WARNING, self)
            (self.wordCtrl if "word" in err.lower() or "abbreviation can" in err
             else self.pronCtrl).SetFocus()
            return  # dialog stays open
        if slot == "root":
            word = word.lower()  # roots are case-insensitive; stored lowercase
        self.result = (slot, word, pron)
        evt.Skip()


# ---------------------------------------------------------------- set details


class SetDetailsDialog(wx.Dialog):
    def __init__(self, parent, set_id):
        info = SETS[set_id]
        super().__init__(parent, title="Set Details: %s" % info["name"])
        outer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(2, 5, 8)
        grid.AddGrowableCol(1)
        for label, value in [
            ("Name:", info["name"]), ("Version:", info["version"]),
            ("Source:", info["url"]), ("Revision:", info["revision"]),
            ("License:", info["license"]), ("Attribution:", info["attribution"]),
            ("Set ID:", set_id),
        ]:
            grid.Add(wx.StaticText(self, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            ctrl = wx.TextCtrl(self, value=value, size=(360, -1),
                               style=wx.TE_READONLY)
            grid.Add(ctrl, 1, wx.EXPAND)
        outer.Add(grid, 1, wx.EXPAND | wx.ALL, 10)
        outer.Add(wx.StaticLine(self), 0, wx.EXPAND)
        outer.Add(self.CreateStdDialogButtonSizer(wx.CLOSE), 0, wx.EXPAND | wx.ALL, 10)
        self.SetEscapeId(wx.ID_CLOSE)
        self.SetSizerAndFit(outer)
        self.CentreOnParent()


# ---------------------------------------------------------------- main dialog


class EditorDialog(wx.Dialog):
    def __init__(self):
        super().__init__(None, title="Eloquence Dictionary Entries — PROTOTYPE",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.overlay = dict(OVERLAY)  # working copy; committed on OK
        self.rows = []

        outer = wx.BoxSizer(wx.VERTICAL)
        body = wx.BoxSizer(wx.VERTICAL)

        # [Prototype harness] — not part of the real design
        self.simEloquence = wx.CheckBox(
            self,
            label="[Prototype harness] Simulate Eloquence as the active synthesizer")
        self.simEloquence.SetValue(True)
        body.Add(self.simEloquence, 0, wx.BOTTOM, 10)

        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(wx.StaticText(self, label="&Language:"), 0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.langChoice = wx.Choice(
            self, choices=[name for _, name in LANGUAGES])
        self.langChoice.SetSelection(0)  # real dialog: active Eloquence voice's lang
        self.langChoice.Bind(wx.EVT_CHOICE, lambda e: self.refresh())
        top.Add(self.langChoice, 0, wx.RIGHT, 15)

        top.Add(wx.StaticText(self, label="Managed &set:"), 0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.set_ids = list(SETS)
        self.setChoice = wx.Choice(
            self, choices=["%s (%s)" % (SETS[s]["name"], SETS[s]["version"])
                           for s in self.set_ids] + ["None (personal entries only)"])
        # PROTOTYPE default: the Alt set, so the walkthrough's Spanish "no" scenario
        # is visible on open. The real dialog defaults to the only eligible set.
        self.setChoice.SetSelection(1)
        self.setChoice.Bind(wx.EVT_CHOICE, lambda e: self.refresh())
        top.Add(self.setChoice, 0, wx.RIGHT, 7)
        detailsBtn = wx.Button(self, label="Set &details")
        detailsBtn.Bind(wx.EVT_BUTTON, self.onSetDetails)
        top.Add(detailsBtn, 0)
        body.Add(top, 0, wx.BOTTOM, 3)

        body.Add(wx.StaticText(
            self, label="Viewing only — the set your synthesizer uses is "
                        "chosen in the synthesizer's settings."), 0, wx.BOTTOM, 10)

        filterRow = wx.BoxSizer(wx.HORIZONTAL)
        filterRow.Add(wx.StaticText(self, label="&Filter by:"), 0,
                      wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.filterCtrl = wx.TextCtrl(self, size=(180, -1))
        self.filterCtrl.Bind(wx.EVT_TEXT, lambda e: self.refresh())
        filterRow.Add(self.filterCtrl, 0, wx.RIGHT, 15)
        filterRow.Add(wx.StaticText(self, label="Sho&w:"), 0,
                      wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.showChoice = wx.Choice(self, choices=[
            "All entries", "Personal only", "Personal overrides only",
            "Managed only"])
        self.showChoice.SetSelection(0)
        self.showChoice.Bind(wx.EVT_CHOICE, lambda e: self.refresh())
        filterRow.Add(self.showChoice, 0)
        body.Add(filterRow, 0, wx.BOTTOM, 10)

        body.Add(wx.StaticText(self, label="Dictionary &entries:"), 0)
        self.list = wx.ListCtrl(self, size=(640, 260),
                                style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        for col, width in [("Word", 140), ("Pronunciation", 170), ("Type", 100),
                           ("Source", 220)]:
            self.list.AppendColumn(col, width=width)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda e: self.updateButtons())
        self.list.Bind(wx.EVT_LIST_ITEM_DESELECTED, lambda e: self.updateButtons())
        body.Add(self.list, 1, wx.EXPAND | wx.BOTTOM, 5)

        btnRow = wx.BoxSizer(wx.HORIZONTAL)
        self.addBtn = wx.Button(self, label="&Add")
        self.editBtn = wx.Button(self, label="&Edit")
        self.removeBtn = wx.Button(self, label="&Remove")
        removeAllBtn = wx.Button(self, label="Remove all personal entries")
        self.addBtn.Bind(wx.EVT_BUTTON, self.onAdd)
        self.editBtn.Bind(wx.EVT_BUTTON, self.onEdit)
        self.removeBtn.Bind(wx.EVT_BUTTON, self.onRemove)
        removeAllBtn.Bind(wx.EVT_BUTTON, self.onRemoveAll)
        for b in (self.addBtn, self.editBtn, self.removeBtn):
            btnRow.Add(b, 0, wx.RIGHT, 7)
        btnRow.AddStretchSpacer()
        btnRow.Add(removeAllBtn, 0)
        body.Add(btnRow, 0, wx.EXPAND)

        outer.Add(body, 1, wx.EXPAND | wx.ALL, 10)
        outer.Add(wx.StaticLine(self), 0, wx.EXPAND)
        outer.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0,
                  wx.EXPAND | wx.ALL, 10)
        self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
        self.SetSizerAndFit(outer)
        self.SetSize((720, 560))
        self.CentreOnScreen()
        self.refresh()
        self.list.SetFocus()

    # ---- state helpers

    def lang(self):
        return LANGUAGES[self.langChoice.GetSelection()][0]

    def viewed_set(self):
        i = self.setChoice.GetSelection()
        return self.set_ids[i] if i < len(self.set_ids) else None

    def buildRows(self):
        """Effective merged view: managed (viewed set) + overlay, overrides folded."""
        lang, set_id = self.lang(), self.viewed_set()
        merged = {}
        if set_id:
            info = SETS[set_id]
            managed_label = "Managed — %s (%s)" % (info["name"], info["version"])
            for (l, slot, key), value in MANAGED[set_id].items():
                if l == lang:
                    merged[identity_key(l, slot, key)] = dict(
                        word=key, pron=value, slot=slot, source=managed_label,
                        kind="managed")
        for (l, slot, key), value in self.overlay.items():
            if l != lang:
                continue
            ident = identity_key(l, slot, key)
            if ident in merged:
                merged[ident].update(
                    pron=value, word=key, kind="override",
                    source="Personal — overrides %s" % SETS[set_id]["name"])
            else:
                merged[ident] = dict(word=key, pron=value, slot=slot,
                                     source="Personal", kind="personal")
        rows = list(merged.values())
        flt = self.filterCtrl.GetValue().strip().lower()
        if flt:
            rows = [r for r in rows if r["word"].lower().startswith(flt)
                    or flt in r["pron"].lower()]
        show = self.showChoice.GetSelection()
        if show == 1:
            rows = [r for r in rows if r["kind"] in ("personal", "override")]
        elif show == 2:
            rows = [r for r in rows if r["kind"] == "override"]
        elif show == 3:
            rows = [r for r in rows if r["kind"] == "managed"]
        rows.sort(key=lambda r: (r["word"].lower() != flt if flt else False,
                                 r["word"].lower(), SLOT_ORDER.index(r["slot"])))
        return rows

    def refresh(self, focus_word=None, focus_slot=None):
        self.rows = self.buildRows()
        self.list.DeleteAllItems()
        for r in self.rows:
            self.list.Append((r["word"], r["pron"], SLOT_LABELS[r["slot"]],
                              r["source"]))
        target = 0
        if focus_word is not None:
            for i, r in enumerate(self.rows):
                if r["word"] == focus_word and r["slot"] == focus_slot:
                    target = i
                    break
        if self.rows:
            self.list.Select(target)
            self.list.Focus(target)
        self.updateButtons()
        self.dumpState()

    def selectedRow(self):
        i = self.list.GetFirstSelected()
        return self.rows[i] if i != -1 else None

    def updateButtons(self):
        row = self.selectedRow()
        self.editBtn.Enable(row is not None)
        # Remove only where there is a personal component; managed rows: disabled.
        self.removeBtn.Enable(row is not None and row["kind"] != "managed")

    def dumpState(self):
        # PROTOTYPE: surface the working-copy state after every action.
        print("\n--- working-copy overlay (%d entries) ---" % len(self.overlay))
        for (l, slot, key), value in sorted(self.overlay.items()):
            print("  [%s %s] %s\t%s" % (l, slot, key, value))

    # ---- actions

    def onSetDetails(self, evt):
        set_id = self.viewed_set()
        if set_id:
            SetDetailsDialog(self, set_id).ShowModal()

    def _confirmReplace(self, word, slot):
        return wx.MessageBox(
            'You already have a personal entry for "%s" (%s). Replace it?'
            % (word, SLOT_LABELS[slot]),
            "Dictionary Entry", wx.YES_NO | wx.NO_DEFAULT, self) == wx.YES

    def onAdd(self, evt):
        dlg = EntryDialog(self, "Add Dictionary Entry", self.lang(),
                          eloquence_active=self.simEloquence.GetValue())
        if dlg.ShowModal() == wx.ID_OK and dlg.result:
            slot, word, pron = dlg.result
            ident = identity_key(self.lang(), slot, word)
            if ident in self.overlay and not self._confirmReplace(word, slot):
                dlg.Destroy()
                self.list.SetFocus()
                return
            self.overlay.pop(ident, None)
            self.overlay[(self.lang(), slot, word)] = pron
            self.refresh(focus_word=word, focus_slot=slot)
        dlg.Destroy()
        self.list.SetFocus()

    def onEdit(self, evt):
        row = self.selectedRow()
        if not row:
            return
        customizing = row["kind"] == "managed"
        title = ("Customize Dictionary Entry" if customizing
                 else "Edit Dictionary Entry")
        dlg = EntryDialog(self, title, self.lang(), slot=row["slot"],
                          word=row["word"], pron=row["pron"],
                          lock_type=True, lock_word=customizing,
                          eloquence_active=self.simEloquence.GetValue())
        if dlg.ShowModal() == wx.ID_OK and dlg.result:
            slot, word, pron = dlg.result
            old_ident = identity_key(self.lang(), row["slot"], row["word"])
            for k in list(self.overlay):
                if identity_key(*k) == old_ident:
                    del self.overlay[k]
            self.overlay[(self.lang(), slot, word)] = pron
            self.refresh(focus_word=word, focus_slot=slot)
        dlg.Destroy()
        self.list.SetFocus()

    def onRemove(self, evt):
        row = self.selectedRow()
        if not row or row["kind"] == "managed":
            return
        # No confirmation: Cancel discards the whole working copy (the safety net).
        ident = identity_key(self.lang(), row["slot"], row["word"])
        for k in list(self.overlay):
            if identity_key(*k) == ident:
                del self.overlay[k]
        # Override: the managed entry resurfaces in place and keeps focus.
        # Pure personal: the row disappears; focus falls to the nearest row.
        self.refresh(focus_word=row["word"], focus_slot=row["slot"])
        self.list.SetFocus()

    def onRemoveAll(self, evt):
        lang = self.lang()
        mine = [k for k in self.overlay if k[0] == lang]
        lang_name = LANGUAGES[self.langChoice.GetSelection()][1]
        if not mine:
            wx.MessageBox("You have no personal entries for %s." % lang_name,
                          "Eloquence Dictionary Entries", wx.OK, self)
            return
        if wx.MessageBox(
                "Remove all %d of your personal entries for %s? Managed entries "
                "are not affected." % (len(mine), lang_name),
                "Eloquence Dictionary Entries",
                wx.YES_NO | wx.NO_DEFAULT, self) == wx.YES:
            for k in mine:
                del self.overlay[k]
            self.refresh()
        self.list.SetFocus()

    def onOk(self, evt):
        global OVERLAY
        OVERLAY = dict(self.overlay)
        print("\n=== OK: overlay committed (real add-on would write "
              "<config>/eciDictionaries/personal/<code><slot>.dic, CP1252, CRLF) ===")
        self.dumpState()
        evt.Skip()


if __name__ == "__main__":
    app = wx.App()
    dlg = EditorDialog()
    dlg.ShowModal()
    print("\nPrototype closed. (Cancel discards the working copy.)")
