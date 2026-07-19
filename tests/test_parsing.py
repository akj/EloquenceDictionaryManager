from __future__ import annotations

from pathlib import Path

import pytest

from ecidic import (
	CANONICAL_LINE_ENDING,
	DictionaryEncodingError,
	DictionaryFilenameError,
	DictionaryFormatError,
	Entry,
	Slot,
	canonical_filename,
	find_dictionary_file,
	load_dictionary_file,
	parse_dictionary_bytes,
	parse_dictionary_filename,
	serialize_dictionary_bytes,
	write_dictionary_file,
)


@pytest.mark.parametrize(
	("name", "language", "slot"),
	[
		("enumain.dic", "enu", Slot.MAIN),
		("ENUmain.dic", "enu", Slot.MAIN),
		("ENURoot.dic", "enu", Slot.ROOT),
		("DEUabbr.dic", "deu", Slot.ABBREVIATION),
		("frcABBR.DIC", "frc", Slot.ABBREVIATION),
	],
)
def test_dictionary_filename_parser_tolerates_observed_case_conventions(
	name: str,
	language: str,
	slot: Slot,
) -> None:
	parsed = parse_dictionary_filename(name)

	assert parsed.language.code == language
	assert parsed.slot is slot
	assert parsed.canonical_name == canonical_filename(language, slot)
	assert parsed.canonical_name == parsed.canonical_name.lower()


def test_invalid_or_unsupported_filename_is_rejected() -> None:
	with pytest.raises(DictionaryFilenameError):
		_ = parse_dictionary_filename("enuwords.dic")
	with pytest.raises(DictionaryFilenameError):
		_ = parse_dictionary_filename("chsmain.dic")


def test_case_insensitive_discovery_works_on_case_sensitive_filesystems(tmp_path: Path) -> None:
	path = tmp_path / "ENURoot.dic"
	_ = path.write_bytes(b"figure\tfigyer\r\n")

	assert find_dictionary_file(tmp_path, "enu", Slot.ROOT) == path
	assert load_dictionary_file(path) == (Entry("figure", "figyer"),)


def test_case_insensitive_discovery_rejects_ambiguous_copies(tmp_path: Path) -> None:
	_ = (tmp_path / "enumain.dic").write_bytes(b"one\tone\r\n")
	_ = (tmp_path / "ENUmain.dic").write_bytes(b"two\ttwo\r\n")
	if len(list(tmp_path.iterdir())) < 2:
		pytest.skip("The test filesystem is case-insensitive")

	with pytest.raises(DictionaryFilenameError, match="More than one"):
		_ = find_dictionary_file(tmp_path, "enu", Slot.MAIN)


@pytest.mark.parametrize(
	"data",
	[
		b"alpha\tone\r\nbeta\ttwo\r\n",
		b"alpha\tone\nbeta\ttwo\n",
		b"alpha\tone\r\nbeta\ttwo\n",
	],
)
def test_parser_tolerates_crlf_lf_and_mixed_line_endings(data: bytes) -> None:
	assert parse_dictionary_bytes(data, "enu", Slot.MAIN) == (
		Entry("alpha", "one"),
		Entry("beta", "two"),
	)


@pytest.mark.parametrize(
	("slot", "canonical"),
	[
		(Slot.MAIN, "tête-à-têtes\ttext `0 here\r\n".encode("cp1252")),
		(Slot.ROOT, b"ribcage\t`[r1Ib.2keJ]\r\n"),
		(Slot.ABBREVIATION, b"Ltjg\tlieutenant junior-grade\r\n"),
	],
)
def test_canonical_bytes_round_trip_byte_for_byte(slot: Slot, canonical: bytes) -> None:
	entries = parse_dictionary_bytes(canonical, "enu", slot)

	assert serialize_dictionary_bytes(entries, "enu", slot) == canonical


def test_serialization_canonicalizes_line_endings_and_adds_final_newline() -> None:
	mixed = b"alpha\tone\r\nbeta\ttwo\ngamma\tthree"

	result = serialize_dictionary_bytes(
		parse_dictionary_bytes(mixed, "enu", Slot.MAIN),
		"enu",
		Slot.MAIN,
	)

	assert CANONICAL_LINE_ENDING == b"\r\n"
	assert result == b"alpha\tone\r\nbeta\ttwo\r\ngamma\tthree\r\n"


def test_payload_whitespace_and_cp1252_bytes_are_preserved() -> None:
	canonical = "café\tcrème brûlée \r\n".encode("cp1252")

	entries = parse_dictionary_bytes(canonical, "fra", Slot.MAIN)

	assert entries == (Entry("café", "crème brûlée "),)
	assert serialize_dictionary_bytes(entries, "fra", Slot.MAIN) == canonical


def test_writer_uses_canonical_lowercase_filename_and_bytes(tmp_path: Path) -> None:
	path = write_dictionary_file(
		tmp_path,
		"ENU",
		Slot.ABBREVIATION,
		[Entry("Dr.", "doctor")],
	)

	assert path.name == "enuabbr.dic"
	assert path.read_bytes() == b"Dr.\tdoctor\r\n"


@pytest.mark.parametrize(
	("data", "message"),
	[
		(b"blank\tline\r\n\r\n", "blank"),
		(b"no separator\r\n", "exactly one tab"),
		(b"too\tmany\ttabs\r\n", "exactly one tab"),
		(b"bare\treturn\rnext\tvalue", "line ending"),
	],
)
def test_structurally_invalid_dictionary_lines_are_rejected(data: bytes, message: str) -> None:
	with pytest.raises(DictionaryFormatError, match=message):
		_ = parse_dictionary_bytes(data, "enu", Slot.MAIN)


def test_invalid_bytes_for_language_code_page_are_rejected() -> None:
	with pytest.raises(DictionaryEncodingError, match="invalid"):
		_ = parse_dictionary_bytes(b"word\t\x81\r\n", "enu", Slot.MAIN)


def test_empty_file_round_trips() -> None:
	assert parse_dictionary_bytes(b"", "enu", Slot.MAIN) == ()
	assert serialize_dictionary_bytes([], "enu", Slot.MAIN) == b""
