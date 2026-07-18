"""Core value objects for ECI dictionary files."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Slot(str, Enum):
	"""A supported Western ECI dictionary volume."""

	MAIN = "main"
	ROOT = "root"
	ABBREVIATION = "abbr"


@dataclass(frozen=True, slots=True)
class Entry:
	"""One ECI dictionary key and translation value."""

	key: str
	value: str


def coerce_slot(slot: Slot | str) -> Slot:
	"""Return *slot* as a :class:`Slot`, accepting its on-disk suffix."""

	if isinstance(slot, Slot):
		return slot
	return Slot(slot.lower())
