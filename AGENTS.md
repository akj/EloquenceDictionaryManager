# Eloquence Dictionaries add-on

NVDA add-on (working name **Eloquence Dictionaries**) that owns distribution of community
Eloquence pronunciation dictionary sets and an editor for personal entries. Split out of the
Eloquence synth-driver add-on; see `docs/specs/dictionaries-addon.md` for the origin design.

Standing constraints:

- Built on the official NV Access add-on template; distributed through the NVDA add-on store.
- UX must be NVDA-idiomatic — the NVDA source at `../nvda` is the pattern reference.
- Every user-visible string uses NVDA's gettext pattern (this add-on will be translated).

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues, driven via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary — `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
