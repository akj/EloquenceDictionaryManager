from __future__ import annotations

from pathlib import Path

import pytest

from ecidic.model import Entry, Slot
from ecidic.sets import discover_managed_sets


REQUIRED_METADATA = {
	"name": "Example Dictionaries",
	"source_url": "https://example.com/source",
	"source_version": "v1.2.3",
	"source_revision": "0123456789abcdef0123456789abcdef01234567",
	"attribution": "Example contributors",
	"license": "CC0-1.0",
	"license_url": "https://example.com/license",
}


def _write_provider_contract(root: Path, *, version: str = "1", extra: str = "") -> None:
	dictionaries = root / "dictionaries"
	dictionaries.mkdir(parents=True)
	_ = (dictionaries / "contract.ini").write_text(
		f"[contract]\nformat = eci-dictionary-sets\nversion = {version}\n{extra}",
		encoding="utf-8",
	)


def _write_set(
	provider: Path,
	set_id: str,
	*,
	metadata: dict[str, str] | None = None,
	directory_name: str | None = None,
	extra: str = "",
) -> Path:
	values = dict(REQUIRED_METADATA)
	if metadata is not None:
		values.update(metadata)
	set_directory = provider / "dictionaries" / "sets" / (directory_name or set_id)
	set_directory.mkdir(parents=True)
	lines = ["[set]", f"id = {set_id}"]
	lines.extend(f"{key} = {value}" for key, value in values.items())
	if extra:
		lines.append(extra)
	_ = (set_directory / "set.ini").write_text("\n".join(lines) + "\n", encoding="utf-8")
	return set_directory


def test_valid_provider_loads_metadata_entries_and_ignores_unrecognized_files(tmp_path: Path) -> None:
	provider = tmp_path / "provider"
	_write_provider_contract(provider, extra="future_option = accepted\n")
	set_directory = _write_set(provider, "github.example.dictionaries", extra="future_field = accepted")
	_ = (set_directory / "enumain.dic").write_bytes(b"word\tfirst\nword\tlast\n")
	_ = (set_directory / "deuroot.dic").write_bytes(b"Haus\thouse\textra invalid field\n")
	_ = (set_directory / "enuext.dic").write_bytes(b"ignored\textended\n")
	_ = (set_directory / "chsmain.dic").write_bytes(b"ignored\tasian\n")
	_ = (set_directory / "readme.txt").write_text("ignored", encoding="utf-8")

	sets, diagnostics = discover_managed_sets([provider])

	assert diagnostics == ()
	assert len(sets) == 1
	managed_set = sets[0]
	assert managed_set.id == "github.example.dictionaries"
	assert managed_set.name == REQUIRED_METADATA["name"]
	assert managed_set.source_url == REQUIRED_METADATA["source_url"]
	assert managed_set.source_version == REQUIRED_METADATA["source_version"]
	assert managed_set.source_revision == REQUIRED_METADATA["source_revision"]
	assert managed_set.attribution == REQUIRED_METADATA["attribution"]
	assert managed_set.license == REQUIRED_METADATA["license"]
	assert managed_set.license_url == REQUIRED_METADATA["license_url"]
	assert managed_set.entries_for("enu", Slot.MAIN) == (Entry("word", "last"),)
	assert managed_set.entries_for("deu", Slot.ROOT) == (Entry("Haus", "house\textra invalid field"),)


def test_invalid_set_does_not_hide_valid_sibling(tmp_path: Path) -> None:
	provider = tmp_path / "provider"
	_write_provider_contract(provider)
	invalid = _write_set(provider, "github.invalid.set")
	_ = (invalid / "set.ini").write_text("[set]\nid = github.invalid.set\n", encoding="utf-8")
	valid = _write_set(provider, "github.valid.set")
	_ = (valid / "enumain.dic").write_bytes(b"valid\tentry\n")

	sets, diagnostics = discover_managed_sets([provider])

	assert [managed_set.id for managed_set in sets] == ["github.valid.set"]
	assert len(diagnostics) == 1
	assert diagnostics[0].path == invalid
	assert "required field" in diagnostics[0].reason


