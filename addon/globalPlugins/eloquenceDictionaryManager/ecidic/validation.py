"""Slot-aware validation for Western ECI dictionary entries."""

from __future__ import annotations

import re
import string
import unicodedata
from dataclasses import dataclass
from enum import Enum

from .languages import Language, get_language
from .model import Entry, Slot, coerce_slot

try:
	import addonHandler

	addonHandler.initTranslation()
except (ImportError, ModuleNotFoundError):

	def _(text: str) -> str:
		return text


class Field(str, Enum):
	"""The editor field associated with a validation failure."""

	KEY = "key"
	VALUE = "value"


class ValidationCode(str, Enum):
	"""Stable machine-readable identities for validation failures."""

	EMPTY_KEY = "emptyKey"
	EMPTY_VALUE = "emptyValue"
	KEY_TAB = "keyTab"
	VALUE_TAB = "valueTab"
	KEY_NEWLINE = "keyNewline"
	VALUE_NEWLINE = "valueNewline"
	KEY_NUL = "keyNul"
	VALUE_NUL = "valueNul"
	MAIN_KEY_WHITESPACE = "mainKeyWhitespace"
	MAIN_KEY_FINAL_PUNCTUATION = "mainKeyFinalPunctuation"
	ROOT_KEY_INVALID = "rootKeyInvalid"
	ROOT_VALUE_INVALID = "rootValueInvalid"
	ABBREVIATION_KEY_INVALID = "abbreviationKeyInvalid"
	ABBREVIATION_VALUE_INVALID = "abbreviationValueInvalid"
	UNENCODABLE_CHARACTER = "unencodableCharacter"
	KEY_TOO_LONG = "keyTooLong"
	VALUE_TOO_LONG = "valueTooLong"
	SPR_UNCLOSED = "sprUnclosed"
	SPR_EMPTY = "sprEmpty"
	SPR_QUOTE_INVALID = "sprQuoteInvalid"
	SPR_PRIMARY_STRESS_REQUIRED = "sprPrimaryStressRequired"
	ANNOTATION_INVALID = "annotationInvalid"
	SPELLING_MODE_UNCLOSED = "spellingModeUnclosed"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
	"""One specific validation failure suitable for display in the editor."""

	code: ValidationCode
	field: Field
	message: str


class WarningCode(str, Enum):
	"""Stable machine-readable identities for validation warnings."""

	ABBREVIATION_KEY_NEVER_MATCHES = "abbreviationKeyNeverMatches"


@dataclass(frozen=True, slots=True)
class ValidationWarning:
	"""A problem with a valid entry: the engine loads it but never applies it."""

	code: WarningCode
	field: Field
	message: str


MAX_KEY_BYTES = 128
"""The longest key, in bytes in the voice's code page, that Eloquence accepts."""

MAX_VALUE_BYTES = 512
"""The longest value, in bytes in the voice's code page, that Eloquence accepts."""

# Engine tests on #173: these voices load an abbreviation key with a hyphen, slash or ampersand
# but never match it.
_NEVER_MATCHING_ABBREVIATION_LANGUAGES = frozenset({"enu", "eng"})
_NEVER_MATCHING_ABBREVIATION_CHARACTERS = frozenset("-/&")

# A period joins two abbreviation words, and a hyphen may follow it, as in "Dipl.-Ing.".
_ABBREVIATION_SEPARATOR = re.compile(r"\.-?")
# English voices also load a hyphen, slash or ampersand on its own between two words.
_ENGLISH_ABBREVIATION_SEPARATOR = re.compile(r"\.-?|[-/&]")


# The backquote codes a value may carry: a phonetic string, an emphasis code, or a spelling-mode
# code. Any other annotation, such as a pause, voice, volume or language code, can silence or
# derail speech well past the word, so it makes the entry invalid.
_ANNOTATION = re.compile(r"`(?:(?P<spr>\[)|(?P<emphasis>00|[0-4])(?=\s)|ts(?P<spelling>[0-3])(?!\d))")


