"""Efficient membership checks for the shipped historical-line union.

Each artifact file contains sorted, unique, raw 32-byte SHA-256 digests with
no header or separators. There is one file per ``(language, slot)``. A digest
is SHA-256 over the normalized ``key<TAB>value`` text encoded as UTF-8; UTF-8
makes hashes independent of the source dictionary's on-disk code page.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from .languages import Language, get_language
from .model import Slot, coerce_slot


DIGEST_SIZE = hashlib.sha256().digest_size
DEFAULT_ARTIFACT_ROOT = Path(__file__).parents[3] / "dictionaries" / "historicalUnion"


class HistoricalUnionFormatError(ValueError):
	"""Raised when a normalized line or shipped artifact is malformed."""


def historical_artifact_name(language: Language | str, slot: Slot | str) -> str:
	"""Return the artifact filename for one language and dictionary slot."""

	language_record = get_language(language) if isinstance(language, str) else language
	return f"{language_record.code}{coerce_slot(slot).value}.sha256"


def normalize_historical_line(key: str, value: str, slot: Slot | str) -> bytes:
	"""Return the canonical UTF-8 bytes hashed by the historical-union workflow.

	Line endings are absent because callers pass the already separated key and
	value. Whitespace and value text remain exact. Only root keys are case-folded.
	"""

	if any(character in key or character in value for character in ("\t", "\r", "\n")):
		raise HistoricalUnionFormatError(
			"Historical-union keys and values must not contain tabs or line endings.",
		)
	slot_value = coerce_slot(slot)
	normalized_key = key.casefold() if slot_value is Slot.ROOT else key
	return f"{normalized_key}\t{value}".encode("utf-8")


def historical_line_digest(key: str, value: str, slot: Slot | str) -> bytes:
	"""Hash one normalized historical dictionary line with SHA-256."""

	return hashlib.sha256(normalize_historical_line(key, value, slot)).digest()


def validate_historical_artifact(data: bytes, path: Path) -> None:
	"""Validate the framing and sort order required for binary search."""

	if len(data) % DIGEST_SIZE:
		raise HistoricalUnionFormatError(
			f"Historical-union artifact {path} is not a sequence of {DIGEST_SIZE}-byte digests.",
		)
	for offset in range(DIGEST_SIZE, len(data), DIGEST_SIZE):
		previous = data[offset - DIGEST_SIZE : offset]
		current = data[offset : offset + DIGEST_SIZE]
		if previous >= current:
			raise HistoricalUnionFormatError(
				f"Historical-union artifact {path} is not strictly sorted and unique.",
			)


def _contains_digest(data: bytes, digest: bytes) -> bool:
	low = 0
	high = len(data) // DIGEST_SIZE
	while low < high:
		middle = (low + high) // 2
		offset = middle * DIGEST_SIZE
		candidate = data[offset : offset + DIGEST_SIZE]
		if candidate < digest:
			low = middle + 1
		else:
			high = middle
	offset = low * DIGEST_SIZE
	return offset < len(data) and data[offset : offset + DIGEST_SIZE] == digest


@dataclass(slots=True)
class HistoricalUnion:
	"""Lazily load per-language artifacts and answer membership in O(log n)."""

	artifact_root: Path = DEFAULT_ARTIFACT_ROOT
	_artifacts: dict[tuple[str, Slot], bytes] = field(
		default_factory=dict[tuple[str, Slot], bytes],
		init=False,
		repr=False,
	)

	def _artifact(self, language: Language, slot: Slot) -> bytes:
		cache_key = (language.code, slot)
		if cache_key not in self._artifacts:
			path = self.artifact_root / historical_artifact_name(language, slot)
			try:
				data = path.read_bytes()
			except OSError as error:
				raise HistoricalUnionFormatError(
					f"Could not read historical-union artifact {path}: {error}",
				) from error
			validate_historical_artifact(data, path)
			self._artifacts[cache_key] = data
		return self._artifacts[cache_key]

	def contains(
		self,
		language: Language | str,
		slot: Slot | str,
		key: str,
		value: str,
	) -> bool:
		"""Return whether a normalized key/value line occurs in its historical set."""

		language_record = get_language(language) if isinstance(language, str) else language
		slot_value = coerce_slot(slot)
		digest = historical_line_digest(key, value, slot_value)
		return _contains_digest(self._artifact(language_record, slot_value), digest)
