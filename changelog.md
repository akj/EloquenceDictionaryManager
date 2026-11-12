# 0.1.0

First release.

- Bundles the v26.11 release of the IBMTTSDictionaries pronunciation set
  curated by eigencrow. It works as soon as the add-on is installed.
- Adds the **Eloquence Dictionary Entries** editor. Open it from the NVDA menu:
  **Preferences**, then **Eloquence dictionaries...**. You can add, edit, and
  remove your own entries, and customize any entry in the bundled set without
  changing the set itself.
- Plays the current and the new pronunciation of an entry when Eloquence or
  OpenEVV is your synthesizer.
- Checks each entry against the rules Eloquence follows before saving it:
  - Word roots can contain an apostrophe inside the word, as in "j'accuse".
  - German abbreviations such as "Dipl.-Ing." are accepted.
  - English abbreviations that contain a hyphen, slash, or ampersand are
    refused, because Eloquence never uses them. Use an Exact word entry instead.
  - Entries longer than Eloquence accepts are refused, because Eloquence would
    reject the whole dictionary file.
- A personal Word root entry overrides the set's Exact word entries for the same
  word, whatever their capitalization, so you hear your entry.
- Exports and imports personal entries as `.edm-dict` files, to back them up or
  share them.
- Recovers your hand edits from old Eloquence dictionary files. It looks first
  for the backup that the Eloquence add-on keeps in your NVDA configuration
  folder.
