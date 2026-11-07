# One row per set ID, and the installed provider's copy wins

A Managed Dictionary Set can reach a synth twice: pinned and reviewed inside an installed Dictionary Provider such as EDM, and as the synth's own runtime download of the same upstream repository. Both copies carry the same Managed Dictionary Set ID, because the ID names the dataset, not where a copy came from. We decided that a synth shows one row for that ID and uses the provider's copy, so the same dataset is never stacked twice and the reviewed copy is the one users hear. Agreed with the Eloquence maintainers on [fastfinge/eloquence_64#173](https://github.com/fastfinge/eloquence_64/issues/173).

## Considered options

- **Two rows, one per copy.** Rejected: stacking two revisions of one dataset applies it twice and leaves users to work out which row matters.
- **The newer revision wins.** Rejected: comparing revisions across providers needs new contract fields for little gain.

## Consequences

Upstream corrections reach users who have EDM installed only when EDM publishes a refresh, even if the synth could download a newer copy. To keep that delay short, EDM aims to publish a refresh for each upstream release tag, so the curators' tags set the pace.
