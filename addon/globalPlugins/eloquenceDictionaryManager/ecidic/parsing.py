"""Parsing, serialization, discovery, and deduplication for ECI ``.dic`` files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .languages import Language, get_language
from .model import Entry, Slot, coerce_slot
from .validation import normalize_entry, validate_or_raise

try:
	import addonHandler

	addonHandler.initTranslation()
except (ImportError, ModuleNotFoundError):
	_ = lambda s: s


CANONICAL_LINE_ENDING = b"\r\n"


class DictionaryFormatError(ValueError):
	"""Raised when dictionary bytes do not have the required line structure."""


class DictionaryEncodingError(UnicodeError):
	"""Raised when dictionary bytes or text do not fit a language code page."""


class DictionaryFilenameError(ValueError):
	"""Raised when a filename does not identify a supported dictionary file."""


@dataclass(frozen=True, slots=True)
class DictionaryFilename:
	"""The language and slot encoded by a conventional ``.dic`` filename."""

	language: Language
	slot: Slot

	@property
	def canonical_name(self) -> str:
		return canonical_filename(self.language, self.slot)


_FILENAME_PATTERN = re.compile(
	r"^(?P<language>[A-Za-z]{3})(?P<slot>main|root|abbr)\.dic$",
	re.IGNORECASE,
)


def canonical_filename(language: Language | str, slot: Slot | str) -> str:
	"""Return the lowercase conventional filename for *language* and *slot*."""

	language_record = get_language(language) if isinstance(language, str) else language
	return f"{language_record.code}{coerce_slot(slot).value}.dic"


def parse_dictionary_filename(path: str | Path) -> DictionaryFilename:
	"""Parse either observed filename-case convention."""

	name = Path(path).name
	match = _FILENAME_PATTERN.fullmatch(name)
	if match is None:
		# Translators: Import error when a filename does not follow the ECI dictionary naming convention. {name} is the filename.
		message = _(
			'The file "{name}" is not named like an ECI dictionary file.',
		).format(name=name)
		raise DictionaryFilenameError(message)
	try:
		language = get_language(match.group("language"))
	except ValueError as error:
		raise DictionaryFilenameError(str(error)) from error
	return DictionaryFilename(language=language, slot=coerce_slot(match.group("slot").lower()))


def find_dictionary_file(
	directory: str | Path,
	language: Language | str,
	slot: Slot | str,
) -> Path | None:
	"""Find a dictionary file case-insensitively, including on Linux."""

	directory_path = Path(directory)
	expected = canonical_filename(language, slot).casefold()
	matches = [path for path in directory_path.iterdir() if path.is_file() and path.name.casefold() == expected]
	if len(matches) > 1:
		# Translators: Import error when differently-cased copies of the same dictionary filename coexist. {name} is the canonical filename.
		message = _(
			'More than one file matches the dictionary filename "{name}".',
		).format(name=canonical_filename(language, slot))
		raise DictionaryFilenameError(message)
	return matches[0] if matches else None


def parse_dictionary_bytes(
	data: bytes,
	language: Language | str,
	slot: Slot | str,
) -> tuple[Entry, ...]:
	"""Decode and parse LF, CRLF, or mixed-line-ending dictionary bytes."""

	language_record = get_language(language) if isinstance(language, str) else language
	coerce_slot(slot)
	try:
		text = data.decode(language_record.encoding, errors="strict")
	except UnicodeDecodeError as error:
		# Translators: Import error for bytes invalid in a language's code page. {code} is the ECI voice code and {offset} is the byte position.
		message = _(
			'The dictionary contains bytes that are invalid for the "{code}" voice at byte {offset}.',
		).format(code=language_record.code, offset=error.start)
		raise DictionaryEncodingError(message) from error
	text = text.replace("\r\n", "\n")
	if "\r" in text:
		# Translators: Import error when a dictionary contains a bare carriage return instead of LF or CRLF.
		message = _("The dictionary contains an unsupported line ending.")
		raise DictionaryFormatError(message)
	if not text:
		return ()
	lines = text.split("\n")
	if lines[-1] == "":
		lines.pop()
	entries: list[Entry] = []
	for line_number, line in enumerate(lines, start=1):
		if not line:
			# Translators: Import error for a blank dictionary line. {line} is the one-based line number.
			message = _("Dictionary line {line} is blank.").format(line=line_number)
			raise DictionaryFormatError(message)
		if line.count("\t") != 1:
			# Translators: Import error when a line does not contain exactly one tab separator. {line} is the one-based line number.
			message = _(
				"Dictionary line {line} must contain exactly one tab between the word and pronunciation.",
			).format(line=line_number)
			raise DictionaryFormatError(message)
		key, value = line.split("\t")
		entries.append(Entry(key=key, value=value))
	return tuple(entries)


def key_identity(key: str, slot: Slot | str) -> str:
	"""Return the key identity used for matching and deduplication."""

	return key.casefold() if coerce_slot(slot) is Slot.ROOT else key


def deduplicate_entries(entries: Iterable[Entry], slot: Slot | str) -> tuple[Entry, ...]:
	"""Keep the last occurrence of each key, in last-occurrence order."""

	entry_list = list(entries)
	seen: set[str] = set()
	result: list[Entry] = []
	for entry in reversed(entry_list):
		identity = key_identity(entry.key, slot)
		if identity in seen:
			continue
		seen.add(identity)
		result.append(entry)
	result.reverse()
	return tuple(result)


def merge_entries(
	managed: Iterable[Entry],
	personal: Iterable[Entry],
	slot: Slot | str,
) -> tuple[Entry, ...]:
	"""Merge managed and Personal Dictionary Overlay entries, personal last-wins."""

	return deduplicate_entries((*managed, *personal), slot)


def serialize_dictionary_bytes(
	entries: Iterable[Entry],
	language: Language | str,
	slot: Slot | str,
	*,
	validate: bool = True,
	deduplicate: bool = True,
) -> bytes:
	"""Serialize entries using the language code page and canonical CRLF lines."""

	language_record = get_language(language) if isinstance(language, str) else language
	slot_value = coerce_slot(slot)
	entry_list = tuple(entries)
	if deduplicate:
		entry_list = deduplicate_entries(entry_list, slot_value)
	canonical_entries: list[Entry] = []
	for entry in entry_list:
		if validate:
			validate_or_raise(entry, slot_value, language_record)
			entry = normalize_entry(entry, slot_value)
		canonical_entries.append(entry)
	text = "\r\n".join(f"{entry.key}\t{entry.value}" for entry in canonical_entries)
	if canonical_entries:
		text += "\r\n"
	try:
		return text.encode(language_record.encoding, errors="strict")
	except UnicodeEncodeError as error:
		character = text[error.start : error.start + 1]
		# Translators: Save error for a character not supported by a Western ECI language code page. {character} is the character.
		message = _(
			'The character "{character}" cannot be saved in an Eloquence dictionary '
			"(Western encoding only).",
		).format(character=character)
		raise DictionaryEncodingError(message) from error


def load_dictionary_file(path: str | Path) -> tuple[Entry, ...]:
	"""Infer language and slot from *path*, then parse its bytes."""

	path_value = Path(path)
	filename = parse_dictionary_filename(path_value)
	return parse_dictionary_bytes(path_value.read_bytes(), filename.language, filename.slot)


def write_dictionary_file(
	directory: str | Path,
	language: Language | str,
	slot: Slot | str,
	entries: Iterable[Entry],
) -> Path:
	"""Write a canonical lowercase filename and return its path."""

	path = Path(directory) / canonical_filename(language, slot)
	path.write_bytes(serialize_dictionary_bytes(entries, language, slot))
	return path
