# NVDA add-on template, store submission, compatibility & dictionary licensing

Research for issue #2. Primary sources only; each claim cites the file/URL that owns it.
Captured 2026-07-12 against the then-current state of the upstream repos and a local
NVDA checkout at `C:\Users\andrew\code\nvda` (NVDA `2026.3`).

---

## Blockers and open questions (read first)

1. **BLOCKER — `mohamed00/AltIBMTTSDictionaries` has no license.** The repo carries no
   `LICENSE`/`COPYING` file and no license statement anywhere (GitHub reports
   `"license": null`; the `/license` API returns HTTP 404; a recursive tree listing finds
   only `README.md`, `changelog.txt`, `doc/`, and the `.dic` data). Under default
   copyright law this is **all-rights-reserved**: we have **no right to redistribute it**,
   which is exactly what "bundle both sets inside the add-on" requires. We must obtain
   explicit written permission from the author (Mohamed) to redistribute — ideally by
   asking him to add an open license (CC0 or MIT to match the other set) to the repo —
   **before** this set can ship in the add-on. This gates the "both sets bundled" design
   in the spec (`docs/specs/dictionaries-addon.md`, layer 1).
   - Source: `gh api repos/Mohamed00/AltIBMTTSDictionaries` → `license: null`;
     `gh api repos/Mohamed00/AltIBMTTSDictionaries/license` → 404;
     tree of `master` contains no license file. README:
     https://github.com/Mohamed00/AltIBMTTSDictionaries/blob/master/README.md (no
     license/permission text).

2. **`eigencrow/IBMTTSDictionaries` is clear to bundle** — CC0-1.0 (public-domain
   dedication). No blocker. See licensing section.

3. **Which template repo is canonical is mid-migration.** The long-standing community
   template `nvdaaddons/AddonTemplate` now redirects users to **`nvaccess/AddonTemplate`**
   (a fork NV Access created 2025-11-24 and is actively maintaining). Recommend building on
   `nvaccess/AddonTemplate`. See template section for the nuance.

4. **Open (product-side, not blocking):** the store `addonId`/`name` and the `publisher`
   string still need to be chosen (spec open question 5); and whoever submits must be, or
   get authorized by, an approved store submitter (approval can take up to ~2 weeks).

---

## 1. What the NV Access add-on template gives us for free

**Which repo:** Use **`nvaccess/AddonTemplate`** (GPL-2.0, GitHub "template" repo).
It is a fork of the historical community template `nvdaaddons/AddonTemplate`; the latter's
own `readme.md` now says: *"as of December 1, 2025, nvdaaddons/addonTemplate repository is
archived. Please use nvaccess/AddonTemplate repository."* Both repos are still live and
their contents are effectively in sync, but NV Access is the going-forward maintainer.
- Sources: `gh api repos/nvaccess/AddonTemplate` (`fork: true`, `parent:
  nvdaaddons/AddonTemplate`, `is_template: true`, `license: gpl-2.0`);
  `nvdaaddons/AddonTemplate/readme.md` line 3 (redirect note).

The template is a **SCons-based build kit**. Concretely it provides:

- **Centralized build metadata** in `buildVars.py` — a single `AddonInfo` dict with:
  `addon_name`, `addon_summary`, `addon_description`, `addon_version`, `addon_changelog`,
  `addon_author`, `addon_url`, `addon_sourceURL`, `addon_docFileName`,
  `addon_minimumNVDAVersion`, `addon_lastTestedNVDAVersion`, `addon_updateChannel`,
  `addon_license`, `addon_licenseURL`; plus `pythonSources`, `i18nSources`,
  `excludedFiles`, `baseLanguage`, `markdownExtensions`, `brailleTables`,
  `symbolDictionaries`. (Source: `AddonTemplate/buildVars.py`.)
- **Manifest generation.** `manifest.ini.tpl` is string-formatted with the buildVars to
  produce the `manifest.ini` NVDA reads (`name`, `summary`, `description`, `author`, `url`,
  `version`, `changelog`, `docFileName`, `minimumNVDAVersion`, `lastTestedNVDAVersion`,
  `updateChannel`). Custom `brailleTables`/`symbolDictionaries` sections are appended
  programmatically. (Sources: `AddonTemplate/manifest.ini.tpl`,
  `site_scons/site_tools/NVDATool/manifests.py`.)
