# Set IDs for downloaded repositories are derived, and encode what they can't keep

A synth that downloads a GitHub repository as a Managed Dictionary Set needs an ID for it that every synth derives the same way and that fits the ID pattern `^[a-z0-9][a-z0-9.-]*$`. The Eloquence design on [fastfinge/eloquence_64#173](https://github.com/fastfinge/eloquence_64/issues/173) proposed `github.<owner>.<repo>`, lowercased. That breaks on repository names with `_`, which the pattern rejects, and on names with `.` once a sub-folder such as `IBMTTS 6.7` in AltIBMTTSDictionaries becomes a set of its own. We decided to keep `github.<owner>.<repo>` for the common case and to percent-encode everything else, with `.` in place of `%`. A sub-folder set appends `..` and its encoded folder path. The two registered repositories keep their IDs. Anything EDM registers later takes its derived ID, and the two repositories whose derived IDs would equal the registered ones get no ID.

## Considered options

- **Replace `_` and `.` with `-`.** Rejected: `foo_bar`, `foo.bar`, and `foo-bar` can be three different repositories from one owner, and they would share an ID.
- **A short hash of the repository and folder.** Rejected: unreadable, and a hash only makes collisions unlikely rather than impossible.
- **GitHub's numeric repository ID.** Rejected: nobody can read it, and it needs an API call before the download, although it would survive renames and transfers.
- **A colon or slash before the folder, as asked on the Eloquence issue.** Rejected: neither fits the ID pattern, and both are awkward in folder names.

## Consequences

Repository names with only letters, digits, and hyphens keep the ID the Eloquence design announced. Other names, and most folder names, give IDs such as `github.mohamed00.alt-ibmtts-dictionaries..ibmtts.206.2e7` that are hard to read, but users see a set's `name`, not its ID. The rule assigns an ID when a synth first downloads a repository. What a synth does when that repository is later renamed or transferred is left open, as it was under the Eloquence design.