class EntryValidationError(ValueError):
	"""Raised when an entry cannot be written safely."""

	def __init__(self, issue: ValidationIssue):
		super().__init__(issue.message)
		self.issue = issue


def _issue(code: ValidationCode, field: Field, message: str) -> ValidationIssue:
	return ValidationIssue(code=code, field=field, message=message)


def _mechanical_issues(entry: Entry) -> list[ValidationIssue]:
	issues: list[ValidationIssue] = []
	if not entry.key:
		# Translators: Validation error when the dictionary word field is empty.
		issues.append(_issue(ValidationCode.EMPTY_KEY, Field.KEY, _("A word is required.")))
	if not entry.value:
		issues.append(
			# Translators: Validation error when the pronunciation field is empty.
			_issue(ValidationCode.EMPTY_VALUE, Field.VALUE, _("A pronunciation is required.")),
		)
	for field, text in ((Field.KEY, entry.key), (Field.VALUE, entry.value)):
		if "\t" in text:
			if field is Field.KEY:
				# Translators: Validation error when a tab was pasted into the word field.
				message = _("The word cannot contain a tab character.")
				code = ValidationCode.KEY_TAB
			else:
				# Translators: Validation error when a tab was pasted into the pronunciation field.
				message = _("The pronunciation cannot contain a tab character.")
				code = ValidationCode.VALUE_TAB
			issues.append(_issue(code, field, message))
		if "\r" in text or "\n" in text:
			if field is Field.KEY:
				# Translators: Validation error when a line break was pasted into the word field.
				message = _("The word cannot contain a line break.")
				code = ValidationCode.KEY_NEWLINE
			else:
				# Translators: Validation error when a line break was pasted into the pronunciation field.
				message = _("The pronunciation cannot contain a line break.")
				code = ValidationCode.VALUE_NEWLINE
			issues.append(_issue(code, field, message))
		if "\0" in text:
			if field is Field.KEY:
				# Translators: Validation error when a NUL control character occurs in the word field.
				message = _("The word cannot contain a NUL character.")
				code = ValidationCode.KEY_NUL
			else:
				# Translators: Validation error when a NUL control character occurs in the pronunciation field.
				message = _("The pronunciation cannot contain a NUL character.")
				code = ValidationCode.VALUE_NUL
			issues.append(_issue(code, field, message))
	return issues


def _is_punctuation(character: str) -> bool:
	return character in string.punctuation or unicodedata.category(character).startswith("P")


def _is_bare_spr(value: str) -> bool:
	if not value.startswith("`["):
		return False
	closing = value.find("]", 2)
	return closing == len(value) - 1 and value.find("`[", 2) == -1


def _is_word_with_internal_apostrophes(word: str) -> bool:
	"""Return whether *word* is letters, optionally joined by single apostrophes.

	An apostrophe may not start or end the word, and two may not be adjacent.
	"""

	return all(part.isalpha() for part in word.split("'"))


def _valid_abbreviation_key(key: str, language: Language) -> bool:
	"""Return whether *key* is words joined by periods, with an optional trailing period.

	Each word is letters with optional internal apostrophes. A hyphen is allowed
	straight after a joining period, as in "Dipl.-Ing.". English voices also accept
	a hyphen, slash or ampersand in place of a joining period, as in "AT&T"; the
	engine loads those keys but never matches them, so :func:`entry_warnings`
	reports them.
	"""

	body = key[:-1] if key.endswith(".") else key
	separator = (
		_ENGLISH_ABBREVIATION_SEPARATOR
		if language.code in _NEVER_MATCHING_ABBREVIATION_LANGUAGES
		else _ABBREVIATION_SEPARATOR
	)
	return all(_is_word_with_internal_apostrophes(part) for part in separator.split(body))


