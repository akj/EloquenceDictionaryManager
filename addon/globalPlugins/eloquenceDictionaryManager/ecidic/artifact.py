"""Import and export Personal Dictionary Overlay ``.edm-dict`` artifacts.

The archive format is deliberately small: canonical ECI dictionary files and a
single INI manifest.  Constants for the format and manifest schema live here so
the importer can share them without duplicating protocol details.
"""

from __future__ import annotations

import configparser
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from io import BytesIO, StringIO
from zipfile import BadZipFile, LargeZipFile, ZIP_STORED, ZipFile, ZipInfo

from .languages import LANGUAGES, get_language
from .model import Entry, Slot
from .overlay import PersonalOverlay
from .parsing import (
	DictionaryEncodingError,
	canonical_filename,
	parse_dictionary_bytes,
	serialize_dictionary_bytes,
)
from .validation import EntryValidationError, ValidationCode, normalize_entry, validate_entry

try:
	import addonHandler

	addonHandler.initTranslation()
except (ImportError, ModuleNotFoundError):

	def _(text: str) -> str:
		return text


EDM_DICT_FORMAT_ID = "eloquence-dictionary-manager-overlay"
"""Stable identifier for an Eloquence Dictionary Manager overlay artifact."""

EDM_DICT_FORMAT_VERSION = 1
"""Supported major version of the ``.edm-dict`` artifact format."""

MANIFEST_FILENAME = "manifest.ini"
MANIFEST_SECTION = "edm-dict"
MANIFEST_FORMAT_ID_KEY = "format"
MANIFEST_FORMAT_VERSION_KEY = "format_version"
MANIFEST_EXPORTING_EDM_VERSION_KEY = "exporting_edm_version"
MANIFEST_LANGUAGES_KEY = "languages"

_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class InvalidArtifactError(ValueError):
	"""Raised when an ``.edm-dict`` artifact must be rejected as a whole."""


@dataclass(frozen=True, slots=True)
class ArtifactDictionary:
	"""Entries parsed from one canonical dictionary member in an artifact."""

	language: str
	slot: Slot
	entries: tuple[Entry, ...]


@dataclass(frozen=True, slots=True)
class EdmDictArtifact:
	"""A validated manifest and the dictionary members it declares."""

	languages: tuple[str, ...]
	dictionaries: tuple[ArtifactDictionary, ...]


class ImportMode(str, Enum):
	"""How an import changes the Personal Dictionary Overlay working copy."""

	MERGE = "merge"
	REPLACE = "replace"


class CollisionResolution(str, Enum):
	"""How merge mode handles entries matching existing personal entries."""

	KEEP_PERSONAL = "keepPersonal"
	USE_IMPORTED = "useImported"


@dataclass(frozen=True, slots=True)
class PlannedImportEntry:
	"""One validated, normalized artifact entry classified against an overlay."""

	language: str
	slot: Slot
	entry: Entry
	collision: bool


@dataclass(frozen=True, slots=True)
class ImportPlan:
	"""A UI-independent plan that can be previewed before applying an import."""

	languages: tuple[str, ...]
	entries: tuple[PlannedImportEntry, ...]
	skipped_invalid: int

	@property
	def collision_count(self) -> int:
		"""Return the number of imported rows matching personal entries."""

		return sum(item.collision for item in self.entries)


@dataclass(frozen=True, slots=True)
class ImportResult:
	"""Counts describing the completed working-copy mutation."""

	imported: int
	collisions_kept: int
	collisions_replaced: int
	skipped_invalid: int


def _serialize_manifest(exporting_edm_version: str, content_languages: tuple[str, ...]) -> bytes:
	"""Return the UTF-8 INI manifest for the artifact.

	``content_languages`` contains only requested languages that contributed at
	least one dictionary file.  Recording content rather than the original scope
	lets a future replace-mode importer identify exactly which language overlays
	the artifact represents.
	"""

	parser = configparser.ConfigParser(interpolation=None)
	parser[MANIFEST_SECTION] = {
		MANIFEST_FORMAT_ID_KEY: EDM_DICT_FORMAT_ID,
		MANIFEST_FORMAT_VERSION_KEY: str(EDM_DICT_FORMAT_VERSION),
		MANIFEST_EXPORTING_EDM_VERSION_KEY: exporting_edm_version,
		MANIFEST_LANGUAGES_KEY: ", ".join(content_languages),
	}
	stream = StringIO(newline="\n")
	parser.write(stream)
	return stream.getvalue().encode("utf-8")


