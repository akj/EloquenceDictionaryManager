from __future__ import annotations

import pytest

from ecidic import (
	DictionaryEncodingError,
	Entry,
	EntryValidationError,
	Field,
	Slot,
	ValidationCode,
	serialize_dictionary_bytes,
	validate_entry,
	validate_or_raise,
	validated_entry,
)


def codes(entry: Entry, slot: Slot = Slot.MAIN, language: str = "enu") -> list[ValidationCode]:
	return [issue.code for issue in validate_entry(entry, slot, language)]


@pytest.mark.parametrize(
	("entry", "expected"),
	[
		(Entry("", "value"), ValidationCode.EMPTY_KEY),
		(Entry("word", ""), ValidationCode.EMPTY_VALUE),
		(Entry("bad\tkey", "value"), ValidationCode.KEY_TAB),
		(Entry("word", "bad\tvalue"), ValidationCode.VALUE_TAB),
		(Entry("bad\nkey", "value"), ValidationCode.KEY_NEWLINE),
		(Entry("word", "bad\r\nvalue"), ValidationCode.VALUE_NEWLINE),
		(Entry("bad\0key", "value"), ValidationCode.KEY_NUL),
		(Entry("word", "bad\0value"), ValidationCode.VALUE_NUL),
	],
)
def test_mechanical_validation_catalog(entry: Entry, expected: ValidationCode) -> None:
	issues = validate_entry(entry, Slot.MAIN, "enu")

	assert issues[0].code is expected
	assert issues[0].message


@pytest.mark.parametrize(
	("entry", "expected"),
	[
		(Entry("two words", "value"), ValidationCode.MAIN_KEY_WHITESPACE),
		(Entry("win!", "value"), ValidationCode.MAIN_KEY_FINAL_PUNCTUATION),
	],
)
def test_exact_word_validation_catalog(entry: Entry, expected: ValidationCode) -> None:
	assert codes(entry) == [expected]


def test_exact_word_values_allow_text_annotations_and_structurally_valid_sprs() -> None:
	entry = Entry("quinoa", "ordinary text `0 and `[.1kwi.0nwa]")

	assert validate_entry(entry, Slot.MAIN, "enu") == ()


@pytest.mark.parametrize(
	("entry", "expected"),
	[
		(Entry("Win32", "word"), ValidationCode.ROOT_KEY_NOT_LETTERS),
		(Entry("root", "two words"), ValidationCode.ROOT_VALUE_INVALID),
		(Entry("root", "word2"), ValidationCode.ROOT_VALUE_INVALID),
		(Entry("root", "`0 word"), ValidationCode.ROOT_VALUE_INVALID),
	],
)
def test_word_root_validation_catalog(entry: Entry, expected: ValidationCode) -> None:
	assert codes(entry, Slot.ROOT)[0] is expected


def test_word_root_allows_bare_word_or_bare_spr_and_is_stored_lowercase() -> None:
	assert validate_entry(Entry("Quinoa", "keenwah"), Slot.ROOT, "enu") == ()
	assert validate_entry(Entry("quinoa", "`[.1kwi.0nwa]"), Slot.ROOT, "enu") == ()
	assert validated_entry(Entry("Quinoa", "keenwah"), Slot.ROOT, "enu") == Entry(
		"quinoa",
		"keenwah",
	)


@pytest.mark.parametrize(
	"key",
	[".Dr", "Dr..", "Dr'", "'Dr", "D''r", "Dr!", "D2", "two words"],
)
def test_abbreviation_key_validation_catalog(key: str) -> None:
	assert codes(Entry(key, "doctor"), Slot.ABBREVIATION) == [
		ValidationCode.ABBREVIATION_KEY_INVALID,
	]


@pytest.mark.parametrize(
	"value",
	["word2", "word!", "`[w3d]", " leading", "trailing ", "two  words", "two--words"],
)
def test_abbreviation_value_validation_catalog(value: str) -> None:
	assert codes(Entry("Dr.", value), Slot.ABBREVIATION) == [
		ValidationCode.ABBREVIATION_VALUE_INVALID,
	]


@pytest.mark.parametrize("key", ["Dr.", "e.g.", "approx", "O'Neill"])
def test_valid_abbreviation_key_forms(key: str) -> None:
	assert validate_entry(Entry(key, "plain words-separated"), Slot.ABBREVIATION, "enu") == ()


@pytest.mark.parametrize(
	("value", "expected"),
	[
		("`[abc", ValidationCode.SPR_UNCLOSED),
		("`[]", ValidationCode.SPR_EMPTY),
		("`[.abc]", ValidationCode.SPR_PRIMARY_STRESS_REQUIRED),
		("`[.1a.'b]", ValidationCode.SPR_QUOTE_INVALID),
		("`[.1a.'abc']", ValidationCode.SPR_QUOTE_INVALID),
	],
)
def test_spr_structure_validation_catalog(value: str, expected: ValidationCode) -> None:
	assert expected in codes(Entry("word", value), Slot.MAIN)


def test_spr_validation_does_not_check_language_specific_phoneme_legality() -> None:
	assert validate_entry(Entry("word", "`[.1ZZZ]"), Slot.MAIN, "enu") == ()


@pytest.mark.parametrize(
	("entry", "field"),
	[
		(Entry("漢", "word"), Field.KEY),
		(Entry("word", "漢"), Field.VALUE),
	],
)
def test_unencodable_characters_are_rejected_loudly(entry: Entry, field: Field) -> None:
	issues = validate_entry(entry, Slot.MAIN, "enu")
	encoding_issue = next(issue for issue in issues if issue.code is ValidationCode.UNENCODABLE_CHARACTER)

	assert encoding_issue.field is field
	assert "漢" in encoding_issue.message
	assert "Western encoding only" in encoding_issue.message
	with pytest.raises(EntryValidationError) as error:
		validate_or_raise(entry, Slot.MAIN, "enu")
	assert error.value.issue.code is ValidationCode.UNENCODABLE_CHARACTER


def test_serializer_never_replaces_or_strips_unencodable_text_even_without_validation() -> None:
	with pytest.raises(DictionaryEncodingError, match="漢"):
		serialize_dictionary_bytes(
			[Entry("word", "漢")],
			"enu",
			Slot.MAIN,
			validate=False,
		)
