from __future__ import annotations

import configparser
from io import BytesIO, TextIOWrapper
from zipfile import ZipFile

import pytest

from ecidic.artifact import (
	EDM_DICT_FORMAT_ID,
	EDM_DICT_FORMAT_VERSION,
	MANIFEST_EXPORTING_EDM_VERSION_KEY,
	MANIFEST_FILENAME,
	MANIFEST_FORMAT_ID_KEY,
	MANIFEST_FORMAT_VERSION_KEY,
	MANIFEST_LANGUAGES_KEY,
	MANIFEST_SECTION,
	export_edm_dict_artifact,
)
from ecidic.languages import LANGUAGES
from ecidic.model import Entry, Slot
from ecidic.overlay import PersonalOverlay
from ecidic.parsing import (
	DictionaryEncodingError,
	parse_dictionary_bytes,
	serialize_dictionary_bytes,
)


def _open_artifact(data: bytes) -> ZipFile:
	return ZipFile(BytesIO(data))


def _read_manifest(zip_file: ZipFile) -> configparser.ConfigParser:
	parser = configparser.ConfigParser(interpolation=None)
	with zip_file.open(MANIFEST_FILENAME) as manifest_file:
		with TextIOWrapper(manifest_file, encoding="utf-8") as text_file:
			parser.read_file(text_file)
	return parser


def test_one_language_export_contains_canonical_dictionary_bytes_and_manifest() -> None:
	entries = (Entry("café", "crème brûlée"), Entry("jalapeño", "pepper"))
	overlay = PersonalOverlay.from_entries(("enu", Slot.MAIN, entry) for entry in entries)

	with _open_artifact(export_edm_dict_artifact(overlay, ("enu",), "0.1.0")) as zip_file:
		assert zip_file.namelist() == ["enumain.dic", MANIFEST_FILENAME]
		assert zip_file.read("enumain.dic") == serialize_dictionary_bytes(
			entries,
			"enu",
			Slot.MAIN,
		)


def test_all_languages_scope_includes_content_languages_and_excludes_empty_languages() -> None:
	overlay = PersonalOverlay.from_entries(
		[
			("enu", Slot.MAIN, Entry("word", "pronunciation")),
			("deu", Slot.ROOT, Entry("haus", "house")),
		],
	)

	with _open_artifact(
		export_edm_dict_artifact(overlay, tuple(LANGUAGES), "0.1.0"),
	) as zip_file:
		assert zip_file.namelist() == ["deuroot.dic", "enumain.dic", MANIFEST_FILENAME]
		manifest = _read_manifest(zip_file)
		assert manifest.get(MANIFEST_SECTION, MANIFEST_LANGUAGES_KEY).split(", ") == ["deu", "enu"]


def test_manifest_schema_round_trips() -> None:
	overlay = PersonalOverlay.from_entries(
		[
			("enu", Slot.MAIN, Entry("word", "pronunciation")),
			("fra", Slot.ABBREVIATION, Entry("M.", "monsieur")),
		],
	)

	with _open_artifact(export_edm_dict_artifact(overlay, ("fra", "enu"), "2.7.3-dev")) as zip_file:
		manifest = _read_manifest(zip_file)

	assert manifest.sections() == [MANIFEST_SECTION]
	assert set(manifest[MANIFEST_SECTION]) == {
		MANIFEST_FORMAT_ID_KEY,
		MANIFEST_FORMAT_VERSION_KEY,
		MANIFEST_EXPORTING_EDM_VERSION_KEY,
		MANIFEST_LANGUAGES_KEY,
	}
	assert manifest.get(MANIFEST_SECTION, MANIFEST_FORMAT_ID_KEY) == EDM_DICT_FORMAT_ID
	assert manifest.getint(MANIFEST_SECTION, MANIFEST_FORMAT_VERSION_KEY) == EDM_DICT_FORMAT_VERSION
	assert manifest.get(MANIFEST_SECTION, MANIFEST_FORMAT_VERSION_KEY) == "1"
	assert manifest.get(MANIFEST_SECTION, MANIFEST_EXPORTING_EDM_VERSION_KEY) == "2.7.3-dev"
	assert manifest.get(MANIFEST_SECTION, MANIFEST_LANGUAGES_KEY) == "enu, fra"


def test_mixed_case_scope_produces_lowercase_canonical_filenames() -> None:
	overlay = PersonalOverlay.from_entries(
		[("ENU", Slot.ABBREVIATION, Entry("Dr.", "doctor"))],
	)

	with _open_artifact(export_edm_dict_artifact(overlay, {"EnU"}, "0.1.0")) as zip_file:
		assert zip_file.namelist() == ["enuabbr.dic", MANIFEST_FILENAME]
		assert all(name == name.lower() for name in zip_file.namelist())


def test_empty_language_slot_combinations_do_not_create_dictionary_files() -> None:
	overlay = PersonalOverlay.from_entries(
		[("enu", Slot.ROOT, Entry("quinoa", "keenwah"))],
	)

	with _open_artifact(export_edm_dict_artifact(overlay, ("enu", "deu"), "0.1.0")) as zip_file:
		assert zip_file.namelist() == ["enuroot.dic", MANIFEST_FILENAME]
		manifest = _read_manifest(zip_file)
		assert manifest.get(MANIFEST_SECTION, MANIFEST_LANGUAGES_KEY) == "enu"


def test_exported_dictionary_files_round_trip_to_original_entries() -> None:
	entries_by_file = {
		"enuabbr.dic": (Entry("Dr.", "doctor"),),
		"enumain.dic": (Entry("café", "coffee"),),
		"enuroot.dic": (Entry("quinoa", "keenwah"),),
	}
	overlay = PersonalOverlay.from_entries(
		("enu", slot, entry)
		for slot, filename in (
			(Slot.ABBREVIATION, "enuabbr.dic"),
			(Slot.MAIN, "enumain.dic"),
			(Slot.ROOT, "enuroot.dic"),
		)
		for entry in entries_by_file[filename]
	)

	with _open_artifact(export_edm_dict_artifact(overlay, ("enu",), "0.1.0")) as zip_file:
		for slot, filename in (
			(Slot.ABBREVIATION, "enuabbr.dic"),
			(Slot.MAIN, "enumain.dic"),
			(Slot.ROOT, "enuroot.dic"),
		):
			assert parse_dictionary_bytes(zip_file.read(filename), "enu", slot) == entries_by_file[filename]


def test_export_surfaces_dictionary_encoding_error_for_unencodable_entries() -> None:
	overlay = PersonalOverlay.from_entries(
		[("enu", Slot.MAIN, Entry("word", "漢"))],
	)

	with pytest.raises(DictionaryEncodingError) as error:
		assert export_edm_dict_artifact(overlay, ("enu",), "0.1.0")

	assert not isinstance(error.value.__cause__, UnicodeEncodeError)


def test_export_is_byte_for_byte_deterministic() -> None:
	overlay = PersonalOverlay.from_entries(
		[
			("deu", Slot.MAIN, Entry("Haus", "house")),
			("enu", Slot.MAIN, Entry("word", "pronunciation")),
		],
	)

	first = export_edm_dict_artifact(overlay, ("enu", "deu"), "0.1.0")
	second = export_edm_dict_artifact(overlay, ("deu", "enu"), "0.1.0")

	assert first == second