def _valid_abbreviation_value(value: str) -> bool:
	if not value or value[0] in " -" or value[-1] in " -":
		return False
	parts = value.replace("-", " ").split(" ")
	return bool(parts) and all(part.isalpha() for part in parts)


def _slot_issues(entry: Entry, slot: Slot, language: Language) -> list[ValidationIssue]:
	issues: list[ValidationIssue] = []
	if not entry.key or not entry.value:
		return issues
	if slot is Slot.MAIN:
		if any(character.isspace() for character in entry.key):
			message = _(
				# Translators: Exact-word validation error; entries match one token at a time.
				"The word cannot contain spaces. Dictionary entries match one word at a time.",
			)
			issues.append(_issue(ValidationCode.MAIN_KEY_WHITESPACE, Field.KEY, message))
		if _is_punctuation(entry.key[-1]):
			message = _(
				# Translators: Exact-word validation error. The first placeholder is the word and the second is its final punctuation character.
				'The word cannot end with punctuation ("{word}" ends with "{character}").',
			).format(word=entry.key, character=entry.key[-1])
			issues.append(
				_issue(ValidationCode.MAIN_KEY_FINAL_PUNCTUATION, Field.KEY, message),
			)
	elif slot is Slot.ROOT:
		if not _is_word_with_internal_apostrophes(entry.key):
			message = _(
				# Translators: Word-root validation error. {word} is the invalid word root.
				'Word roots can contain only letters, with apostrophes inside the word. "{word}" cannot be a word root — for words with digits or symbols, use an Exact word entry.',
			).format(word=entry.key)
			issues.append(_issue(ValidationCode.ROOT_KEY_INVALID, Field.KEY, message))
		if not (entry.value.isalpha() or _is_bare_spr(entry.value)):
			message = _(
				# Translators: Word-root validation error describing the two permitted pronunciation forms.
				"A word root pronunciation must be a single word or one phonetic string (`[...]) — no spaces, digits, or emphasis codes.",
			)
			issues.append(_issue(ValidationCode.ROOT_VALUE_INVALID, Field.VALUE, message))
	else:
		if not _valid_abbreviation_key(entry.key, language):
			message = _(
				# Translators: Abbreviation validation error with examples of permitted keys.
				'An abbreviation can contain only letters and periods, with apostrophes inside the word and hyphens straight after a period — for example "Dr.", "e.g." or "Dipl.-Ing.".',
			)
			issues.append(
				_issue(ValidationCode.ABBREVIATION_KEY_INVALID, Field.KEY, message),
			)
		if not _valid_abbreviation_value(entry.value):
			message = _(
				# Translators: Abbreviation validation error describing permitted expansion text.
				"An abbreviation expansion must be plain words separated by spaces or hyphens — no digits, punctuation, or phonetic symbols.",
			)
			issues.append(
				_issue(ValidationCode.ABBREVIATION_VALUE_INVALID, Field.VALUE, message),
			)
	return issues


def find_unencodable_character(text: str, language: Language | str) -> str | None:
	"""Return the first character not representable by *language*, if any."""

	language_record = get_language(language) if isinstance(language, str) else language
	for character in text:
		try:
			_encoded = character.encode(language_record.encoding, errors="strict")
		except UnicodeEncodeError:
			return character
	return None


def _encoding_issues(entry: Entry, language: Language) -> list[ValidationIssue]:
	issues: list[ValidationIssue] = []
	for field, text in ((Field.KEY, entry.key), (Field.VALUE, entry.value)):
		character = find_unencodable_character(text, language)
		if character is not None:
			message = _(
				# Translators: Encoding validation error. {character} is the unsupported character.
				'The character "{character}" cannot be saved in an Eloquence dictionary (Western encoding only).',
			).format(character=character)
			issues.append(_issue(ValidationCode.UNENCODABLE_CHARACTER, field, message))
	return issues


