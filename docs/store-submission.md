# NVDA add-on store submission

How to release Eloquence Dictionary Manager and register it in the NVDA add-on
store. The store is [`nvaccess/addon-datastore`](https://github.com/nvaccess/addon-datastore).
Its [submission guide](https://github.com/nvaccess/addon-datastore/blob/master/docs/submitters/submissionGuide.md)
and [Add-on registration form](https://github.com/nvaccess/addon-datastore/blob/master/.github/ISSUE_TEMPLATE/registerAddon.yml)
are the primary sources for this page.

## Release metadata

These values come from `buildVars.py` and end up in the add-on's manifest.

| Field | Value |
| --- | --- |
| Add-on ID (`addon_name`) | `eloquenceDictionaryManager` |
| Version (`addon_version`) | `0.1.0` |
| Minimum NVDA version | `2026.1.0` |
| Last tested NVDA version | `2026.3.0` |
| Update channel (`addon_updateChannel`) | `None`, which means stable |

The store checks that the minimum and last tested versions are listed in
[`nvdaAPIVersions.json`](https://github.com/nvaccess/addon-datastore/blob/master/transform/nvdaAPIVersions.json).
A **stable** submission must also name stable NVDA releases in both fields.
Raise the last tested version only after testing on that NVDA release.

NVDA does not read `updateChannel` from the manifest, and the store does not
check it. The channel that counts is the one chosen in the registration form.
Keep the two the same. For a beta or dev release, set `addon_updateChannel` to
`"beta"` or `"dev"` and choose the same channel in the form.

## Registration form answers

| Form field | Answer |
| --- | --- |
| Download URL | `https://github.com/akj/EloquenceDictionaryManager/releases/download/v0.1.0/eloquenceDictionaryManager-0.1.0.nvda-addon` |
| Source URL | <https://github.com/akj/EloquenceDictionaryManager> |
| Publisher | The publisher's name, chosen at submission |
| Channel | `stable` |
| License Name | `GPL v2 or later` (replace the form's default, `GPL v2`) |
| License URL | <https://github.com/akj/EloquenceDictionaryManager/blob/main/COPYING.txt> (replace the form's default GNU URL) |

The form has no SHA256 field. The store downloads the file from the Download
URL and calculates its SHA256 itself. The release notes list the same SHA256, so
you can compare the two.

## Bundled-content provenance and licensing

The package bundles the `github.eigencrow.ibmtts-dictionaries` set from
[eigencrow IBMTTSDictionaries](https://github.com/eigencrow/IBMTTSDictionaries).
The bundled dictionary data is licensed separately from the add-on software
under CC0-1.0, a public domain dedication. Its upstream license is
[`LICENSE.md`](https://github.com/eigencrow/IBMTTSDictionaries/blob/9c6c401a7aa12f28a41829dddb007fdc46b97730/LICENSE.md).

[mohamed00 AltIBMTTSDictionaries](https://github.com/Mohamed00/AltIBMTTSDictionaries)
is not bundled and has no redistribution license grant. Only hashes derived
from its history are used as migration-history provenance data in the
historical-union artifact; no AltIBMTTSDictionaries dictionary content is
included in the package.

## Store description

> Eloquence Dictionary Manager bundles the community IBMTTSDictionaries Eloquence pronunciation dictionary set curated by eigencrow, ready to use as soon as the add-on is installed. Its editor lets you add and customize your own pronunciations with spoken previews, export and import .edm-dict files to share or back up personal entries, and recover your hand edits from Eloquence dictionary files used before this add-on. The add-on software is licensed under the GNU General Public License, version 2 or later. The bundled dictionary data is licensed separately under CC0-1.0, a public domain dedication. The migration feature uses only content hashes derived from the history of mohamed00's AltIBMTTSDictionaries; that set's dictionary content is not bundled.

The paragraph above is copied verbatim from the English source string for
`addon_description` in `buildVars.py`.

## Release and submission steps

1. Test the add-on on the newest stable NVDA release. If that release is newer
   than the last tested version above, set `addon_lastTestedNVDAVersion` in
   `buildVars.py` to it, and merge that change.
2. Check that `addon_version` in `buildVars.py` and the top heading in
   `changelog.md` both name the version you are releasing.
3. Push a tag named `v` followed by that version, for example `v0.1.0`, on the
   commit to release. The build does not read the tag, so a tag that does not
   match `addon_version` publishes a file with a different version. A tag that
   contains `-` is published as a prerelease.
4. Wait for the **build addon** workflow run for that tag to finish. Its
   `upload_release` job creates a GitHub release with the `.nvda-addon` file,
   the `.pot` translation template, and `changelog.md` as release notes, with
   the file's SHA256 added at the end.
5. Check the release: the file name contains the right version, and the
   release notes show the SHA256.
6. Open the [Add-on registration form](https://github.com/nvaccess/addon-datastore/issues/new?template=registerAddon.yml)
   and fill it in with the answers above.
7. Wait for the store's checks. A first submission of an add-on needs manual
   approval of the publisher, which can take up to 2 weeks. The store also
   scans the file with VirusTotal. If a check fails, the store comments on the
   issue. Fix the problem and submit the form again.