def _zip_info(filename: str) -> ZipInfo:
	"""Return reproducible metadata for one stored archive member."""

	info = ZipInfo(filename, date_time=_ZIP_TIMESTAMP)
	info.compress_type = ZIP_STORED
	info.create_system = 0
	return info


def _parse_manifest(data: bytes) -> tuple[str, ...]:
	"""Validate manifest bytes and return canonical declared language codes."""

	try:
		text = data.decode("utf-8-sig", errors="strict")
		parser = configparser.ConfigParser(interpolation=None)
		parser.read_string(text)
	except (UnicodeError, configparser.Error) as error:
		message = _(
			# Translators: Import error when an Eloquence dictionary artifact manifest cannot be parsed.
			"The dictionary artifact manifest is not valid UTF-8 INI data.",
		)
		raise InvalidArtifactError(message) from error

	try:
		section = parser[MANIFEST_SECTION]
		format_id = section[MANIFEST_FORMAT_ID_KEY]
		version_text = section[MANIFEST_FORMAT_VERSION_KEY]
		languages_text = section[MANIFEST_LANGUAGES_KEY]
	except KeyError as error:
		message = _(
			# Translators: Import error when a required section or value is absent from an Eloquence dictionary artifact manifest.
			"The dictionary artifact manifest is missing required information.",
		)
		raise InvalidArtifactError(message) from error

	if format_id != EDM_DICT_FORMAT_ID:
		message = _(
			# Translators: Import error when a file is not an Eloquence Dictionary Manager overlay artifact.
			"The selected file is not an Eloquence Dictionary Manager dictionary artifact.",
		)
		raise InvalidArtifactError(message)
	try:
		format_version = int(version_text)
	except ValueError as error:
		message = _(
			# Translators: Import error when an Eloquence dictionary artifact has an invalid format version value.
			"The dictionary artifact has an invalid format version.",
		)
		raise InvalidArtifactError(message) from error
	if format_version < 0:
		message = _(
			# Translators: Import error when an Eloquence dictionary artifact has an invalid format version value.
			"The dictionary artifact has an invalid format version.",
		)
		raise InvalidArtifactError(message)
	if format_version > EDM_DICT_FORMAT_VERSION:
		message = _(
			# Translators: Import error for an artifact created by a newer incompatible version. {version} is the artifact format version and {supported} is the newest supported version.
			"This dictionary artifact uses format version {version}, but this version of Eloquence Dictionary Manager supports only version {supported}.",
		).format(version=format_version, supported=EDM_DICT_FORMAT_VERSION)
		raise InvalidArtifactError(message)

	if not languages_text.strip():
		return ()
	declared_codes = tuple(part.strip() for part in languages_text.split(","))
	if any(not code for code in declared_codes):
		message = _(
			# Translators: Import error when the language list in an Eloquence dictionary artifact manifest is malformed.
			"The dictionary artifact manifest has an invalid language list.",
		)
		raise InvalidArtifactError(message)
	try:
		languages = tuple(get_language(code).code for code in declared_codes)
	except ValueError as error:
		message = _(
			# Translators: Import error when an Eloquence dictionary artifact declares an unsupported language. {error} describes the unsupported voice code.
			"The dictionary artifact declares an unsupported language.\n\n{error}",
		).format(error=error)
		raise InvalidArtifactError(message) from error
	if len(set(languages)) != len(languages):
		message = _(
			# Translators: Import error when a language is listed more than once in an Eloquence dictionary artifact manifest.
			"The dictionary artifact manifest lists a language more than once.",
		)
		raise InvalidArtifactError(message)
	return languages


