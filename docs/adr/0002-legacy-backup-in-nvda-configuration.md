# The Eloquence migration backup lives in the NVDA configuration

When Eloquence migrates Old Eloquence Dictionary Files, it writes one backup copy to `<active NVDA configuration>/eciDictionaries/legacy/eloquence/`, and EDM's migration tool scans that folder first. We moved it from the earlier planned location, `synthDrivers/eloquence-dic-backup/` inside the Eloquence add-on, because NVDA replaces an add-on's folder on every update, so Eloquence would have had to carry the backup forward on every install. The old path never shipped, so moving it cost nothing. Agreed on [fastfinge/eloquence_64#173](https://github.com/fastfinge/eloquence_64/issues/173).

## Consequences

Eloquence becomes a second writer in the shared `eciDictionaries/` folder. That's acceptable because it writes the backup once and never changes it, and EDM only reads it. The backup also survives Eloquence being uninstalled, which is when a user is most likely to want their hand edits back.
