from __future__ import annotations

from pathlib import Path

import pytest

from ecidic.model import Entry, Slot
from ecidic.overlay import PersonalOverlay, load_personal_overlay, save_personal_overlay
from ecidic.parsing import DictionaryEncodingError
from ecidic.validation import EntryValidationError


def test_missing_overlay_directory_is_empty(tmp_path: Path) -> None:
	overlay, diagnostics = load_personal_overlay(tmp_path / "missing")

	assert overlay.entries == {}
	assert diagnostics == ()


def test_overlay_loads_languages_slots_and_case_insensitive_filenames(tmp_path: Path) -> None:
	_ = (tmp_path / "ENUMAIN.DIC").write_bytes(b"Word\tpronunciation\r\n")
	_ = (tmp_path / "deuRoot.Dic").write_bytes(b"Haus\thouse\n")

	overlay, diagnostics = load_personal_overlay(tmp_path)

	assert diagnostics == ()
	assert overlay.entries_for("enu", Slot.MAIN) == (Entry("Word", "pronunciation"),)
	assert overlay.entries_for("deu", Slot.ROOT) == (Entry("Haus", "house"),)


def test_corrupt_overlay_file_is_skipped_without_hiding_valid_files(tmp_path: Path) -> None:
	_ = (tmp_path / "enumain.dic").write_bytes(b"missing tab\n")
	_ = (tmp_path / "deumain.dic").write_bytes(b"Haus\thouse\n")

	overlay, diagnostics = load_personal_overlay(tmp_path)

	assert overlay.entries_for("enu", Slot.MAIN) == ()
	assert overlay.entries_for("deu", Slot.MAIN) == (Entry("Haus", "house"),)
	assert len(diagnostics) == 1
	assert diagnostics[0].path == tmp_path / "enumain.dic"


def test_set_and_get_entry_use_slot_identity() -> None:
	overlay = PersonalOverlay()
	first = Entry("Quinoa", "first")
	replacement = Entry("quinoa", "replacement")

	overlay.set_entry("ENU", Slot.ROOT, first)
	assert overlay.get_entry("enu", Slot.ROOT, "QUINOA") == first

	overlay.set_entry("enu", Slot.ROOT, replacement)

	assert len(overlay.entries) == 1
	assert overlay.get_entry("ENU", Slot.ROOT, "Quinoa") == replacement


def test_remove_entry_uses_identity_and_missing_entry_is_a_no_op() -> None:
	overlay = PersonalOverlay.from_entries(
		[("enu", Slot.ROOT, Entry("Quinoa", "keenwah"))],
	)

	overlay.remove_entry("ENU", Slot.ROOT, "QUINOA")
	overlay.remove_entry("enu", Slot.ROOT, "absent")

	assert overlay.entries == {}


def test_remove_language_only_removes_matching_language_and_returns_count() -> None:
	overlay = PersonalOverlay.from_entries(
		[
			("enu", Slot.MAIN, Entry("Word", "pronunciation")),
			("enu", Slot.ROOT, Entry("quinoa", "keenwah")),
			("deu", Slot.MAIN, Entry("Haus", "house")),
		],
	)

	assert overlay.count_for("ENU") == 2
	assert overlay.remove_language("ENU") == 2

	assert overlay.count_for("enu") == 0
	assert overlay.entries_for("deu", Slot.MAIN) == (Entry("Haus", "house"),)


def test_save_personal_overlay_round_trips_canonical_files(tmp_path: Path) -> None:
	overlay = PersonalOverlay.from_entries(
		[
			("enu", Slot.MAIN, Entry("café", "coffee")),
			("enu", Slot.ROOT, Entry("quinoa", "keenwah")),
		],
	)

	save_personal_overlay(overlay, tmp_path)
	reloaded, diagnostics = load_personal_overlay(tmp_path)

	assert diagnostics == ()
	assert reloaded.entries == overlay.entries
	assert sorted(path.name for path in tmp_path.iterdir()) == ["enumain.dic", "enuroot.dic"]
	assert (tmp_path / "enumain.dic").read_bytes() == b"caf\xe9\tcoffee\r\n"
	assert (tmp_path / "enuroot.dic").read_bytes() == b"quinoa\tkeenwah\r\n"


def test_save_personal_overlay_normalizes_root_keys_to_lowercase(tmp_path: Path) -> None:
	overlay = PersonalOverlay.from_entries(
		[("enu", Slot.ROOT, Entry("Quinoa", "keenwah"))],
	)

	save_personal_overlay(overlay, tmp_path)
	reloaded, diagnostics = load_personal_overlay(tmp_path)

	assert diagnostics == ()
	assert (tmp_path / "enuroot.dic").read_bytes() == b"quinoa\tkeenwah\r\n"
	assert reloaded.get_entry("enu", Slot.ROOT, "QUINOA") == Entry("quinoa", "keenwah")


def test_save_personal_overlay_deletes_empty_slot_file(tmp_path: Path) -> None:
	path = tmp_path / "enumain.dic"
	_ = path.write_bytes(b"Word\tpronunciation\r\n")

	save_personal_overlay(PersonalOverlay(), tmp_path)

	assert not path.exists()


def test_save_personal_overlay_replaces_differently_cased_filename(tmp_path: Path) -> None:
	old_path = tmp_path / "ENUmain.dic"
	_ = old_path.write_bytes(b"Old\tvalue\r\n")
	overlay = PersonalOverlay.from_entries(
		[("enu", Slot.MAIN, Entry("New", "value"))],
	)

	save_personal_overlay(overlay, tmp_path)

	matches = [path for path in tmp_path.iterdir() if path.name.casefold() == "enumain.dic"]
	assert len(matches) == 1
	assert matches[0].name == "enumain.dic"
	assert matches[0].read_bytes() == b"New\tvalue\r\n"


def test_save_personal_overlay_rejects_invalid_entry(tmp_path: Path) -> None:
	overlay = PersonalOverlay.from_entries(
		[("enu", Slot.MAIN, Entry("two words", "value"))],
	)

	with pytest.raises(EntryValidationError):
		save_personal_overlay(overlay, tmp_path)


def test_save_personal_overlay_rejects_unencodable_entry(tmp_path: Path) -> None:
	overlay = PersonalOverlay.from_entries(
		[("enu", Slot.MAIN, Entry("word", "漢"))],
	)

	with pytest.raises(DictionaryEncodingError):
		save_personal_overlay(overlay, tmp_path)
