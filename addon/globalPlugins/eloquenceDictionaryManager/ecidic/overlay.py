"""Loading and working-copy storage for the Personal Dictionary Overlay."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .languages import LANGUAGES
from .model import Entry, Slot
from .parsing import deduplicate_entries, find_dictionary_file, key_identity, load_dictionary_file


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
