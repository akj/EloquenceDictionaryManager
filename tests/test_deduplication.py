from __future__ import annotations

from ecidic import Entry, Slot, deduplicate_entries, key_identity, merge_entries


def test_root_key_identity_and_deduplication_are_case_insensitive() -> None:
	entries = [
		Entry("Figure", "old"),
		Entry("other", "unchanged"),
		Entry("figure", "new"),
	]

	assert key_identity("Straße", Slot.ROOT) == key_identity("STRASSE", Slot.ROOT)
	assert deduplicate_entries(entries, Slot.ROOT) == (
		Entry("other", "unchanged"),
		Entry("figure", "new"),
	)


def test_main_keys_compare_exactly() -> None:
	entries = [Entry("Word", "capital"), Entry("word", "lower"), Entry("Word", "latest")]

	assert deduplicate_entries(entries, Slot.MAIN) == (
		Entry("word", "lower"),
		Entry("Word", "latest"),
	)


def test_abbreviation_keys_compare_exactly() -> None:
	entries = [Entry("Dr", "doctor"), Entry("dr", "drive"), Entry("Dr", "latest")]

	assert deduplicate_entries(entries, Slot.ABBREVIATION) == (
		Entry("dr", "drive"),
		Entry("Dr", "latest"),
	)


def test_personal_overlay_wins_when_entries_are_merged() -> None:
	managed = [Entry("FIGURE", "managed"), Entry("other", "managed other")]
	personal = [Entry("figure", "personal")]

	assert merge_entries(managed, personal, Slot.ROOT) == (
		Entry("other", "managed other"),
		Entry("figure", "personal"),
	)
