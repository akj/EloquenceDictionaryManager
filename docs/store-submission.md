# NVDA add-on store submission preparation

Prepared answers for the `nvaccess/addon-datastore` **Add-on registration**
GitHub issue form. Release-specific fields are deliberately left for the actual
submission.

## Source and software license

- Source URL: <https://github.com/akj/EloquenceDictionaryManager>
- Software license: GPL v2 or later
- Software license URL:
  <https://github.com/akj/EloquenceDictionaryManager/blob/main/COPYING.txt>
- Minimum NVDA version: `2026.1.0`
- Last tested NVDA version: `2026.3.0`

These values are copied from `addon_sourceURL`, `addon_license`,
`addon_licenseURL`, `addon_minimumNVDAVersion`, and
`addon_lastTestedNVDAVersion` in `buildVars.py`.

## Bundled-content provenance and licensing

The package bundles the `github.eigencrow.ibmtts-dictionaries` set from
[eigencrow IBMTTSDictionaries](https://github.com/eigencrow/IBMTTSDictionaries).
The bundled dictionary data is licensed separately from the add-on software
under CC0-1.0, a public domain dedication. Its upstream license is
[`LICENSE.md`](https://github.com/eigencrow/IBMTTSDictionaries/blob/d997036dec4b5aad80ad53d8133326a67d1f41ec/LICENSE.md).

[mohamed00 AltIBMTTSDictionaries](https://github.com/Mohamed00/AltIBMTTSDictionaries)
is not bundled and has no redistribution license grant. Only hashes derived
from its history are used as migration-history provenance data in the
historical-union artifact; no AltIBMTTSDictionaries dictionary content is
included in the package.

## Store description

> Eloquence Dictionary Manager bundles the community IBMTTSDictionaries Eloquence pronunciation dictionary set curated by eigencrow, ready to use as soon as the add-on is installed. Its editor lets you add and customize your own pronunciations with spoken previews, export and import .edm-dict files to share or back up personal entries, and recover your hand edits from Eloquence dictionary files used before this add-on. The add-on software is licensed under the GNU General Public License, version 2 or later. The bundled dictionary data is licensed separately under CC0-1.0, a public domain dedication. The migration feature uses only content hashes derived from the history of mohamed00's AltIBMTTSDictionaries; that set's dictionary content is not bundled.

The paragraph above is copied verbatim from the English source string for
`addon_description` in `buildVars.py`.

## Steps for the actual submission

- Confirm that the publisher has approved-submitter status for this add-on, or
  complete the approval process before submission.
- Tag a release. The release workflow then builds and publishes the downloadable
  `.nvda-addon` file and computes its SHA256 checksum. There is no release URL or
  release SHA256 to record during this readiness change.
- File the **Add-on registration** issue using the release download URL and
  SHA256. The datastore runs compatibility and metadata validation and submits
  the package to VirusTotal automatically. The VirusTotal result and scan URL
  are produced at submission time, not now.