- **gettext / localization wiring** (this is the l10n our AGENTS.md requires, done for us):
  - `scons pot` extracts a `.pot` from `i18nSources` (defaults to `pythonSources +
    ["buildVars.py"]`), so buildVars' own translatable summary/description/changelog are
    included. (Source: `AddonTemplate/sconstruct` `pot`/`mergePot` targets;
    `buildVars.i18nSources`.)
  - Translators drop `addon/locale/<lang>/LC_MESSAGES/nvda.po`; the build compiles each to
    `.mo` (`gettextMoFile`). (Source: `sconstruct` per-lang loop.)
  - **Per-language translated manifests** are generated from each `.mo` +
    `manifest-translated.ini.tpl` (translates `summary`/`description`/`changelog`), so the
    store shows localized listing text. (Sources: `sconstruct`,
    `manifests.py:generateTranslatedManifest`, `manifest-translated.ini.tpl`.)
  - pot bug-report address is preset to `nvda-translations@groups.io`. (Source:
    `sconstruct` `gettextvars`.)
- **Docs pipeline:** Markdown docs (`addon/doc/<lang>/*.md`, plus a root `readme.md`) are
  converted to HTML (with optional `style.css` and per-language title translation), wiring
  up the add-on's Help button. (Source: `sconstruct` md2html section.)
- **Packaging:** produces `${addon_name}-${addon_version}.nvda-addon` from the `addon/`
  tree, honoring `excludedFiles`. Version can be overridden on the CLI; `dev=1` names the
  build `YYYYMMDD.0.0` and sets channel `dev`. **Version is validated to be
  `major.minor.patch` integers** to satisfy the store. (Source: `sconstruct`
  `validateVersionNumber`, `NVDAAddon` builder.)
- **CI/release via GitHub Actions** (`.github/workflows/build_addon.yml`):
  - Triggers on tag push, PRs to `main`/`master`, and manual `workflow_dispatch`.
  - Ubuntu runner, Python 3.11, installs `pre-commit scons markdown` + `gettext`; runs
    `pre-commit run --all` (code checks), then `scons && scons pot`; uploads the
    `.nvda-addon` and `.pot` as artifacts.
  - **On a pushed tag** it creates a GitHub Release, appends the `.nvda-addon` SHA256 to
    `changelog.md`, and uploads the `.nvda-addon` + `.pot` as release assets;
    prerelease if the tag contains `-`. (Source: `build_addon.yml`.)
- **Lint/type-check config:** `pyproject.toml` ships Ruff + Pyright config; `.vscode/` is
  preconfigured (expects an NVDA checkout as a sibling dir); a `.pre-commit-config.yaml`
  runs `check-ast`, `check-case-conflict`, `check-yaml`; `dependabot.yml` is included.
  (Sources: `AddonTemplate/readme.md` "Additional tools"; `.pre-commit-config.yaml`.)
- **Tooling requirements** the template states: Python 3.13 64-bit recommended, SCons
  ≥ 4.10.1, GNU gettext, Markdown ≥ 3.8.2. (Source: `AddonTemplate/readme.md` Requirements.)

## 2. What we must add (template does NOT provide)

- **All add-on functionality.** The template ships an empty `addon/` tree. Everything in
  the spec — the settings panel (active-set dropdown, per-language overlay toggles), the
  entry editor with CP1252 validation + live preview, the migration import tool, the
  contract/`contract.ini` marker file, and the discovery glue — is ours to write under
  `addon/globalPlugins/` (or `settingsDialogs`) etc.
- **The bundled dictionary payload.** Both `.dic` sets under
  `addon/dictionaries/<set-id>/`, plus the build-time fetch/submodule step that refreshes
  them from upstream (spec: "build-time step … not a runtime feature"). Not a template
  feature.
- **`addonHandler.initTranslation()` per module + `# Translators:` comments.** The template
  gives the extraction/compile machinery, but marking strings NVDA-style in our source is
  on us (per AGENTS.md). buildVars' fake `_()` is only for the metadata strings.
