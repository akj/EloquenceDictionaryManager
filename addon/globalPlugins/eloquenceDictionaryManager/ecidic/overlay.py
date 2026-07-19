"""Loading and working-copy storage for the Personal Dictionary Overlay."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .languages import LANGUAGES
from .model import Entry, Slot
from .parsing import (
	canonical_filename,
	deduplicate_entries,
	DictionaryEncodingError,
	find_dictionary_file,
	key_identity,
	load_dictionary_file,
	write_dictionary_file,
)
from .validation import EntryValidationError, ValidationCode


def _empty_overlay_entries() -> dict[tuple[str, Slot, str], Entry]:
	return {}


@dataclass(frozen=True, slots=True)
class OverlayDiagnostic:
	"""A structured reason why one Personal Dictionary Overlay file was skipped."""

	path: Path
	reason: str


@dataclass(slots=True)
class PersonalOverlay:
	"""A mutable working copy of Personal Dictionary Overlay entries."""

	entries: dict[tuple[str, Slot, str], Entry] = field(default_factory=_empty_overlay_entries)

	def get_entry(self, language: str, slot: Slot, key: str) -> Entry | None:
		"""Return a personal entry by its language, slot, and key identity."""

		return self.entries.get((language.casefold(), slot, key_identity(key, slot)))

	def set_entry(self, language: str, slot: Slot, entry: Entry) -> None:
		"""Insert or replace a personal entry by identity."""

		self.entries[(language.casefold(), slot, key_identity(entry.key, slot))] = entry

	def remove_entry(self, language: str, slot: Slot, key: str) -> None:
		"""Remove a personal entry by identity, if it exists."""

		_previous_entry = self.entries.pop((language.casefold(), slot, key_identity(key, slot)), None)

	def remove_language(self, language: str) -> int:
		"""Remove and count every personal entry for one language."""

		language_code = language.casefold()
		matching_keys = [key for key in self.entries if key[0] == language_code]
		for key in matching_keys:
			del self.entries[key]
		return len(matching_keys)

	def count_for(self, language: str) -> int:
		"""Return the number of personal entries for one language."""

		language_code = language.casefold()
		return sum(entry_language == language_code for entry_language, _slot, _key in self.entries)

	def entries_for(self, language: str, slot: Slot) -> tuple[Entry, ...]:
		"""Return the working-copy entries for one language and slot."""

		language_code = language.casefold()
		return tuple(
			entry
			for (entry_language, entry_slot, _identity), entry in self.entries.items()
			if entry_language == language_code and entry_slot is slot
		)

	@classmethod
	def from_entries(
		cls,
		items: Iterable[tuple[str, Slot, Entry]],
	) -> PersonalOverlay:
		"""Build a working copy from language, slot, and entry triples."""

		overlay = cls()
		for language, slot, entry in items:
			overlay.entries[(language.casefold(), slot, key_identity(entry.key, slot))] = entry
		return overlay


def load_personal_overlay(
	directory: str | Path,
) -> tuple[PersonalOverlay, tuple[OverlayDiagnostic, ...]]:
	"""Load the Personal Dictionary Overlay, skipping corrupt files independently."""

	overlay = PersonalOverlay()
	diagnostics: list[OverlayDiagnostic] = []
	directory_path = Path(directory)
	if not directory_path.is_dir():
		return overlay, ()
	for language_code in LANGUAGES:
		for slot in Slot:
			try:
				path = find_dictionary_file(directory_path, language_code, slot)
			except (OSError, ValueError) as error:
				diagnostics.append(
					OverlayDiagnostic(
						directory_path,
						f"could not locate {language_code}{slot.value}.dic: {error}",
					),
				)
				continue
			if path is None:
				continue
			try:
				entries = deduplicate_entries(load_dictionary_file(path), slot)
			except (OSError, UnicodeError, ValueError) as error:
				diagnostics.append(OverlayDiagnostic(path, str(error)))
				continue
			for entry in entries:
				overlay.entries[(language_code, slot, key_identity(entry.key, slot))] = entry
	return overlay, tuple(diagnostics)


def save_personal_overlay(overlay: PersonalOverlay, directory: str | Path) -> None:
	"""Commit a working copy to canonical Personal Dictionary Overlay files."""

	directory_path = Path(directory)
	directory_path.mkdir(parents=True, exist_ok=True)
	for language_code in LANGUAGES:
		for slot in Slot:
			entries = overlay.entries_for(language_code, slot)
			existing_path = find_dictionary_file(directory_path, language_code, slot)
			if not entries:
				if existing_path is not None:
					existing_path.unlink()
				continue
			canonical_path = directory_path / canonical_filename(language_code, slot)
			if existing_path is not None and existing_path.name != canonical_path.name:
				existing_path.unlink()
			try:
				_written_path = write_dictionary_file(directory_path, language_code, slot, entries)
			except EntryValidationError as error:
				if error.issue.code is ValidationCode.UNENCODABLE_CHARACTER:
					raise DictionaryEncodingError(str(error)) from error
				raise
