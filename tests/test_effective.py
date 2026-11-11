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

	# The personal root entry also hides the set's main "Madrid".
	rows = view.rows()
	assert [(row.word, row.slot, row.kind) for row in rows] == [
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


def test_personal_root_entry_hides_the_sets_main_entries_for_its_word() -> None:
	managed = _managed_set(
		{
			("enu", Slot.MAIN): (
				Entry("GUI", "gooey"),
				Entry("Gui", "ghee"),
				Entry("guide", "guide"),
			),
		},
	)
	view = EffectiveView("enu", managed, _overlay(("enu", Slot.ROOT, "gui", "gee you eye")))

	assert [(row.word, row.pronunciation, row.slot, row.kind) for row in view.rows()] == [
		("gui", "gee you eye", Slot.ROOT, RowKind.OVERRIDE),
		("guide", "guide", Slot.MAIN, RowKind.MANAGED),
	]
	assert [row.source for row in view.rows(show=ShowFilter.OVERRIDES)] == [
		"Personal — overrides Example Set",
	]


def test_removing_the_personal_root_entry_restores_the_sets_main_entries() -> None:
	managed = _managed_set({("enu", Slot.MAIN): (Entry("GUI", "gooey"),)})
	overlay = _overlay(("enu", Slot.ROOT, "gui", "gee you eye"))
	assert [row.word for row in EffectiveView("enu", managed, overlay).rows()] == ["gui"]

	overlay.remove_entry("enu", Slot.ROOT, "gui")

	assert [(row.word, row.slot, row.kind) for row in EffectiveView("enu", managed, overlay).rows()] == [
		("GUI", Slot.MAIN, RowKind.MANAGED),
	]


def test_personal_root_entry_overrides_the_sets_root_and_hides_its_main() -> None:
	managed = _managed_set(
		{
			("enu", Slot.MAIN): (Entry("Wii", "wee main"),),
			("enu", Slot.ROOT): (Entry("wii", "wee root"),),
		},
	)
	view = EffectiveView("enu", managed, _overlay(("enu", Slot.ROOT, "wii", "personal")))

	assert [(row.word, row.slot, row.kind) for row in view.rows()] == [
		("wii", Slot.ROOT, RowKind.OVERRIDE),
	]


def test_main_and_root_within_one_layer_are_both_listed() -> None:
	managed = _managed_set(
		{
			("enu", Slot.MAIN): (Entry("Sys", "managed main"),),
			("enu", Slot.ROOT): (Entry("sys", "managed root"),),
		},
	)
	view = EffectiveView(
		"enu",
		None,
		_overlay(
			("enu", Slot.MAIN, "Sys", "personal main"),
			("enu", Slot.ROOT, "sys", "personal root"),
		),
	)
	assert [(row.word, row.slot, row.kind) for row in view.rows()] == [
		("Sys", Slot.MAIN, RowKind.PERSONAL),
		("sys", Slot.ROOT, RowKind.PERSONAL),
	]

	managed_only = EffectiveView("enu", managed, PersonalOverlay())
	assert [(row.word, row.slot, row.kind) for row in managed_only.rows()] == [
		("Sys", Slot.MAIN, RowKind.MANAGED),
		("sys", Slot.ROOT, RowKind.MANAGED),
	]


def test_personal_main_override_stays_listed_beside_a_personal_root_entry() -> None:
	managed = _managed_set({("enu", Slot.MAIN): (Entry("Sys", "managed main"),)})
	view = EffectiveView(
		"enu",
		managed,
		_overlay(
			("enu", Slot.MAIN, "Sys", "personal main"),
			("enu", Slot.ROOT, "sys", "personal root"),
		),
	)

	assert [(row.word, row.pronunciation, row.slot, row.kind) for row in view.rows()] == [
		("Sys", "personal main", Slot.MAIN, RowKind.OVERRIDE),
		("sys", "personal root", Slot.ROOT, RowKind.OVERRIDE),
	]