- **Filling in `buildVars.py`** with real name/summary/description/author/URLs/license/
  version and the NVDA min/lastTested versions (section 3).
- **A LICENSE/COPYING for our add-on** and, given we bundle third-party content, an
  attribution/credits file (section 5). The template's own `COPYING.txt` is GPL-2.0 for the
  *template*, not a license for our add-on.
- **Tests.** No unit-test scaffold is provided beyond the pre-commit `check-ast`.
- **Store submission** itself (section 4) — the template stops at producing the
  `.nvda-addon`; it does not talk to the store.

## 3. Recommended NVDA compatibility range

**Recommendation: `minimumNVDAVersion = 2026.1.0`, `lastTestedNVDAVersion = 2026.3.0`**
(bump `lastTested` on each NVDA release you re-test against).

How NVDA gates add-on loading (the mechanics that make this the right choice):
- `isAddonCompatible = hasAddonGotRequiredSupport AND isAddonTested`, where
  `hasAddonGotRequiredSupport` ⇔ `addon.minimumNVDAVersion <= CURRENT` and `isAddonTested`
  ⇔ `addon.lastTestedNVDAVersion >= BACK_COMPAT_TO`, both evaluated against the *running*
  NVDA. (Source: `nvda/source/addonHandler/addonVersionCheck.py`.)
- On the local NVDA checkout: `CURRENT = 2026.3.0`, and
  `BACK_COMPAT_TO = (2026, 1, 0)`. (Sources: `nvda/source/buildVersion.py`
  `version_year=2026, version_major=3, version_minor=0`; `nvda/source/addonAPIVersion.py`
  `BACK_COMPAT_TO = (2026, 1, 0)`.)
- Meaning: to load on today's NVDA (2026.3) an add-on's `lastTestedNVDAVersion` must be
  `>= 2026.1.0`, and its `minimumNVDAVersion` must be `<= 2026.3.0`.

Why `2026.1.0` as the floor:
- **2026.1 is a hard API break and NVDA's current back-compat floor.** `addonAPIVersion.py`
  records `(2026, 1, 0): Upgrade to python 3.13 and migration to 64bit from 32bit`. NVDA
  releases before 2026.1 run Python 3.11 / 32-bit; the current add-on template targets
  Python 3.13 / 64-bit. Supporting anything below 2026.1 means building and testing on the
  old runtime line.
- **This is a brand-new add-on with zero legacy install base** — there is no existing user
  on old NVDA to keep working. Nothing in the spec needs APIs older than 2026.1.
- Choosing `2026.1.0` keeps the add-on out of NVDA's "incompatible / needs override"
  bucket on all current and near-future NVDA (any NVDA whose `BACK_COMPAT_TO` is
  `<= 2026.1` treats it as tested).
- **Tradeoff to flag:** the spec notes the same dictionary sets are consumed by
  davidacm's NVDA-IBMTTS-Driver, and floats serving those users. If serving pre-2026.1
  NVDA ever becomes a goal, `minimumNVDAVersion` could be lowered (e.g. `2024.1.0` or
  `2025.1.0`) — but only if we actually build/test against that older Python-3.11 API line,
  which is a real, recurring cost for a pure-settings/editor add-on. Recommend **not**
  doing this for v1; revisit only if there's concrete demand.

`year.major` vs `year.major.minor`: the manifest/store accept `major.minor` or
`major.minor.patch` for versions and the year-based `YYYY.N[.N]` form for NVDA versions
(regex `^(0|\d{4})\.(\d)(?:\.(\d))?$`). Use the three-part `2026.1.0` / `2026.3.0` form to
be explicit. (Source: `nvda/source/addonAPIVersion.py` `ADDON_API_VERSION_REGEX`;
`AddonTemplate/readme.md` manifest spec.)

## 4. Add-on store submission checklist (for this add-on)

