"""Discovery and loading of installed Managed Dictionary Sets."""

from __future__ import annotations

import configparser
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .languages import LANGUAGES
from .model import Entry, Slot
from .parsing import canonical_filename, deduplicate_entries, load_dictionary_file


_CONTRACT_FORMAT = "eci-dictionary-sets"
_CONTRACT_VERSION = 1
_SET_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
_REQUIRED_FIELDS = (
	"id",
	"name",
	"source_url",
	"source_version",
	"source_revision",
	"attribution",
	"license",
	"license_url",
)


@dataclass(frozen=True, slots=True)
class DiscoveryDiagnostic:
	"""A structured reason why a provider or Managed Dictionary Set was rejected."""

	path: Path
	reason: str


@dataclass(frozen=True, slots=True)
class ManagedSet:
	"""A validated, immutable Managed Dictionary Set and its parsed entries."""

	id: str
	name: str
	source_url: str
	source_version: str
	source_revision: str
	attribution: str
	license: str
	license_url: str
	_entries: Mapping[tuple[str, Slot], tuple[Entry, ...]] = field(repr=False)

	def entries_for(self, language: str, slot: Slot) -> tuple[Entry, ...]:
		"""Return entries for one Western language and slot."""

		return self._entries.get((language.casefold(), slot), ())


def _read_ini(path: Path) -> configparser.ConfigParser:
	parser = configparser.ConfigParser(interpolation=None)
	with path.open("r", encoding="utf-8") as ini_file:
		parser.read_file(ini_file)
	return parser


def _recognize_provider(provider_root: Path) -> tuple[Path | None, DiscoveryDiagnostic | None]:
	dictionaries_root = provider_root / "dictionaries"
	contract_path = dictionaries_root / "contract.ini"
	try:
		parser = _read_ini(contract_path)
	except (OSError, UnicodeError, configparser.Error) as error:
		return None, DiscoveryDiagnostic(contract_path, f"missing or malformed contract.ini: {error}")
	if not parser.has_section("contract"):
		return None, DiscoveryDiagnostic(contract_path, "contract.ini has no [contract] section")
	contract_format = parser.get("contract", "format", fallback="")
	if contract_format != _CONTRACT_FORMAT:
		return None, DiscoveryDiagnostic(contract_path, f"unsupported contract format {contract_format!r}")
	version_text = parser.get("contract", "version", fallback="")
	try:
		version = int(version_text)
	except ValueError:
		return None, DiscoveryDiagnostic(contract_path, f"invalid contract version {version_text!r}")
	if version != _CONTRACT_VERSION:
		return None, DiscoveryDiagnostic(contract_path, f"unsupported contract version {version}")
	return dictionaries_root, None


def _load_set(set_directory: Path) -> ManagedSet:
	parser = _read_ini(set_directory / "set.ini")
	if not parser.has_section("set"):
		raise ValueError("set.ini has no [set] section")
	values = {
		field_name: parser.get("set", field_name, fallback="").strip() for field_name in _REQUIRED_FIELDS
	}
	missing = [field_name for field_name, value in values.items() if not value]
	if missing:
		raise ValueError(f"set.ini has empty or missing required field(s): {', '.join(missing)}")
	set_id = values["id"]
	if set_id != set_directory.name:
		raise ValueError(f"Managed Dictionary Set ID {set_id!r} does not match directory name")
	if _SET_ID_PATTERN.fullmatch(set_id) is None:
		raise ValueError(f"Managed Dictionary Set ID {set_id!r} has an invalid shape")

	set_files = {path.name: path for path in set_directory.iterdir() if path.is_file()}
	entries: dict[tuple[str, Slot], tuple[Entry, ...]] = {}
	for language_code in LANGUAGES:
		for slot in Slot:
			path = set_files.get(canonical_filename(language_code, slot))
			if path is None:
				continue
			entries[(language_code, slot)] = deduplicate_entries(
				load_dictionary_file(path, allow_invalid_entries=True),
				slot,
			)
	return ManagedSet(
		id=set_id,
		name=values["name"],
		source_url=values["source_url"],
		source_version=values["source_version"],
		source_revision=values["source_revision"],
		attribution=values["attribution"],
		license=values["license"],
		license_url=values["license_url"],
		_entries=entries,
	)


def discover_managed_sets(
	provider_roots: Iterable[str | Path],
) -> tuple[tuple[ManagedSet, ...], tuple[DiscoveryDiagnostic, ...]]:
	"""Discover valid Managed Dictionary Sets from candidate installed add-on roots.

	Providers and individual sets fail closed. The first occurrence of a duplicate
	Managed Dictionary Set ID wins, preserving the caller's provider ordering.
	"""

	discovered: dict[str, ManagedSet] = {}
	diagnostics: list[DiscoveryDiagnostic] = []
	for root_value in provider_roots:
		provider_root = Path(root_value)
		dictionaries_root, diagnostic = _recognize_provider(provider_root)
		if diagnostic is not None:
			diagnostics.append(diagnostic)
			continue
		assert dictionaries_root is not None
		sets_root = dictionaries_root / "sets"
		try:
			set_directories = sorted(
				(path for path in sets_root.iterdir() if path.is_dir()),
				key=lambda path: path.name.casefold(),
			)
		except OSError as error:
			diagnostics.append(DiscoveryDiagnostic(sets_root, f"could not enumerate sets: {error}"))
			continue
		for set_directory in set_directories:
			try:
				managed_set = _load_set(set_directory)
			except (OSError, UnicodeError, configparser.Error, ValueError) as error:
				diagnostics.append(DiscoveryDiagnostic(set_directory, str(error)))
				continue
			if managed_set.id in discovered:
				diagnostics.append(
					DiscoveryDiagnostic(
						set_directory,
						f"duplicate Managed Dictionary Set ID {managed_set.id!r}; the first provider wins",
					),
				)
				continue
			discovered[managed_set.id] = managed_set
	return tuple(discovered.values()), tuple(diagnostics)