@pytest.mark.parametrize(
	("set_id", "directory_name", "reason"),
	(
		("github.other.set", "github.expected.set", "does not match"),
		("Invalid_Set", None, "invalid shape"),
	),
)
def test_invalid_set_identity_is_skipped(
	tmp_path: Path,
	set_id: str,
	directory_name: str | None,
	reason: str,
) -> None:
	provider = tmp_path / "provider"
	_write_provider_contract(provider)
	_ = _write_set(provider, set_id, directory_name=directory_name)

	sets, diagnostics = discover_managed_sets([provider])

	assert sets == ()
	assert len(diagnostics) == 1
	assert reason in diagnostics[0].reason


@pytest.mark.parametrize("contract_kind", ("missing", "malformed", "unsupported"))
def test_invalid_provider_contract_is_ignored(tmp_path: Path, contract_kind: str) -> None:
	provider = tmp_path / "provider"
	if contract_kind == "missing":
		provider.mkdir()
	elif contract_kind == "malformed":
		contract = provider / "dictionaries" / "contract.ini"
		contract.parent.mkdir(parents=True)
		_ = contract.write_text("not an ini file", encoding="utf-8")
	else:
		_write_provider_contract(provider, version="2")

	sets, diagnostics = discover_managed_sets([provider])

	assert sets == ()
	assert len(diagnostics) == 1


def test_undecodable_set_ini_is_skipped(tmp_path: Path) -> None:
	provider = tmp_path / "provider"
	_write_provider_contract(provider)
	set_directory = provider / "dictionaries" / "sets" / "github.invalid.encoding"
	set_directory.mkdir(parents=True)
	_ = (set_directory / "set.ini").write_bytes(b"[set]\nname = \xff\n")

	sets, diagnostics = discover_managed_sets([provider])

	assert sets == ()
	assert len(diagnostics) == 1


def test_unparseable_dictionary_fails_whole_set_closed(tmp_path: Path) -> None:
	provider = tmp_path / "provider"
	_write_provider_contract(provider)
	set_directory = _write_set(provider, "github.invalid.dictionary")
	_ = (set_directory / "enumain.dic").write_bytes(b"valid\tentry\n")
	_ = (set_directory / "deumain.dic").write_bytes(b"missing tab\n")

	sets, diagnostics = discover_managed_sets([provider])

	assert sets == ()
	assert len(diagnostics) == 1
	assert diagnostics[0].path == set_directory


def test_noncanonical_managed_dictionary_filename_case_is_ignored(tmp_path: Path) -> None:
	provider = tmp_path / "provider"
	_write_provider_contract(provider)
	set_directory = _write_set(provider, "github.noncanonical.filename")
	_ = (set_directory / "ENUMAIN.DIC").write_bytes(b"ignored\tentry\n")

	sets, diagnostics = discover_managed_sets([provider])

	assert diagnostics == ()
	assert sets[0].entries_for("enu", Slot.MAIN) == ()


def test_duplicate_set_id_keeps_first_provider(tmp_path: Path) -> None:
	providers = [tmp_path / "first", tmp_path / "second"]
	for provider in providers:
		_write_provider_contract(provider)
	first_set = _write_set(providers[0], "github.duplicate.set", metadata={"name": "First"})
	second_set = _write_set(providers[1], "github.duplicate.set", metadata={"name": "Second"})
	_ = (first_set / "enumain.dic").write_bytes(b"first\tentry\n")
	_ = (second_set / "enumain.dic").write_bytes(b"second\tentry\n")

	sets, diagnostics = discover_managed_sets(providers)

	assert [managed_set.name for managed_set in sets] == ["First"]
	assert len(diagnostics) == 1
	assert diagnostics[0].path == second_set
	assert "first provider wins" in diagnostics[0].reason


def test_real_vendored_managed_set_is_discoverable() -> None:
	repo_root = Path(__file__).resolve().parents[1]

	sets, diagnostics = discover_managed_sets([repo_root / "addon"])

	assert diagnostics == ()
	assert len(sets) == 1
	managed_set = sets[0]
	assert managed_set.id == "github.eigencrow.ibmtts-dictionaries"
	assert managed_set.name == "IBMTTSDictionaries"
	assert managed_set.source_version == "v26.07"
	assert managed_set.entries_for("enu", Slot.MAIN)
	assert managed_set.entries_for("deu", Slot.MAIN)
