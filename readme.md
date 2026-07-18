# Eloquence Dictionary Manager

Eloquence Dictionary Manager is an NVDA add-on for distributing community
Eloquence pronunciation dictionary sets and editing personal dictionary entries.
The add-on is under active development; the current dialog is a placeholder for
the entry editor described in the project specification.

## Development

This repository uses the official
[NV Access AddonTemplate](https://github.com/nvaccess/AddonTemplate). The build
requires Python 3.13, GNU gettext, and the dependencies declared in
`pyproject.toml`.

Install the development dependencies and build the add-on with:

```powershell
uv sync
uv run scons
```

The package is written to the repository root as
`eloquenceDictionaryManager-0.1.0.nvda-addon`.

Generate the gettext template with:

```powershell
uv run scons pot
```

The generated catalog is `eloquenceDictionaryManager.pot`.

Project behavior and packaging requirements are documented in
[`docs/specs/dictionaries-addon.md`](docs/specs/dictionaries-addon.md).

## License

The add-on scaffold and source are licensed under the GNU General Public License,
version 2 or later. See [COPYING.txt](COPYING.txt).