Store repo: **`nvaccess/addon-datastore`** (`https://addonstore.nvaccess.org/`). Submission
guide: `docs/submitters/submissionGuide.md`. (Sources: `gh api repos/nvaccess/addon-datastore`;
that repo's `README.md` and `docs/submitters/submissionGuide.md`.)

Process & policy:
- **Submission is via a GitHub issue form** ("Add-on registration" template) on
  `nvaccess/addon-datastore`; automated validation runs on the resulting PR and comments
  errors. (Source: `submissionGuide.md`.)
- **Approved-submitter gate.** NV Access keeps a list of approved submitters
  (`submitters.json`); publishers are approved per-add-on, and **first-time approval can
  take up to ~2 weeks**. Future updates to an already-approved add-on don't need
  re-approval. If you don't own the add-on's repo you must have the authors' authorization
  to publish. (Sources: `README.md`, `submissionGuide.md`.)
- **VirusTotal scan** is run on every submitted `.nvda-addon`; **SHA256 checksum** pins file
  integrity/immutability. Malicious add-ons are rejected/removed. (Sources: `README.md`,
  `submissionGuide.md`, and the `scanResults`/`sha256` fields in every published entry.)
- **Code of Conduct** ("Citizen and Contributor Code of Conduct") applies; violations can be
  removed by PR or by emailing `info@nvaccess.org`. (Source: `README.md`.)
- **Not a lock-in:** the store "does not restrict add-on authors from developing,
  publishing, and distributing an add-on outside this store." No mandatory human
  code/UX review before listing. The catalog data is Open-Data-Commons licensed. (Source:
  `README.md`.)
- **Open source is not strictly required**, but `sourceURL`, `license`, and `licenseURL`
  are expected metadata fields (present in every entry). Plan to ship as GPL-2.0-or-later
  (matches template lineage) with a public `sourceURL`.

Metadata the submission entry carries (from a real published entry —
`addons/AIContentDescriber/2023.11.23.json`): `addonId`, `displayName`, `URL` (a direct
`https://…/*.nvda-addon` download), `description`, `sha256`, `addonVersionName`,
`addonVersionNumber {major,minor,patch}`, `minNVDAVersion {major,minor,patch}`,
`lastTestedVersion {major,minor,patch}`, `channel` (`stable`/`beta`/`dev`), `publisher`,
`sourceURL`, `license`, `licenseURL`, `translations`, plus store-added `reviewUrl`,
`vtScanUrl`, `scanResults`. Validation rules of note: all URLs must be `https://`; the
download URL must end `.nvda-addon` and actually download; `name` must be unique and only
letters/numbers/underscores/hyphens; version must be `major.minor[.patch]`;
`minimumNVDAVersion`/`lastTestedNVDAVersion` must be valid NVDA API versions; beta/alpha
builds must use `channel` `beta`/`dev`. (Sources: `submissionGuide.md`; example JSON.)

**Our concrete pre-submission checklist:**
- [ ] Resolve the AltIBMTTS license blocker (section 1/5) — do **not** submit a build that
      bundles unlicensed content.
- [ ] Pick a unique `addonId`/`name` (camelCase, unique in the store) and a `publisher`.
- [ ] Fill `buildVars.py`: summary, description, changelog, author, `addon_url`,
      `addon_sourceURL`, `addon_license = "GPL v2"` (or chosen), `addon_licenseURL`,
      `minimumNVDAVersion = "2026.1.0"`, `lastTestedNVDAVersion = "2026.3.0"`.
- [ ] Tag a release; let the template's Actions workflow build the `.nvda-addon` + compute
      SHA256 and publish a GitHub Release (gives the direct `https://…/*.nvda-addon` URL).
- [ ] Get an approved submitter (or become one) and file the "Add-on registration" issue
      form; expect VirusTotal scan + automated validation on the PR.
- [ ] Ship credits/attribution + bundled-content licenses inside the add-on (section 5).

## 5. Licensing & attribution obligations for the bundled dictionaries

Both sets are **content** (word→pronunciation `.dic` data), so redistribution rights hinge
on each repo's own license.

### `eigencrow/IBMTTSDictionaries` — VERDICT: clear to bundle (CC0-1.0)
- Licensed **CC0 1.0 Universal** (public-domain dedication) via a `LICENSE.md` in the repo.
  CC0 waives copyright worldwide, so we may bundle, modify, and redistribute freely, for any
  purpose, with **no legal attribution requirement**. (Sources:
  `gh api repos/eigencrow/IBMTTSDictionaries` → `license.spdx_id: CC0-1.0`;
  `https://github.com/eigencrow/IBMTTSDictionaries/blob/master/LICENSE.md`.)
- **Obligation:** none legally. **Do anyway:** credit "IBMTTSDictionaries by eigencrow
  (CC0-1.0)" in the add-on's readme/credits — good practice and matches the community
  norm, though CC0 does not compel it.

### `mohamed00/AltIBMTTSDictionaries` — VERDICT: CANNOT bundle as-is (no license)
- **No license of any kind.** No `LICENSE`/`COPYING`, no license/permission/redistribution
  statement in the README or elsewhere. GitHub: `"license": null`; `/license` API → 404;
  the only non-data/non-doc file in the tree is `README.md`. (Sources:
  `gh api repos/Mohamed00/AltIBMTTSDictionaries`;
  `.../license` → 404; recursive tree of `master`;
  `https://github.com/Mohamed00/AltIBMTTSDictionaries/blob/master/README.md`.)
- **Implication (do not paper over):** absent a license, the work is **all rights reserved**
  by default copyright. GitHub's terms grant other users only the right to *view and fork
  within GitHub* — **not** to redistribute outside it. Bundling these files in our
  `.nvda-addon` and distributing via the store is redistribution and would infringe unless
  the author grants permission.
- **Required action before shipping this set:** get explicit permission from the author
  (Mohamed) to redistribute — the clean fix is to ask him to add an open license to the
  repo (CC0 or MIT, to match the other set). Until then, options are: (a) ship v1 with only
  the CC0 IBMTTSDictionaries set and add AltIBMTTS once licensed, or (b) hold "both sets
  bundled" until permission lands. This is a hard gate on the spec's layer-1 design.

### Store-side note on third-party content
The store expects submitters to have the right to publish what they submit ("it is expected
that you have authorisation to publish the add-on from the authors") and enforces a Code of
Conduct; there is no separate automated license check on *bundled* content, but shipping
unlicensed third-party data is our legal exposure regardless. (Source:
`addon-datastore/docs/submitters/submissionGuide.md`, `README.md`.)

### Recommended attribution artifact
Ship a `copyright`/`credits` doc inside the add-on listing, per set: repo name, author,
license (with URL), and the upstream commit/date the bundled snapshot was taken from
(useful anyway for the migration tool's "union of historical upstream versions" diff, spec
§ Migration import tool). For CC0 this is courtesy; for AltIBMTTS it should record the
granted permission once obtained.

---

## Source index

| Claim area | Source |
|---|---|
| Template repo (current) | `gh api repos/nvaccess/AddonTemplate` (fork of `nvdaaddons/AddonTemplate`, `is_template`, GPL-2.0) |
| Template redirect note | `nvdaaddons/AddonTemplate/readme.md` line 3 |
| Build metadata / l10n vars | `AddonTemplate/buildVars.py` |
| Manifest generation | `AddonTemplate/manifest.ini.tpl`, `manifest-translated.ini.tpl`, `site_scons/site_tools/NVDATool/manifests.py` |
| Build/pot/docs pipeline | `AddonTemplate/sconstruct` |
| CI/release | `AddonTemplate/.github/workflows/build_addon.yml` |
| Tooling reqs, features, manifest spec | `AddonTemplate/readme.md` |
| NVDA current version | `nvda/source/buildVersion.py` (2026.3.0) |
| API break / back-compat floor | `nvda/source/addonAPIVersion.py` (`BACK_COMPAT_TO=(2026,1,0)`) |
| Compatibility gate logic | `nvda/source/addonHandler/addonVersionCheck.py` |
| Store repo / policy | `gh api repos/nvaccess/addon-datastore`; `README.md` |
| Submission process/fields | `addon-datastore/docs/submitters/submissionGuide.md`; example `addons/AIContentDescriber/2023.11.23.json` |
| IBMTTSDictionaries license | `gh api repos/eigencrow/IBMTTSDictionaries` (CC0-1.0); `LICENSE.md` |
| AltIBMTTSDictionaries license | `gh api repos/Mohamed00/AltIBMTTSDictionaries` (`license: null`); `/license` → 404; repo tree/README |
