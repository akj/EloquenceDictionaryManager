from __future__ import annotations

from collections.abc import Mapping

from ecidic.effective import EffectiveView, RowKind, ShowFilter
from ecidic.model import Entry, Slot
from ecidic.overlay import PersonalOverlay
from ecidic.sets import ManagedSet


def _managed_set(
	entries: Mapping[tuple[str, Slot], tuple[Entry, ...]],
) -> ManagedSet:
	return ManagedSet(
		id="github.example.set",
		name="Example Set",
		source_url="https://example.com/source",
		source_version="v2",
		source_revision="0123456789abcdef0123456789abcdef01234567",
		attribution="Example contributors",
		license="CC0-1.0",
		license_url="https://example.com/license",
		_entries=entries,
	)


def _overlay(*items: tuple[str, Slot, str, str]) -> PersonalOverlay:
	return PersonalOverlay.from_entries(
		(language, slot, Entry(word, pronunciation)) for language, slot, word, pronunciation in items
	)


def test_personal_override_collapses_to_one_row_and_reports_source() -> None:
	managed = _managed_set({("enu", Slot.MAIN): (Entry("word", "managed"),)})
	view = EffectiveView("enu", managed, _overlay(("enu", Slot.MAIN, "word", "personal")))

	rows = view.rows()
	assert len(rows) == 1
	row = rows[0]
	assert (row.word, row.pronunciation, row.kind) == ("word", "personal", RowKind.OVERRIDE)
	assert row.source == "Personal — overrides Example Set"


def test_root_keys_override_case_insensitively_but_main_keys_are_exact() -> None:
	managed = _managed_set(
		{
			("enu", Slot.ROOT): (Entry("Madrid", "managed root"),),
			("enu", Slot.MAIN): (Entry("Madrid", "managed main"),),
		},
	)
	view = EffectiveView(
		"enu",
		managed,
		_overlay(
			("enu", Slot.ROOT, "madrid", "personal root"),
			("enu", Slot.MAIN, "madrid", "personal main"),
		),
	)

	rows = view.rows()
	assert [(row.word, row.slot, row.kind) for row in rows] == [
		("Madrid", Slot.MAIN, RowKind.MANAGED),
		("madrid", Slot.MAIN, RowKind.PERSONAL),
		("madrid", Slot.ROOT, RowKind.OVERRIDE),
	]


def test_source_labels_cover_managed_personal_and_override() -> None:
	managed = _managed_set(
		{
			("enu", Slot.MAIN): (Entry("managed", "one"), Entry("override", "two")),
		},
	)
	view = EffectiveView(
		"enu",
		managed,
		_overlay(
			("enu", Slot.MAIN, "personal", "three"),
			("enu", Slot.MAIN, "override", "four"),
		),
	)

	assert {row.kind: row.source for row in view.rows()} == {
		RowKind.MANAGED: "Managed — Example Set (v2)",
		RowKind.PERSONAL: "Personal",
		RowKind.OVERRIDE: "Personal — overrides Example Set",
	}


def test_word_prefix_and_pronunciation_substring_filters() -> None:
	managed = _managed_set(
		{
			("enu", Slot.MAIN): (
				Entry("alpha", "first sound"),
				Entry("beta", "contains Needle here"),
				Entry("gamma", "third sound"),
			),
		},
	)
	view = EffectiveView("enu", managed, PersonalOverlay())

	assert [row.word for row in view.rows("ALP")] == ["alpha"]
	assert [row.word for row in view.rows("needle")] == ["beta"]


def test_exact_word_match_sorts_before_other_prefix_matches() -> None:
	managed = _managed_set(
		{
			("enu", Slot.MAIN): (
				Entry("alphabet", "one"),
				Entry("alpha", "two"),
				Entry("alphanumeric", "three"),
			),
		},
	)
	view = EffectiveView("enu", managed, PersonalOverlay())

	assert [row.word for row in view.rows("alpha")] == ["alpha", "alphabet", "alphanumeric"]


def test_show_filters_return_the_approved_subsets() -> None:
	managed = _managed_set(
		{
			("enu", Slot.MAIN): (Entry("managed", "one"), Entry("override", "two")),
		},
	)
	view = EffectiveView(
		"enu",
		managed,
		_overlay(
			("enu", Slot.MAIN, "personal", "three"),
			("enu", Slot.MAIN, "override", "four"),
		),
	)

	assert {row.kind for row in view.rows(show=ShowFilter.ALL)} == set(RowKind)
	assert {row.kind for row in view.rows(show=ShowFilter.PERSONAL)} == {
		RowKind.PERSONAL,
		RowKind.OVERRIDE,
	}
	assert {row.kind for row in view.rows(show=ShowFilter.OVERRIDES)} == {RowKind.OVERRIDE}
	assert {row.kind for row in view.rows(show=ShowFilter.MANAGED)} == {RowKind.MANAGED}


def test_sort_uses_word_casefold_then_main_root_abbreviation_slot_order() -> None:
	managed = _managed_set(
		{
			("enu", Slot.ABBREVIATION): (Entry("Same", "abbr"),),
			("enu", Slot.ROOT): (Entry("same", "root"),),
			("enu", Slot.MAIN): (Entry("same", "main"), Entry("Zulu", "last")),
		},
	)
	view = EffectiveView("enu", managed, PersonalOverlay())

	assert [(row.word, row.slot) for row in view.rows()] == [
		("same", Slot.MAIN),
		("same", Slot.ROOT),
		("Same", Slot.ABBREVIATION),
		("Zulu", Slot.MAIN),
	]


def test_managed_internal_duplicate_keys_collapse_last_wins() -> None:
	managed = _managed_set(
		{
			("enu", Slot.MAIN): (Entry("duplicate", "first"), Entry("duplicate", "last")),
		},
	)

	rows = EffectiveView("enu", managed, PersonalOverlay()).rows()

	assert [(row.word, row.pronunciation) for row in rows] == [("duplicate", "last")]
