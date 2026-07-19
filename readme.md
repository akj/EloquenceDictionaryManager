# Eloquence Dictionary Manager

Eloquence Dictionary Manager is an NVDA add-on that provides community
Eloquence pronunciation dictionary sets and an editor for your own dictionary
entries. It includes the eigencrow IBMTTSDictionaries set, ready to use without
a separate download.

## Opening the dictionary editor

Open the NVDA menu, choose **Preferences**, and then choose **Eloquence
dictionaries...** (Alt+D). This opens the **Eloquence Dictionary Entries**
dialog. The menu item appears next to NVDA's speech dictionary commands.

You can also assign your own gesture:

1. Open the NVDA menu, choose **Preferences**, and then **Input gestures...**.
2. Find the **Eloquence Dictionary Manager** category.
3. Assign a gesture to **Opens the Eloquence Dictionaries dialog.**

This command is initially unassigned.

Changes in **Eloquence Dictionary Entries** are kept in a working copy. Choose
**OK** to save them or **Cancel** to discard everything changed since you opened
the dialog, including imports.

## Languages, managed sets, and the entry list

Use **Language:** (Alt+L) to choose an Eloquence language. Use **Managed set:**
(Alt+S) to view a managed dictionary set, or choose **None (personal entries
only)**. This control only changes what the editor shows. The set used for
speech is chosen in your Eloquence synthesizer's settings.

Managed sets are read only. Select a managed entry and choose **Set Details...**
to open **Managed Dictionary Set Details**. This dialog shows the set's Name,
Attribution, Source URL, License, License URL, Source version, and exact Source
revision.

The **Dictionary entries** list shows the effective entries for the selected
language and set in four columns: **Word**, **Pronunciation**, **Type**, and
**Source**. The source tells you whether an entry is managed, personal, or a
personal override of a managed entry.

Use **Filter by:** (Alt+F) to filter by the beginning of a word; exact matches
are shown first. Use **Show:** (Alt+W) to choose **All entries**, **Personal
only**, **Personal overrides only**, or **Managed only**.

The main actions are **Add**, **Edit**, **Set Details...**, **Remove**,
**Import...**, **Export...**, **Import from old Eloquence dictionary files...**,
and **Remove all personal entries**.

## Adding, editing, and removing entries

Choose **Add** to open **Add Dictionary Entry** and create a personal entry.
Choose **Edit** on a personal row to open **Edit Dictionary Entry**. The entry
Type cannot be changed while editing, but the Word and Pronunciation can be
changed.

Choose **Edit** on a managed row to open **Customize Dictionary Entry**. This
copies the managed entry into your personal entries as an override. Its Word and
Type stay fixed, and you can change its Pronunciation. The original managed file
is never edited.

The entry dialog contains:

- **Word:** (Alt+W) and **Pronunciation:** (Alt+P) fields.
- A **Type** group (Alt+T) with **Exact word**, **Word root (matches all word
  forms)**, and **Abbreviation**.
- Read-only **Rules:** guidance (Alt+S) that changes with the selected Type.
- **Play current** (Alt+C), which previews the Word as Eloquence currently
  speaks it, and **Play new** (Alt+N), which previews the entered Pronunciation.

Preview uses Eloquence directly. If Eloquence is not the active synthesizer,
the buttons remain available but announce: "Preview unavailable: Eloquence is
not the active synthesizer."

Entries are checked before they are accepted:

- Both Word and Pronunciation must contain text. Tabs, line breaks, and NUL
  characters are not allowed. Characters that the selected language cannot
  encode are rejected.
- **Exact word** entries cannot contain spaces or end with punctuation.
  Capitalization matters. Pronunciations may use ordinary text, Eloquence
  phonetic strings, and emphasis codes.
- **Word root** entries contain letters only, are stored in lowercase, and
  ignore capitalization when matching. A pronunciation must be one bare word
  or one phonetic string, not an annotation or multiple words.
- **Abbreviation** entries use letters, meaningful periods, and permitted
  internal apostrophes. Capitalization matters. The expansion must contain
  plain words separated by spaces or hyphens, without phonetic strings or
  annotations.

Choose **Remove** to delete a personal-only entry. Removing a personal override
immediately restores the managed pronunciation. Managed entries themselves
cannot be deleted in this version; they can only be overridden and later
restored by removing the override. **Remove all personal entries** removes all
personal entries for the shown language after confirmation and does not affect
managed content.

## Exporting and importing personal entries

