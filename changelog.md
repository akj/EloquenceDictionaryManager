# 0.1.0

First release.

- Includes the v26.11 release of the IBMTTSDictionaries pronunciation set
  curated by eigencrow, so you don't need to download it separately. Choose it
  in your synthesizer's voice settings.
- Adds the **Eloquence Dictionary Entries** editor. Open it from the NVDA menu:
  **Preferences**, then **Eloquence dictionaries...**. You can add, edit, and
  remove your own entries, and customize any entry in the bundled set without
  changing the set itself.
- Plays the current and the new pronunciation of an entry when Eloquence or
  OpenEVV is your synthesizer. A phonetic pronunciation plays correctly only
  when the synthesizer's backquote voice tags setting is on.
- Checks each entry against the rules Eloquence follows before saving it:
  - Word roots can contain an apostrophe inside the word, as in "j'accuse".
  - German abbreviations such as "Dipl.-Ing." are accepted.
  - English abbreviations that contain a hyphen, slash, or ampersand are
    refused, because Eloquence never uses them. Use an Exact word entry instead.
  - Entries longer than Eloquence accepts are refused, because Eloquence would
    reject the whole dictionary file.
- A personal Word root entry overrides the set's Exact word entries for the same
  word, whatever their capitalization. The editor hides the overridden entries.
  A synthesizer applies this only if it supports the rule.
- Exports and imports personal entries as `.edm-dict` files, to back them up or
  share them.
- Recovers your hand edits from old Eloquence dictionary files. It looks first
  for the backup that the Eloquence add-on keeps in your NVDA configuration
  folder.
