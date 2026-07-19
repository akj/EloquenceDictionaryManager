from __future__ import annotations

from pathlib import Path

from ecidic.historicalunion import HistoricalUnion
from ecidic.migration import (
	MigrationCandidate,
	MigrationCandidateStatus,
	apply_migration_candidates,
	classify_migration_candidates,
	discover_migration_candidates,
	find_eloquence_backup_directories,
	scan_migration_directory,
)
from ecidic.model import Entry, Slot
from ecidic.overlay import PersonalOverlay


class _HistoricalUnionStub(HistoricalUnion):
	def __init__(self, known: set[tuple[str, Slot, str, str]] | None = None):
		self.known = known or set()

	def contains(
		self,
		language: str,
		slot: Slot | str,
		key: str,
		value: str,
	) -> bool:
		return (language, Slot(slot), key, value) in self.known


def _candidate(
	word: str,
	pronunciation: str,
	*,
	language: str = "enu",
	slot: Slot = Slot.MAIN,
) -> MigrationCandidate:
	return MigrationCandidate(language, slot, Entry(word, pronunciation), Path("legacy.dic"))


def test_scanner_decodes_cp1252_and_tolerates_crlf_and_lf(tmp_path: Path) -> None:
	_ = (tmp_path / "enumain.dic").write_bytes(
		b"caf\xe9\tcr\xe8me br\xfbl\xe9e\r\njalape\xf1o\tpepper\n",
	)

	scan = scan_migration_directory(tmp_path)

	assert scan.diagnostics == ()
	assert scan.decoded_files == (tmp_path / "enumain.dic",)
	assert [candidate.entry for candidate in scan.candidates] == [
		Entry("café", "crème brûlée"),
		Entry("jalapeño", "pepper"),
	]


def test_scanner_accepts_both_observed_filename_case_conventions(tmp_path: Path) -> None:
	_ = (tmp_path / "ENUmain.dic").write_bytes(b"first\tone\r\n")
	_ = (tmp_path / "deuRoot.DIC").write_bytes(b"Haus\thouse\n")

	scan = scan_migration_directory(tmp_path)

	assert [(item.language, item.slot, item.entry) for item in scan.candidates] == [
		("enu", Slot.MAIN, Entry("first", "one")),
		("deu", Slot.ROOT, Entry("Haus", "house")),
	]


def test_scanner_deduplicates_upstream_keys_last_occurrence_wins(tmp_path: Path) -> None:
	_ = (tmp_path / "enuroot.dic").write_bytes(
		b"Mixed\tfirst\r\nother\tkept\r\nMIXED\tlast\r\n",
	)

	scan = scan_migration_directory(tmp_path)

	assert [candidate.entry for candidate in scan.candidates] == [
		Entry("other", "kept"),
		Entry("MIXED", "last"),
	]


def test_scanner_preserves_candidate_values_before_import(tmp_path: Path) -> None:
	_ = (tmp_path / "enumain.dic").write_bytes(b"Word\t Value With CASE  \r\n")
	_ = (tmp_path / "enuroot.dic").write_bytes(b"MixedCase\tRootValue\r\n")

	scan = scan_migration_directory(tmp_path)

	assert [candidate.entry for candidate in scan.candidates] == [
		Entry("Word", " Value With CASE  "),
		Entry("MixedCase", "RootValue"),
	]


def test_scanner_ignores_unsupported_voice_codes_and_unrecognized_files(tmp_path: Path) -> None:
	_ = (tmp_path / "jpnmain.dic").write_bytes(b"ignored\tentry\r\n")
	_ = (tmp_path / "notes.txt").write_text("ignored")
	_ = (tmp_path / "finabbr.dic").write_bytes(b"Dr.\tdoctor\r\n")

	scan = scan_migration_directory(tmp_path)

	assert [(item.language, item.slot) for item in scan.candidates] == [("fin", Slot.ABBREVIATION)]
	assert scan.diagnostics == ()


def test_invalid_files_and_directories_are_skipped_with_diagnostics(tmp_path: Path) -> None:
	missing = scan_migration_directory(tmp_path / "missing")
	_ = (tmp_path / "enumain.dic").write_bytes(b"missing separator\r\n")
	invalid = scan_migration_directory(tmp_path)

	assert missing.candidates == ()
	assert len(missing.diagnostics) == 1
	assert invalid.candidates == ()
	assert invalid.diagnostics[0].path == tmp_path / "enumain.dic"


def test_backup_discovery_is_case_insensitive_and_globally_backup_first(tmp_path: Path) -> None:
	first_provider = tmp_path / "first"
	second_provider = tmp_path / "second"
	first_live = first_provider / "SynthDrivers" / "ELOQUENCE"
	second_backup = second_provider / "synthDrivers" / "Eloquence-Dic-Backup"
	first_live.mkdir(parents=True)
	second_backup.mkdir(parents=True)

	assert find_eloquence_backup_directories((first_provider, second_provider)) == (
		second_backup,
		first_live,
	)


def test_auto_scan_short_circuits_after_first_directory_with_candidates(tmp_path: Path) -> None:
	provider = tmp_path / "addon"
	backup = provider / "synthDrivers" / "eloquence-dic-backup"
	live = provider / "synthDrivers" / "eloquence"
	backup.mkdir(parents=True)
	live.mkdir()
	_ = (backup / "enumain.dic").write_bytes(b"backup\tchosen\r\n")
	_ = (live / "enumain.dic").write_bytes(b"live\tnot chosen\r\n")

	discovery = discover_migration_candidates((provider,))

	assert discovery.scan is not None
	assert discovery.scan.directory == backup
	assert [item.entry for item in discovery.scan.candidates] == [Entry("backup", "chosen")]