def read_edm_dict_artifact(data: bytes) -> EdmDictArtifact:
	"""Read and validate an ``.edm-dict`` archive from bytes.

	Format versions older than or equal to :data:`EDM_DICT_FORMAT_VERSION` use
	the v1 layout and are accepted. A newer major version is rejected before any
	dictionary content is returned. Unrecognized archive members are ignored;
	recognized canonical dictionary members must be readable and parseable.
	"""

	try:
		with ZipFile(BytesIO(data), mode="r") as zip_file:
			members = zip_file.infolist()
			manifest_members = [member for member in members if member.filename == MANIFEST_FILENAME]
			if len(manifest_members) != 1:
				message = _(
					# Translators: Import error when an Eloquence dictionary artifact has no single canonical manifest file.
					'The dictionary artifact must contain exactly one "manifest.ini" file.',
				)
				raise InvalidArtifactError(message)
			languages = _parse_manifest(zip_file.read(manifest_members[0]))
			declared_languages = set(languages)
			recognized_members = {
				canonical_filename(language, slot): (language, slot)
				for language in LANGUAGES
				for slot in Slot
			}
			dictionaries: list[ArtifactDictionary] = []
			seen_dictionaries: set[tuple[str, Slot]] = set()
			for member in members:
				dictionary_identity = recognized_members.get(member.filename)
				if dictionary_identity is None:
					continue
				language, slot = dictionary_identity
				if language not in declared_languages:
					message = _(
						# Translators: Import error when a dictionary file's language is absent from the artifact manifest. {name} is the dictionary filename.
						'The dictionary artifact manifest does not declare the language used by "{name}".',
					).format(name=member.filename)
					raise InvalidArtifactError(message)
				if dictionary_identity in seen_dictionaries:
					message = _(
						# Translators: Import error when an Eloquence dictionary artifact contains the same dictionary file more than once. {name} is the dictionary filename.
						'The dictionary artifact contains more than one "{name}" file.',
					).format(name=member.filename)
					raise InvalidArtifactError(message)
				seen_dictionaries.add(dictionary_identity)
				try:
					entries = parse_dictionary_bytes(
						zip_file.read(member),
						language,
						slot,
						allow_invalid_entries=True,
					)
				except (DictionaryEncodingError, ValueError) as error:
					message = _(
						# Translators: Import error when a dictionary member in an artifact cannot be parsed. {name} is the filename and {error} describes the problem.
						'The dictionary artifact contains an invalid dictionary file, "{name}".\n\n{error}',
					).format(name=member.filename, error=error)
					raise InvalidArtifactError(message) from error
				dictionaries.append(
					ArtifactDictionary(language=language, slot=slot, entries=entries),
				)
	except InvalidArtifactError:
		raise
	except (BadZipFile, LargeZipFile, OSError, RuntimeError, EOFError, NotImplementedError) as error:
		message = _(
			# Translators: Import error when an Eloquence dictionary artifact cannot be opened or read.
			"The selected dictionary artifact could not be opened or read.",
		)
		raise InvalidArtifactError(message) from error
	return EdmDictArtifact(languages=languages, dictionaries=tuple(dictionaries))


def build_import_plan(artifact: EdmDictArtifact, overlay: PersonalOverlay) -> ImportPlan:
	"""Validate artifact rows and classify them against a working-copy overlay."""

	planned_entries: list[PlannedImportEntry] = []
	skipped_invalid = 0
	for dictionary in artifact.dictionaries:
		for entry in dictionary.entries:
			if validate_entry(entry, dictionary.slot, dictionary.language):
				skipped_invalid += 1
				continue
			normalized_entry = normalize_entry(entry, dictionary.slot)
			planned_entries.append(
				PlannedImportEntry(
					language=dictionary.language,
					slot=dictionary.slot,
					entry=normalized_entry,
					collision=overlay.get_entry(
						dictionary.language,
						dictionary.slot,
						normalized_entry.key,
					)
					is not None,
				),
			)
	return ImportPlan(
		languages=artifact.languages,
		entries=tuple(planned_entries),
		skipped_invalid=skipped_invalid,
	)