def _length_issues(entry: Entry, language: Language) -> list[ValidationIssue]:
	"""Check the encoded length of each field; an unencodable field fails the encoding rule instead."""

	issues: list[ValidationIssue] = []
	for field, text, limit in (
		(Field.KEY, entry.key, MAX_KEY_BYTES),
		(Field.VALUE, entry.value, MAX_VALUE_BYTES),
	):
		try:
			length = len(text.encode(language.encoding, errors="strict"))
		except UnicodeEncodeError:
			continue
		if length <= limit:
			continue
		# Every v1 voice uses a single-byte code page, so bytes and characters are the same count.
		if field is Field.KEY:
			message = _(
				# Translators: Validation error when the dictionary word is too long. {limit} is the maximum number of characters and {length} is the number entered.
				"The word can be at most {limit} characters long, but it has {length}.",
			).format(limit=limit, length=length)
			code = ValidationCode.KEY_TOO_LONG
		else:
			message = _(
				# Translators: Validation error when the pronunciation is too long. {limit} is the maximum number of characters and {length} is the number entered.
				"The pronunciation can be at most {limit} characters long, but it has {length}.",
			).format(limit=limit, length=length)
			code = ValidationCode.VALUE_TOO_LONG
		issues.append(_issue(code, field, message))
	return issues


def _spr_issues(value: str) -> list[ValidationIssue]:
	issues: list[ValidationIssue] = []
	position = 0
	while True:
		start = value.find("`[", position)
		if start < 0:
			break
		end = value.find("]", start + 2)
		nested = value.find("`[", start + 2)
		if end < 0 or (nested >= 0 and nested < end):
			message = _(
				# Translators: SPR validation error when a phonetic string has no matching closing bracket.
				'The phonetic string is not closed — expected "]" after "`[".',
			)
			issues.append(_issue(ValidationCode.SPR_UNCLOSED, Field.VALUE, message))
			break
		body = value[start + 2 : end]
		if not body:
			# Translators: SPR validation error when a phonetic string contains no symbols.
			message = _("The phonetic string cannot be empty.")
			issues.append(_issue(ValidationCode.SPR_EMPTY, Field.VALUE, message))
		quote_parts = body.split("'")
		if len(quote_parts) % 2 == 0 or any(
			len(quote_parts[index]) != 2 for index in range(1, len(quote_parts), 2)
		):
			message = _(
				# Translators: SPR validation error for malformed quoting around a two-character phoneme symbol.
				"A quoted phonetic symbol must contain exactly two characters between matching apostrophes.",
			)
			issues.append(_issue(ValidationCode.SPR_QUOTE_INVALID, Field.VALUE, message))
		if body.count(".") + 1 > 1 and "1" not in body:
			message = _(
				# Translators: SPR validation error when a multi-syllable phonetic string has no primary stress marker.
				'A phonetic string with more than one syllable needs a primary stress marker "1", for example `[.1kwi.0nwa].',
			)
			issues.append(
				_issue(ValidationCode.SPR_PRIMARY_STRESS_REQUIRED, Field.VALUE, message),
			)
		position = end + 1
	return issues


