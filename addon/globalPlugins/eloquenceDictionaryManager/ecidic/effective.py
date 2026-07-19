"""Cached effective-entry view for a Managed Dictionary Set and Personal Dictionary Overlay."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .model import Slot
from .overlay import PersonalOverlay
from .parsing import deduplicate_entries, key_identity
from .sets import ManagedSet

try:
	import addonHandler

	addonHandler.initTranslation()
except (ImportError, ModuleNotFoundError):

	def _(text: str) -> str:
		return text


class RowKind(str, Enum):
	"""Provenance category for one effective-entry row."""

	MANAGED = "managed"
	PERSONAL = "personal"
	OVERRIDE = "override"


class ShowFilter(str, Enum):
	"""Supported subsets of the effective-entry list."""

	ALL = "all"
	PERSONAL = "personal"
	OVERRIDES = "overrides"
	MANAGED = "managed"


@dataclass(frozen=True, slots=True)
class EffectiveRow:
	"""One display row in the merged effective-entry list."""

	word: str
	pronunciation: str
	slot: Slot
	kind: RowKind
	managed_name: str | None = None
	managed_version: str | None = None

	@property
	def source(self) -> str:
		"""Return the localized Source column text."""

		if self.kind is RowKind.MANAGED:
			# Translators: Source column for an entry from a Managed Dictionary Set. {name} is the set name and {version} is its release version.
			return _("Managed — {name} ({version})").format(
				name=self.managed_name,
				version=self.managed_version,
			)
		if self.kind is RowKind.OVERRIDE:
			# Translators: Source column for a personal entry that overrides a Managed Dictionary Set entry. {name} is the set name.
			return _("Personal — overrides {name}").format(name=self.managed_name)
		# Translators: Source column for an entry that exists only in the Personal Dictionary Overlay.
		return _("Personal")


_SLOT_ORDER = {
	Slot.MAIN: 0,
	Slot.ROOT: 1,
	Slot.ABBREVIATION: 2,
}


class EffectiveView:
	"""A merged entry list built once and cheaply refiltered for GUI changes."""

	def __init__(
		self,
		language: str,
		managed_set: ManagedSet | None,
		overlay: PersonalOverlay,
	):
		super().__init__()
		self.language = language.casefold()
		self.managed_set = managed_set
		self._merged_rows = self._build_rows(overlay)

	def _build_rows(self, overlay: PersonalOverlay) -> tuple[EffectiveRow, ...]:
		merged: dict[tuple[Slot, str], EffectiveRow] = {}
		if self.managed_set is not None:
			for slot in Slot:
				entries = deduplicate_entries(self.managed_set.entries_for(self.language, slot), slot)
				for entry in entries:
					merged[(slot, key_identity(entry.key, slot))] = EffectiveRow(
						word=entry.key,
						pronunciation=entry.value,
						slot=slot,
						kind=RowKind.MANAGED,
						managed_name=self.managed_set.name,
						managed_version=self.managed_set.source_version,
					)
		for slot in Slot:
			for entry in deduplicate_entries(overlay.entries_for(self.language, slot), slot):
				identity = (slot, key_identity(entry.key, slot))
				managed_row = merged.get(identity)
				if managed_row is None:
					merged[identity] = EffectiveRow(
						word=entry.key,
						pronunciation=entry.value,
						slot=slot,
						kind=RowKind.PERSONAL,
					)
				else:
					merged[identity] = EffectiveRow(
						word=entry.key,
						pronunciation=entry.value,
						slot=slot,
						kind=RowKind.OVERRIDE,
						managed_name=managed_row.managed_name,
						managed_version=managed_row.managed_version,
					)
		return tuple(merged.values())

	def rows(
		self,
		filter_text: str = "",
		show: ShowFilter = ShowFilter.ALL,
	) -> tuple[EffectiveRow, ...]:
		"""Return rows using the prototype's filter and sort semantics."""

		filter_value = filter_text.strip().casefold()
		rows = self._merged_rows
		if filter_value:
			rows = tuple(
				row
				for row in rows
				if row.word.casefold().startswith(filter_value)
				or filter_value in row.pronunciation.casefold()
			)
		if show is ShowFilter.PERSONAL:
			rows = tuple(row for row in rows if row.kind in (RowKind.PERSONAL, RowKind.OVERRIDE))
		elif show is ShowFilter.OVERRIDES:
			rows = tuple(row for row in rows if row.kind is RowKind.OVERRIDE)
		elif show is ShowFilter.MANAGED:
			rows = tuple(row for row in rows if row.kind is RowKind.MANAGED)
		return tuple(
			sorted(
				rows,
				key=lambda row: (
					row.word.casefold() != filter_value if filter_value else False,
					row.word.casefold(),
					_SLOT_ORDER[row.slot],
				),
			),
		)