Eloquence Dictionary Manager uses `.edm-dict` files to back up personal entries
and share them between users or machines. An `.edm-dict` file is a zip archive
containing validated Eloquence dictionary files and a manifest.

Choose **Export...** to open **Export Dictionary Entries**. Under **Export
scope**, choose **Shown language only** or **All languages**. Export includes
personal entries and personal overrides, not managed entries. Choose a name and
location for the resulting `.edm-dict` file.

Choose **Import...** and select an `.edm-dict` file. In **Import Dictionary
Entries**, choose an **Import mode**:

- **Add to your entries** merges entries from the file with your current
  personal entries. If entries collide, choose **Keep my entries** or **Use the
  imported entries** for all collisions.
- **Replace your entries for the languages in the file** first removes your
  personal entries for the languages included in the file, then imports the
  file's entries. Other languages are not changed.

Invalid entries are skipped and counted in the completion message. Imported
changes appear immediately in the working copy. Choose **OK** in the main dialog
to save them or **Cancel** to undo the complete import.

## Migrating old Eloquence dictionary files

Choose **Import from old Eloquence dictionary files...** to recover likely hand
edits from dictionaries used before this add-on. The tool compares old entries
with provenance hashes made from the known history of IBMTTSDictionaries and
AltIBMTTSDictionaries. Known upstream content is skipped, so the review shows
only entries that look like your own changes. The tool never modifies or
deletes the old files.

The tool first looks in the old Eloquence add-on's
`synthDrivers/eloquence-dic-backup` folder and then its live
`synthDrivers/eloquence` folder. If nothing is found automatically, the button
opens **Select Old Eloquence Dictionary Folder** so you can choose another
location.

When old files are detected automatically, **Old Eloquence Dictionary Files**
asks whether to review them. Choose **Yes** to review now, **Later** to be asked
again in a later editor session, or **Don't ask again** to dismiss future
automatic prompts. You can still use the migration button after dismissing the
prompt.

The **Import from Old Eloquence Dictionary Files** review dialog contains a
checkable **Dictionary entries to import** list with **Word**, **Pronunciation**,
**Type**, **Language**, and **Status** columns. Likely hand edits are checked by
default. You can uncheck entries you do not want. Invalid entries are shown
unchecked and cannot be checked; their Status explains what must be corrected
manually. Entries already identical to your personal entries are omitted. A
different value that collides with a personal entry is unchecked by default;
checking it replaces your current value.

Choose **Import checked entries** to add the checked rows to the main editor's
working copy. Review or edit them there, then choose **OK** to save them or
**Cancel** to undo the migration import.

### Important migration limitation: deletions are not migrated

A deletion you made to old managed dictionary content is not migrated. The
migration tool can recover added or changed lines, but it cannot prove that an
absent line was intentionally deleted. Because managed entries cannot be hidden
with a deletion marker in this version, that managed entry will return.

## Credits and licensing

The Eloquence Dictionary Manager add-on software is licensed under the GNU
General Public License, version 2 or later (GPL-2.0-or-later). See
[COPYING.txt](https://github.com/akj/EloquenceDictionaryManager/blob/main/COPYING.txt).

The bundled dictionary data is licensed separately. The bundled
[eigencrow IBMTTSDictionaries](https://github.com/eigencrow/IBMTTSDictionaries)
set is licensed under
[CC0-1.0](https://github.com/eigencrow/IBMTTSDictionaries/blob/d997036dec4b5aad80ad53d8133326a67d1f41ec/LICENSE.md),
a public domain dedication. Credit goes to eigencrow and the upstream
contributors who curate this set.

[mohamed00 AltIBMTTSDictionaries](https://github.com/Mohamed00/AltIBMTTSDictionaries)
informs only the migration tool's historical provenance hashes. Its dictionary
content is not bundled because the repository provides no redistribution
license grant.

## Development

This repository uses the official
[NV Access AddonTemplate](https://github.com/nvaccess/AddonTemplate). The build
requires Python 3.13, GNU gettext, and the dependencies declared in
`pyproject.toml`.

Install the development dependencies and build the add-on with:

```powershell
uv sync
uv run scons
```

The package is written to the repository root as
`eloquenceDictionaryManager-0.1.0.nvda-addon`.

Generate the gettext template with:

```powershell
uv run scons pot
```

The generated catalog is `eloquenceDictionaryManager.pot`.

Project behavior and packaging requirements are documented in
[`docs/specs/dictionaries-addon.md`](docs/specs/dictionaries-addon.md).