def _annotation_issues(value: str) -> list[ValidationIssue]:
	"""Check that every backquote in *value* begins a permitted annotation.

	A phonetic string or an emphasis code must start the value or follow whitespace,
	and an emphasis code must be followed by whitespace. A spelling-mode code may sit
	anywhere, and one that turns spelling on must be turned off with ``ts0`` before
	the value ends. SPR structure is checked separately.
	"""

	spelling_on = False
	position = value.find("`")
	while position >= 0:
		match = _ANNOTATION.match(value, position)
		after_space = position == 0 or value[position - 1].isspace()
		if match is None or (match["spelling"] is None and not after_space):
			message = _(
				# Translators: Validation error when the pronunciation contains a backquote code that is not allowed. `[...], `0, `4, `00, `ts0 and `ts3 are literal codes and must not be translated.
				"A backquote can only start a phonetic string (`[...]), an emphasis code after a space (`0 to `4, or `00), or a spelling code (`ts0 to `ts3). Other backquote codes are not allowed.",
			)
			return [_issue(ValidationCode.ANNOTATION_INVALID, Field.VALUE, message)]
		if match["spelling"] is not None:
			spelling_on = match["spelling"] != "0"
		position = value.find("`", position + 1)
	if spelling_on:
		message = _(
			# Translators: Validation error when the pronunciation turns on a spelling mode and does not turn it off. `ts0, `ts1, `ts2 and `ts3 are literal codes and must not be translated.
			"The pronunciation turns on spelling with `ts1, `ts2 or `ts3, but does not turn it off with `ts0 before it ends.",
		)
		return [_issue(ValidationCode.SPELLING_MODE_UNCLOSED, Field.VALUE, message)]
	return []


def validate_entry(
	entry: Entry,
	slot: Slot | str,
	language: Language | str,
) -> tuple[ValidationIssue, ...]:
	"""Return all validation failures in the editor's documented check order."""

	slot_value = coerce_slot(slot)
	language_record = get_language(language) if isinstance(language, str) else language
	mechanical = _mechanical_issues(entry)
	issues = list(mechanical)
	mechanically_invalid_fields = {issue.field for issue in mechanical}
	if not mechanically_invalid_fields:
		issues.extend(_slot_issues(entry, slot_value, language_record))
	issues.extend(_encoding_issues(entry, language_record))
	issues.extend(_length_issues(entry, language_record))
	if Field.VALUE not in mechanically_invalid_fields:
		if slot_value is not Slot.ABBREVIATION:
			issues.extend(_spr_issues(entry.value))
		issues.extend(_annotation_issues(entry.value))
	return tuple(issues)


def entry_warnings(
	entry: Entry,
	slot: Slot | str,
	language: Language | str,
) -> tuple[ValidationWarning, ...]:
	"""Return warnings for an entry that passes :func:`validate_entry`.

	A warned entry is valid and the engine loads it, but never applies it. An
	entry that fails validation has no warnings.
	"""

	slot_value = coerce_slot(slot)
	language_record = get_language(language) if isinstance(language, str) else language
	if validate_entry(entry, slot_value, language_record):
		return ()
	if (
		slot_value is Slot.ABBREVIATION
		and language_record.code in _NEVER_MATCHING_ABBREVIATION_LANGUAGES
		and not _NEVER_MATCHING_ABBREVIATION_CHARACTERS.isdisjoint(entry.key)
	):
		message = _(
			# Translators: Abbreviation error for English voices, which load an abbreviation containing a hyphen, slash or ampersand but never use it.
			"Eloquence would never use this entry, because English abbreviations with a hyphen, slash or ampersand never match. Use an Exact word entry instead.",
		)
		return (
			ValidationWarning(
				code=WarningCode.ABBREVIATION_KEY_NEVER_MATCHES,
				field=Field.KEY,
				message=message,
			),
		)
	return ()


def validate_or_raise(entry: Entry, slot: Slot | str, language: Language | str) -> None:
	"""Raise :class:`EntryValidationError` for the first validation failure."""

	issues = validate_entry(entry, slot, language)
	if issues:
		raise EntryValidationError(issues[0])


def normalize_entry(entry: Entry, slot: Slot | str) -> Entry:
	"""Apply the one editor normalization: root keys are stored lowercase."""

	if coerce_slot(slot) is Slot.ROOT:
		return Entry(key=entry.key.lower(), value=entry.value)
	return entry


def validated_entry(
	entry: Entry,
	slot: Slot | str,
	language: Language | str,
) -> Entry:
	"""Validate *entry* and return its canonical stored representation."""

	validate_or_raise(entry, slot, language)
	return normalize_entry(entry, slot)
