# Eloquence Dictionaries

This context describes the dictionary content shared by the Eloquence Dictionary Manager add-on and the synthesizer add-ons that use it.

## Language

**Managed Dictionary Set**:
A named collection of community-maintained ECI pronunciation entries that a synthesizer can turn on for a language. A copy installed by a Dictionary Provider and a copy a synthesizer downloads for the user are the same set when they share a Managed Dictionary Set ID.
_Avoid_: Downloaded dictionaries, dictionary source

**Managed Dictionary Set ID**:
The globally unique, immutable identity of a Managed Dictionary Set, independent of its display name, source location, or packaging provider.
_Avoid_: Set directory name, source repository name

**Dictionary Provider**:
An installed add-on that publishes Managed Dictionary Sets as static content through the directory contract.
_Avoid_: Dictionary source, dictionary add-on

**Dictionary Consumer**:
A synthesizer add-on that discovers Managed Dictionary Sets and the Personal Dictionary Overlay, decides which apply to each language, and loads them into the engine.
_Avoid_: Client, host

**Personal Dictionary Overlay**:
The user-owned ECI pronunciation entries, shared by every Dictionary Consumer, that supplement or override the Managed Dictionary Sets in use for a language.
_Avoid_: User dictionaries, custom dictionaries, own files

**Old Eloquence Dictionary Files**:
Dictionary files from Eloquence versions that mixed downloaded entries and the user's hand edits in one file.
_Avoid_: Legacy dictionaries, user dictionaries
