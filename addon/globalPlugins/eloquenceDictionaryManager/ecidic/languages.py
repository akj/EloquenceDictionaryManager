"""Western ECI languages and their per-language on-disk encodings."""

from __future__ import annotations

from dataclasses import dataclass

try:
	import addonHandler

	addonHandler.initTranslation()
except (ImportError, ModuleNotFoundError):
	_ = lambda s: s


@dataclass(frozen=True, slots=True)
class Language:
	"""An ECI voice code and the code page used by its dictionary files."""

	code: str
	encoding: str


class UnsupportedLanguageError(ValueError):
	"""Raised when a voice code is outside the Western v1 scope."""


# Encoding deliberately lives on every language record. Future language families
# must be able to select a different code page without changing parser behavior.
LANGUAGES: dict[str, Language] = {
	code: Language(code=code, encoding=encoding)
	for code, encoding in (
		("enu", "cp1252"),
		("eng", "cp1252"),
		("esp", "cp1252"),
		("esm", "cp1252"),
		("fra", "cp1252"),
		("frc", "cp1252"),
		("deu", "cp1252"),
		("ita", "cp1252"),
		("ptb", "cp1252"),
		("fin", "cp1252"),
	)
}


def get_language(code: str) -> Language:
	"""Look up one of the ten Western v1 languages by ECI voice code."""

	try:
		return LANGUAGES[code.lower()]
	except KeyError as error:
		# Translators: Error shown when a dictionary uses an unsupported ECI voice code.
		message = _('The ECI voice code "{code}" is not supported.').format(code=code)
		raise UnsupportedLanguageError(message) from error
