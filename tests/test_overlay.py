from __future__ import annotations

from pathlib import Path

from ecidic.model import Entry, Slot
from ecidic.overlay import load_personal_overlay


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
