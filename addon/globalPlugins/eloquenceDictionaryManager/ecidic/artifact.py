"""Export Personal Dictionary Overlay entries as ``.edm-dict`` artifacts.

The archive format is deliberately small: canonical ECI dictionary files and a
single INI manifest.  Constants for the format and manifest schema live here so
the importer can share them without duplicating protocol details.
"""

from __future__ import annotations

import configparser
from collections.abc import Iterable
from io import BytesIO, StringIO
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from .languages import get_language
from .model import Slot
from .overlay import PersonalOverlay
from .parsing import DictionaryEncodingError, canonical_filename, serialize_dictionary_bytes
from .validation import EntryValidationError, ValidationCode


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
	"EDM_DICT_FORMAT_ID",
	"EDM_DICT_FORMAT_VERSION",
	"MANIFEST_EXPORTING_EDM_VERSION_KEY",
	"MANIFEST_FILENAME",
	"MANIFEST_FORMAT_ID_KEY",
	"MANIFEST_FORMAT_VERSION_KEY",
	"MANIFEST_LANGUAGES_KEY",
	"MANIFEST_SECTION",
	"export_edm_dict_artifact",
]
