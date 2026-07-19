from __future__ import annotations

import pytest

from ecidic import LANGUAGES, UnsupportedLanguageError, get_language


EXPECTED_CODES = {"enu", "eng", "esp", "esm", "fra", "frc", "deu", "ita", "ptb", "fin"}


def test_v1_language_table_has_exactly_the_ten_western_voice_codes() -> None:
	assert set(LANGUAGES) == EXPECTED_CODES
	assert all(language.encoding == "cp1252" for language in LANGUAGES.values())


def test_language_lookup_is_case_insensitive_and_returns_per_language_encoding() -> None:
	language = get_language("DEU")

	assert language.code == "deu"
	assert language.encoding == "cp1252"


@pytest.mark.parametrize("code", ["chs", "jpn", "kor", "zzz"])
def test_non_western_or_unknown_voice_codes_are_rejected(code: str) -> None:
	with pytest.raises(UnsupportedLanguageError, match=code):
		_ = get_language(code)
