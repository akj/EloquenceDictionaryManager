"""Read-only discovery and classification of legacy Eloquence dictionaries."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from .historicalunion import HistoricalUnion
from .languages import LANGUAGES
from .model import Entry, Slot
from .parsing import (
	DictionaryEncodingError,
	DictionaryFormatError,
	deduplicate_entries,
	find_dictionary_file,
	parse_dictionary_bytes,
	parse_dictionary_filename,
)
from .validation import EntryValidationError, normalize_entry, validate_entry

try:
	import addonHandler

	addonHandler.initTranslation()
except (ImportError, ModuleNotFoundError):

	def _(text: str) -> str:
		return text


_BACKUP_DIRECTORY_NAMES = ("eloquence-dic-backup", "eloquence")


@dataclass(frozen=True, slots=True)
class MigrationDiagnostic:
	"""A structured reason why one legacy dictionary location was skipped."""

	path: Path
	reason: str


@dataclass(frozen=True, slots=True)
class MigrationCandidate:
	"""One unnormalized legacy dictionary row and its source identity."""

	language: str
	slot: Slot
	entry: Entry
	path: Path


@dataclass(frozen=True, slots=True)
class MigrationScan:
	"""The readable legacy entries and diagnostics found in one directory."""

	directory: Path
	candidates: tuple[MigrationCandidate, ...]
	diagnostics: tuple[MigrationDiagnostic, ...]
	decoded_files: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class MigrationDiscovery:
	"""The first useful auto-scan result and diagnostics from attempted locations."""

	scan: MigrationScan | None
	diagnostics: tuple[MigrationDiagnostic, ...]


class MigrationCandidateStatus(str, Enum):
	"""How a readable legacy entry relates to validation, history, and personal data."""

	LIKELY_HAND_EDIT = "likelyHandEdit"
	INVALID = "invalid"
	DIFFERS_FROM_PERSONAL = "differsFromPersonal"


@dataclass(frozen=True, slots=True)
class MigrationCandidateRow:
	"""One classified row ready for binding to the migration review dialog."""

	word: str
	pronunciation: str
	slot: Slot
	language: str
	status: MigrationCandidateStatus
	status_text: str
	checked_by_default: bool
	checkable: bool
	path: Path


class PersonalOverlayLookup(Protocol):
	"""The Personal Dictionary Overlay operations used during classification."""

	def get_entry(self, language: str, slot: Slot, key: str) -> Entry | None: ...


class PersonalOverlayWriter(PersonalOverlayLookup, Protocol):
	"""The Personal Dictionary Overlay operations used while applying rows."""

	def set_entry(self, language: str, slot: Slot, entry: Entry) -> None: ...


def _find_case_insensitive_directory(parent: Path, expected_name: str) -> tuple[Path, ...]:
	try:
		children = tuple(parent.iterdir())
	except OSError:
		return ()
	return tuple(
		sorted(
			(
				child
				for child in children
				if child.is_dir() and child.name.casefold() == expected_name.casefold()
			),
			key=lambda path: (path.name.casefold(), path.name),
		)
	)


def find_eloquence_backup_directories(provider_paths: Sequence[str | Path]) -> tuple[Path, ...]:
	"""Find legacy Eloquence directories in backup-first, then live-driver order.

	Every installed add-on path is considered for the pinned backup name before
	any live ``eloquence`` directory. Directory-name comparison is case-insensitive
	so the behavior does not depend on the host filesystem.
	"""

	providers = tuple(Path(path) for path in provider_paths)
	synth_roots = tuple(
		(provider, _find_case_insensitive_directory(provider, "synthDrivers")) for provider in providers
	)
	result: list[Path] = []
	for directory_name in _BACKUP_DIRECTORY_NAMES:
		for _provider, roots in synth_roots:
			for root in roots:
				result.extend(_find_case_insensitive_directory(root, directory_name))
	return tuple(result)


def scan_migration_directory(directory: str | Path) -> MigrationScan:
	"""Read recognized Western ECI dictionaries without changing their contents."""

	directory_path = Path(directory)
	diagnostics: list[MigrationDiagnostic] = []
	candidates: list[MigrationCandidate] = []
	decoded_files: list[Path] = []
	if not directory_path.is_dir():
		return MigrationScan(
			directory=directory_path,
			candidates=(),
			diagnostics=(MigrationDiagnostic(directory_path, "directory is unavailable"),),
			decoded_files=(),
		)

	for language in LANGUAGES:
		for slot in Slot:
			try:
				path = find_dictionary_file(directory_path, language, slot)
			except (OSError, ValueError) as error:
				diagnostics.append(MigrationDiagnostic(directory_path, str(error)))
				continue
			if path is None:
				continue
			try:
				filename = parse_dictionary_filename(path)
				entries = parse_dictionary_bytes(
					path.read_bytes(),
					filename.language,
					filename.slot,
					allow_invalid_entries=True,
				)
			except (OSError, DictionaryEncodingError, DictionaryFormatError, ValueError) as error:
				diagnostics.append(MigrationDiagnostic(path, str(error)))
				continue
			decoded_files.append(path)
			for entry in deduplicate_entries(entries, filename.slot):
				candidates.append(
					MigrationCandidate(
						language=filename.language.code,
						slot=filename.slot,
						entry=entry,
						path=path,
					),
				)
	return MigrationScan(
		directory=directory_path,
		candidates=tuple(candidates),
		diagnostics=tuple(diagnostics),
		decoded_files=tuple(decoded_files),
	)


def discover_migration_candidates(provider_paths: Sequence[str | Path]) -> MigrationDiscovery:
	"""Scan auto-detected locations until the first one with a decodable dictionary."""

	diagnostics: list[MigrationDiagnostic] = []
	for directory in find_eloquence_backup_directories(provider_paths):
		scan = scan_migration_directory(directory)
		diagnostics.extend(scan.diagnostics)
		if scan.decoded_files:
			return MigrationDiscovery(scan=scan, diagnostics=tuple(diagnostics))
	return MigrationDiscovery(scan=None, diagnostics=tuple(diagnostics))


def _status_text(status: MigrationCandidateStatus) -> str:
	if status is MigrationCandidateStatus.LIKELY_HAND_EDIT:
		# Translators: Migration status for a legacy dictionary row absent from known upstream history.
		return _("Likely hand edit")
	if status is MigrationCandidateStatus.DIFFERS_FROM_PERSONAL:
		# Translators: Migration status for a legacy row that would replace a different personal entry.
		return _("Differs from your current entry for this word")
	raise ValueError(f"Invalid migration status for a fixed label: {status}")


def classify_migration_candidates(
	candidates: Iterable[MigrationCandidate],
	overlay: PersonalOverlayLookup,
	historical_union: HistoricalUnion,
) -> tuple[MigrationCandidateRow, ...]:
	"""Classify readable legacy rows against the working copy and historical union."""

	rows: list[MigrationCandidateRow] = []
	for candidate in candidates:
		if historical_union.contains(
			candidate.language,
			candidate.slot,
			candidate.entry.key,
			candidate.entry.value,
		):
			continue
		existing = overlay.get_entry(candidate.language, candidate.slot, candidate.entry.key)
		# Root identity is case-insensitive and personal root keys are normalized on
		# write, so an equal value is already the same effective personal entry.
		if existing is not None and existing.value == candidate.entry.value:
			continue
		issues = validate_entry(candidate.entry, candidate.slot, candidate.language)
		if issues:
			status = MigrationCandidateStatus.INVALID
			status_text = issues[0].message
			checked_by_default = False
			checkable = False
		elif existing is not None:
			status = MigrationCandidateStatus.DIFFERS_FROM_PERSONAL
			status_text = _status_text(status)
			checked_by_default = False
			checkable = True
		else:
			status = MigrationCandidateStatus.LIKELY_HAND_EDIT
			status_text = _status_text(status)
			checked_by_default = True
			checkable = True
		rows.append(
			MigrationCandidateRow(
				word=candidate.entry.key,
				pronunciation=candidate.entry.value,
				slot=candidate.slot,
				language=candidate.language,
				status=status,
				status_text=status_text,
				checked_by_default=checked_by_default,
				checkable=checkable,
				path=candidate.path,
			),
		)
	return tuple(rows)


def apply_migration_candidates(
	overlay: PersonalOverlayWriter,
	rows: Iterable[MigrationCandidateRow],
) -> int:
	"""Validate, normalize, and apply selected checkable rows to a working copy."""

	imported = 0
	for row in rows:
		if not row.checkable:
			continue
		entry = Entry(row.word, row.pronunciation)
		issues = validate_entry(entry, row.slot, row.language)
		if issues:
			raise EntryValidationError(issues[0])
		overlay.set_entry(row.language, row.slot, normalize_entry(entry, row.slot))
		imported += 1
	return imported
