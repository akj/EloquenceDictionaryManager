from __future__ import annotations

import configparser
from io import BytesIO, TextIOWrapper
from zipfile import ZIP_STORED, ZipFile

import pytest

from ecidic.artifact import (
	CollisionResolution,
	EDM_DICT_FORMAT_ID,
	EDM_DICT_FORMAT_VERSION,
	ImportMode,
	InvalidArtifactError,
	MANIFEST_EXPORTING_EDM_VERSION_KEY,
	MANIFEST_FILENAME,
	MANIFEST_FORMAT_ID_KEY,
	MANIFEST_FORMAT_VERSION_KEY,
	MANIFEST_LANGUAGES_KEY,
	MANIFEST_SECTION,
	apply_import_plan,
	build_import_plan,
	export_edm_dict_artifact,
	read_edm_dict_artifact,
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


def _manifest_bytes(
	*,
	format_id: str = EDM_DICT_FORMAT_ID,
	format_version: str | None = None,
	languages: str = "enu",
) -> bytes:
	if format_version is None:
		format_version = str(EDM_DICT_FORMAT_VERSION)
	return (
		f"[{MANIFEST_SECTION}]\n"
		f"{MANIFEST_FORMAT_ID_KEY} = {format_id}\n"
		f"{MANIFEST_FORMAT_VERSION_KEY} = {format_version}\n"
		f"{MANIFEST_LANGUAGES_KEY} = {languages}\n"
	).encode()


def _build_artifact(members: dict[str, bytes]) -> bytes:
	archive = BytesIO()
	with ZipFile(archive, mode="w", compression=ZIP_STORED) as zip_file:
		for filename, data in members.items():
			zip_file.writestr(filename, data)
	return archive.getvalue()


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


def test_exported_artifact_round_trips_through_merge_import() -> None:
	source = PersonalOverlay.from_entries(
		[
			("enu", Slot.MAIN, Entry("café", "coffee")),
			("enu", Slot.ROOT, Entry("figures", "figure")),
			("fra", Slot.ABBREVIATION, Entry("M.", "monsieur")),
		],
	)
	artifact_bytes = export_edm_dict_artifact(source, ("enu", "fra"), "0.1.0")

	artifact = read_edm_dict_artifact(artifact_bytes)
	target = PersonalOverlay()
	result = apply_import_plan(target, build_import_plan(artifact, target))

	assert artifact.languages == ("enu", "fra")
	assert target.entries == source.entries
	assert result.imported == 3
	assert result.collisions_kept == 0
	assert result.collisions_replaced == 0
	assert result.skipped_invalid == 0
	assert export_edm_dict_artifact(target, artifact.languages, "0.1.0") == artifact_bytes


def test_exported_artifact_round_trips_through_replace_import() -> None:
	source = PersonalOverlay.from_entries(
		[
			("enu", Slot.MAIN, Entry("new", "imported")),
			("deu", Slot.MAIN, Entry("Haus", "house")),
		],
	)
	target = PersonalOverlay.from_entries(
		[
			("enu", Slot.MAIN, Entry("old", "personal")),
			("deu", Slot.ROOT, Entry("alt", "old")),
			("fra", Slot.MAIN, Entry("bonjour", "salut")),
		],
	)
	artifact = read_edm_dict_artifact(export_edm_dict_artifact(source, ("enu", "deu"), "0.1.0"))

	result = apply_import_plan(target, build_import_plan(artifact, target), ImportMode.REPLACE)

	assert target.get_entry("enu", Slot.MAIN, "old") is None
	assert target.get_entry("deu", Slot.ROOT, "alt") is None
	assert target.get_entry("enu", Slot.MAIN, "new") == Entry("new", "imported")
	assert target.get_entry("deu", Slot.MAIN, "Haus") == Entry("Haus", "house")
	assert target.get_entry("fra", Slot.MAIN, "bonjour") == Entry("bonjour", "salut")
	assert result.imported == 2
	assert result.collisions_kept == 0
	assert result.collisions_replaced == 0


def test_read_rejects_unreadable_non_zip_artifact() -> None:
	with pytest.raises(InvalidArtifactError, match="could not be opened or read"):
		assert read_edm_dict_artifact(b"not a zip archive")


def test_read_rejects_artifact_without_manifest() -> None:
	data = _build_artifact({"enumain.dic": b"word\tpronunciation\r\n"})

	with pytest.raises(InvalidArtifactError, match="exactly one"):
		assert read_edm_dict_artifact(data)


def test_read_rejects_artifact_with_wrong_format_id() -> None:
	data = _build_artifact({MANIFEST_FILENAME: _manifest_bytes(format_id="another-format")})

	with pytest.raises(InvalidArtifactError, match="not an Eloquence Dictionary Manager"):
		assert read_edm_dict_artifact(data)


def test_read_rejects_artifact_with_corrupt_manifest() -> None:
	data = _build_artifact({MANIFEST_FILENAME: b"this is not INI data"})

	with pytest.raises(InvalidArtifactError, match="manifest"):
		assert read_edm_dict_artifact(data)


def test_read_rejects_artifact_with_newer_major_format_version() -> None:
	newer_version = EDM_DICT_FORMAT_VERSION + 1
	data = _build_artifact(
		{MANIFEST_FILENAME: _manifest_bytes(format_version=str(newer_version))},
	)

	with pytest.raises(InvalidArtifactError, match=rf"version {newer_version}.*version 1"):
		assert read_edm_dict_artifact(data)


def test_read_accepts_older_format_and_ignores_unrecognized_members() -> None:
	data = _build_artifact(
		{
			MANIFEST_FILENAME: _manifest_bytes(format_version="0"),
			"enumain.dic": b"word\tpronunciation\r\n",
			"notes.txt": b"ignored",
		},
	)

	artifact = read_edm_dict_artifact(data)

	assert artifact.languages == ("enu",)
	assert artifact.dictionaries[0].entries == (Entry("word", "pronunciation"),)


def test_read_rejects_dictionary_member_that_fails_to_parse() -> None:
	data = _build_artifact(
		{
			MANIFEST_FILENAME: _manifest_bytes(),
			"enumain.dic": b"missing tab separator\r\n",
		},
	)

	with pytest.raises(InvalidArtifactError, match="invalid dictionary file"):
		assert read_edm_dict_artifact(data)


def test_collision_requires_same_language_slot_and_word() -> None:
	source = PersonalOverlay.from_entries(
		[
			("enu", Slot.MAIN, Entry("word", "imported main")),
			("enu", Slot.ROOT, Entry("root", "importedroot")),
			("deu", Slot.MAIN, Entry("gleich", "imported")),
		],
	)
	target = PersonalOverlay.from_entries(
		[
			("enu", Slot.MAIN, Entry("word", "mine")),
			("enu", Slot.ABBREVIATION, Entry("root", "personal")),
			("fra", Slot.MAIN, Entry("gleich", "personal")),
		],
	)
	artifact = read_edm_dict_artifact(export_edm_dict_artifact(source, ("enu", "deu"), "0.1.0"))

	plan = build_import_plan(artifact, target)

	assert plan.collision_count == 1
	assert [(item.language, item.slot, item.entry.key) for item in plan.entries if item.collision] == [
		("enu", Slot.MAIN, "word"),
	]


@pytest.mark.parametrize(
	("resolution", "expected_collision", "expected_result"),
	[
		(
			CollisionResolution.KEEP_PERSONAL,
			Entry("word", "mine"),
			(1, 1, 0),
		),
		(
			CollisionResolution.USE_IMPORTED,
			Entry("word", "imported"),
			(2, 0, 1),
		),
	],
)
def test_merge_collision_resolution_never_blocks_nonconflicting_entries(
	resolution: CollisionResolution,
	expected_collision: Entry,
	expected_result: tuple[int, int, int],
) -> None:
	source = PersonalOverlay.from_entries(
		[
			("enu", Slot.MAIN, Entry("word", "imported")),
			("enu", Slot.MAIN, Entry("new", "always merged")),
		],
	)
	target = PersonalOverlay.from_entries(
		[("enu", Slot.MAIN, Entry("word", "mine"))],
	)
	artifact = read_edm_dict_artifact(export_edm_dict_artifact(source, ("enu",), "0.1.0"))
	plan = build_import_plan(artifact, target)

	result = apply_import_plan(target, plan, ImportMode.MERGE, resolution)

	assert target.get_entry("enu", Slot.MAIN, "word") == expected_collision
	assert target.get_entry("enu", Slot.MAIN, "new") == Entry("new", "always merged")
	assert (result.imported, result.collisions_kept, result.collisions_replaced) == expected_result


def test_invalid_editor_entries_are_skipped_and_counted() -> None:
	data = _build_artifact(
		{
			MANIFEST_FILENAME: _manifest_bytes(),
			"enumain.dic": b"two words\tinvalid\r\nvalid\tpronunciation\r\n",
		},
	)
	artifact = read_edm_dict_artifact(data)
	target = PersonalOverlay()

	plan = build_import_plan(artifact, target)
	result = apply_import_plan(target, plan)

	assert plan.skipped_invalid == 1
	assert result.skipped_invalid == 1
	assert result.imported == 1
	assert target.get_entry("enu", Slot.MAIN, "two words") is None
	assert target.get_entry("enu", Slot.MAIN, "valid") == Entry("valid", "pronunciation")