def apply_import_plan(
	overlay: PersonalOverlay,
	plan: ImportPlan,
	mode: ImportMode | str = ImportMode.MERGE,
	collision_resolution: CollisionResolution | str = CollisionResolution.KEEP_PERSONAL,
) -> ImportResult:
	"""Apply a prepared import plan to a Personal Dictionary Overlay working copy."""

	mode_value = ImportMode(mode)
	resolution_value = CollisionResolution(collision_resolution)
	imported = 0
	collisions_kept = 0
	collisions_replaced = 0
	if mode_value is ImportMode.REPLACE:
		removed_count = sum(overlay.remove_language(language) for language in plan.languages)
		assert removed_count >= 0
		language_scope = set(plan.languages)
		for item in plan.entries:
			if item.language not in language_scope:
				continue
			overlay.set_entry(item.language, item.slot, item.entry)
			imported += 1
	else:
		for item in plan.entries:
			if item.collision and resolution_value is CollisionResolution.KEEP_PERSONAL:
				collisions_kept += 1
				continue
			overlay.set_entry(item.language, item.slot, item.entry)
			imported += 1
			if item.collision:
				collisions_replaced += 1
	return ImportResult(
		imported=imported,
		collisions_kept=collisions_kept,
		collisions_replaced=collisions_replaced,
		skipped_invalid=plan.skipped_invalid,
	)


def export_edm_dict_artifact(
	overlay: PersonalOverlay,
	languages: Iterable[str],
	exporting_edm_version: str,
) -> bytes:
	"""Serialize personal working-copy entries into deterministic zip bytes.

	Only entries from the supplied language scope are included.  Empty
	language/slot combinations do not create dictionary members.  Dictionary
	member names and contents come directly from :func:`canonical_filename` and
	:func:`serialize_dictionary_bytes`, preserving the canonical lowercase names,
	CP1252 encoding, validation, normalization, and CRLF line endings used by
	normal Personal Dictionary Overlay saves.

	Unsupported language codes, invalid entries, and unencodable text propagate
	the domain exceptions raised by the shared language, validation, and parsing
	modules.  In particular, unencodable text is reported as
	:class:`~ecidic.parsing.DictionaryEncodingError`, never a raw
	:class:`UnicodeEncodeError`.
	"""

	scope = tuple(sorted({get_language(language).code for language in languages}))
	members: dict[str, bytes] = {}
	content_languages: list[str] = []
	for language in scope:
		language_has_content = False
		for slot in Slot:
			entries = overlay.entries_for(language, slot)
			if not entries:
				continue
			filename = canonical_filename(language, slot)
			try:
				members[filename] = serialize_dictionary_bytes(entries, language, slot)
			except EntryValidationError as error:
				if error.issue.code is ValidationCode.UNENCODABLE_CHARACTER:
					raise DictionaryEncodingError(str(error)) from error
				raise
			language_has_content = True
		if language_has_content:
			content_languages.append(language)
	members[MANIFEST_FILENAME] = _serialize_manifest(
		exporting_edm_version,
		tuple(content_languages),
	)

	archive = BytesIO()
	with ZipFile(archive, mode="w", compression=ZIP_STORED) as zip_file:
		for filename in sorted(members):
			zip_file.writestr(_zip_info(filename), members[filename])
	return archive.getvalue()


__all__ = [
	"ArtifactDictionary",
	"CollisionResolution",
	"EDM_DICT_FORMAT_ID",
	"EDM_DICT_FORMAT_VERSION",
	"EdmDictArtifact",
	"ImportMode",
	"ImportPlan",
	"ImportResult",
	"InvalidArtifactError",
	"MANIFEST_EXPORTING_EDM_VERSION_KEY",
	"MANIFEST_FILENAME",
	"MANIFEST_FORMAT_ID_KEY",
	"MANIFEST_FORMAT_VERSION_KEY",
	"MANIFEST_LANGUAGES_KEY",
	"MANIFEST_SECTION",
	"PlannedImportEntry",
	"apply_import_plan",
	"build_import_plan",
	"export_edm_dict_artifact",
	"read_edm_dict_artifact",
]
