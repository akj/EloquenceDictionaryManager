# Licensing managed dictionary sets

Research for **Set metadata, attribution & build-time refresh**. Checked against the
upstream repositories and primary licensing sources on 2026-07-15. This is a project
policy recommendation, not legal advice.

## Current upstream status

| Dictionary set | Current license finding | May this project safely redistribute it? |
|---|---|---|
| `eigencrow/IBMTTSDictionaries` | **CC0 1.0 Universal.** The July 2026 release tree contains [`LICENSE.md`](https://github.com/eigencrow/IBMTTSDictionaries/blob/d997036dec4b5aad80ad53d8133326a67d1f41ec/LICENSE.md), whose text is CC0; GitHub also detects the repository as `CC0-1.0`. | **Yes.** CC0 permits copying, modification, and distribution, including commercial use, without permission or conditions. Attribution is not legally required, but recording source and credits remains good provenance practice. |
| `Mohamed00/AltIBMTTSDictionaries` | **No license grant found.** The [July 2026 release tree](https://github.com/Mohamed00/AltIBMTTSDictionaries/tree/ba2f946e2358378eccad760eb3e26c99da5cb10b) has no license or notice file; its [README](https://github.com/Mohamed00/AltIBMTTSDictionaries/blob/ba2f946e2358378eccad760eb3e26c99da5cb10b/README.md) and [contribution template](https://github.com/Mohamed00/AltIBMTTSDictionaries/blob/ba2f946e2358378eccad760eb3e26c99da5cb10b/.github/pull_request_template.md) contain no licensing terms. GitHub's repository API reports no detected license. | **Not yet.** Public visibility permits viewing and GitHub forking, but it is not a general redistribution license. Obtain an explicit license or written permission covering the relevant content and contributors before bundling it. |

GitHub's own licensing guidance says that, absent a license, default copyright law
applies and others may not reproduce, distribute, or create derivative works. A public
repository therefore is not by itself enough permission to ship its files in an NVDA
add-on ([GitHub Docs: Licensing a repository](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)).

The fact that dictionary entries contain facts, individual words, or short phrases does
not eliminate the need for clearance. The U.S. Copyright Office says individual words,
short phrases, and plain facts are not protected, but original expression in database
contents and original selection or arrangement of a factual compilation can be
protected ([Copyright Office: Automated Databases](https://www.copyright.gov/register/tx-databases.html)).
Creative Commons also notes that other jurisdictions can provide separate database
rights. The safe unit to license is therefore the dictionary set as a whole, not a
case-by-case guess about whether each line is copyrightable
([Creative Commons: Data](https://wiki.creativecommons.org/wiki/data)).

For `AltIBMTTSDictionaries`, simply having its maintainer add CC0 is sufficient only to
the extent that the maintainer owns or controls the relevant rights. Creative Commons
states that only a rightsholder, or someone with express authority from the
rightsholder, can apply CC0. Because the repository accepts contributions and its
current contribution template has no inbound license statement, the upstream should
confirm contributor authority or consent when it licenses existing history
([Creative Commons: About CC licenses](https://creativecommons.org/share-your-work/cclicenses/)).

## Recommended policy

Adopt a written **open-data licensing policy** for every managed set:

1. **Default project-produced dictionary data to `CC0-1.0`.** CC0 is the most
   permissive standard tool appropriate to data: it waives copyright and database
   rights as far as law permits and supplies a broad fallback license where waiver is
   ineffective. It expressly permits any purpose, including commercial use
   ([CC0 legal code](https://creativecommons.org/publicdomain/zero/1.0/legalcode.en)).
   `CC0-1.0` is the standard SPDX identifier
   ([SPDX](https://spdx.org/licenses/CC0-1.0)). Apply it to dictionary data, not to the
   add-on's program code, which should retain its own software license.
2. **Only publish third-party sets with explicit, auditable permission** to copy,
   modify, package, and redistribute the data, including commercial use. Prefer
   `CC0-1.0`; `CC-BY-4.0` can be accepted when a source insists on legally required
   attribution. Avoid `NC`, `ND`, `SA`, and bespoke terms for new sets: they are less
   permissive and add ambiguity or downstream obligations.
3. **Make inbound rights explicit.** A contribution template should say, in substance:
   *“By submitting this contribution, I apply CC0-1.0 to it and confirm that I have the
   authority to do so.”* CC0 may only be applied by someone who owns or controls the
   relevant rights, and it is irrevocable
   ([Creative Commons licensing guidance](https://creativecommons.org/cc-license-your-work/)).
4. **Carry the evidence with each set.** `set.ini` should contain the SPDX expression
   and source/license URLs, and the set directory should include the applicable license
   or permission text plus required notices. Preserve `attribution` and source/version
   metadata even for CC0: Creative Commons recommends crediting CC0 data as good
   scholarly/provenance practice although CC0 does not require it
   ([Creative Commons FAQ](https://creativecommons.org/faq/)).
5. **Fail closed.** A missing, unknown, incompatible, or unverifiable license blocks a
   set from a published build until it is resolved. `license = NOASSERTION` may describe
   an internal discovery state, but it must never qualify a set for release.

## Commercial use

If the goal is “as permissive as possible,” commercial use must remain allowed. A
NonCommercial condition would do the opposite: it introduces a purpose restriction,
and Creative Commons defines it by whether a use is primarily directed toward
commercial advantage or monetary compensation, not simply whether the user is a
for-profit entity ([Creative Commons FAQ](https://creativecommons.org/faq/)). That
ambiguity is unnecessary for dictionary data with little independent market value and
could complicate otherwise useful distribution or embedding.

CC0 does allow someone to sell a copy, but it gives them no exclusivity: everyone else
may copy, modify, and redistribute the same data, including for free. That is the
cleanest legal expression of the project's stated intent that nobody should control or
extract rents from these dictionaries.

## Decision-ready conclusion

- Keep the proposed `license` and `licenseURL` metadata fields, using SPDX expressions.
- Adopt `CC0-1.0` as the default for dictionary data and require CC0-compatible inbound
  contributions.
- Keep attribution as mandatory project metadata/provenance even when the license does
  not require it.
- Bundle `eigencrow/IBMTTSDictionaries` under its existing CC0 terms.
- Do **not** bundle `Mohamed00/AltIBMTTSDictionaries` until its existing content is
  covered by an explicit license or equivalent rights-holder permission; ask for CC0.