def test_auto_scan_falls_through_empty_or_unreadable_backup_to_live_directory(tmp_path: Path) -> None:
	provider = tmp_path / "addon"
	backup = provider / "synthDrivers" / "eloquence-dic-backup"
	live = provider / "synthDrivers" / "eloquence"
	backup.mkdir(parents=True)
	live.mkdir()
	_ = (backup / "enumain.dic").write_bytes(b"invalid\r\n")
	_ = (live / "enumain.dic").write_bytes(b"live\tchosen\r\n")

	discovery = discover_migration_candidates((provider,))

	assert discovery.scan is not None
	assert discovery.scan.directory == live
	assert len(discovery.diagnostics) == 1


def test_auto_scan_does_not_fall_through_a_decodable_empty_dictionary(tmp_path: Path) -> None:
	provider = tmp_path / "addon"
	backup = provider / "synthDrivers" / "eloquence-dic-backup"
	live = provider / "synthDrivers" / "eloquence"
	backup.mkdir(parents=True)
	live.mkdir()
	_ = (backup / "enumain.dic").write_bytes(b"")
	_ = (live / "enumain.dic").write_bytes(b"live\tnot scanned\r\n")

	discovery = discover_migration_candidates((provider,))

	assert discovery.scan is not None
	assert discovery.scan.directory == backup
	assert discovery.scan.candidates == ()


def test_classification_covers_remaining_statuses_and_omits_personal_and_upstream_entries() -> None:
	candidates = (
		_candidate("hand", "custom"),
		_candidate("two words", "invalid"),
		_candidate("collision", "legacy"),
		_candidate("upstream", "known"),
		_candidate("identical", "same"),
	)
	overlay = PersonalOverlay.from_entries(
		[
			("enu", Slot.MAIN, Entry("collision", "personal")),
			("enu", Slot.MAIN, Entry("identical", "same")),
		],
	)
	historical = _HistoricalUnionStub({("enu", Slot.MAIN, "upstream", "known")})

	rows = classify_migration_candidates(candidates, overlay, historical)

	assert [row.word for row in rows] == ["hand", "two words", "collision"]
	assert [row.status for row in rows] == [
		MigrationCandidateStatus.LIKELY_HAND_EDIT,
		MigrationCandidateStatus.INVALID,
		MigrationCandidateStatus.DIFFERS_FROM_PERSONAL,
	]
	assert [(row.checked_by_default, row.checkable) for row in rows] == [
		(True, True),
		(False, False),
		(False, True),
	]
	assert (
		rows[1].status_text == "The word cannot contain spaces. Dictionary entries match one word at a time."
	)
	assert rows[2].status_text == "Differs from your current entry for this word"


def test_historical_union_match_is_omitted_from_candidate_rows() -> None:
	candidate = _candidate("upstream", "known")
	historical = _HistoricalUnionStub({("enu", Slot.MAIN, "upstream", "known")})

	rows = classify_migration_candidates((candidate,), PersonalOverlay(), historical)

	assert rows == ()


def test_historical_union_match_wins_over_personal_collision() -> None:
	candidate = _candidate("upstream", "known")
	overlay = PersonalOverlay.from_entries(
		[("enu", Slot.MAIN, Entry("upstream", "personal"))],
	)
	historical = _HistoricalUnionStub({("enu", Slot.MAIN, "upstream", "known")})

	rows = classify_migration_candidates((candidate,), overlay, historical)

	assert rows == ()


def test_invalid_historical_union_match_is_omitted() -> None:
	candidate = _candidate("two words", "known")
	historical = _HistoricalUnionStub({("enu", Slot.MAIN, "two words", "known")})

	rows = classify_migration_candidates((candidate,), PersonalOverlay(), historical)

	assert rows == ()


def test_root_identical_detection_uses_identity_without_normalizing_candidate_display() -> None:
	candidate = _candidate("MixedCase", "same", slot=Slot.ROOT)
	overlay = PersonalOverlay.from_entries(
		[("enu", Slot.ROOT, Entry("mixedcase", "same"))],
	)

	rows = classify_migration_candidates((candidate,), overlay, _HistoricalUnionStub())

	assert rows == ()


def test_import_normalizes_only_when_writing_and_replaces_checked_collision() -> None:
	overlay = PersonalOverlay.from_entries(
		[("enu", Slot.ROOT, Entry("collision", "personal"))],
	)
	candidates = (
		_candidate("MixedCase", "RootValue", slot=Slot.ROOT),
		_candidate("COLLISION", "legacy", slot=Slot.ROOT),
	)
	rows = classify_migration_candidates(candidates, overlay, _HistoricalUnionStub())

	assert rows[0].word == "MixedCase"
	assert rows[1].status is MigrationCandidateStatus.DIFFERS_FROM_PERSONAL
	assert apply_migration_candidates(overlay, rows) == 2
	assert overlay.get_entry("enu", Slot.ROOT, "mixedcase") == Entry("mixedcase", "RootValue")
	assert overlay.get_entry("enu", Slot.ROOT, "collision") == Entry("collision", "legacy")


def test_reclassification_after_import_has_no_new_default_checked_rows() -> None:
	candidates = (
		_candidate("hand", "custom"),
		_candidate("upstream", "known"),
	)
	overlay = PersonalOverlay()
	historical = _HistoricalUnionStub({("enu", Slot.MAIN, "upstream", "known")})
	first_rows = classify_migration_candidates(candidates, overlay, historical)
	selected = tuple(row for row in first_rows if row.checked_by_default)

	assert apply_migration_candidates(overlay, selected) == 1
	second_rows = classify_migration_candidates(candidates, overlay, historical)

	assert second_rows == ()
	assert not any(row.checked_by_default for row in second_rows)
