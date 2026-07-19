from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from vendored_sets import VendoringError, load_lock, process_upstream_tree, verify_tree, write_vendored_sets


SET_ID = "github.example.test-dictionaries"


def _write_lock(path: Path, *, license_value: str = "CC0-1.0") -> None:
	_ = path.write_text(
		f"""[set {SET_ID}]
github_repository = example/test-dictionaries
name = TestDictionaries
source_url = https://example.com/test-dictionaries
source_version = v1.0
source_revision = 0123456789abcdef0123456789abcdef01234567
attribution = Maintained by Test Contributors.
license = {license_value}
license_url = https://example.com/test-dictionaries/LICENSE.md
license_file = LICENSE.md

[files {SET_ID}]
""",
		encoding="utf-8",
		newline="\n",
	)


def _write_upstream_tree(path: Path) -> dict[str, bytes]:
	contents = {
		"ENURoot.dic": b"talk\ttalk\r\n",
		"ENUmain.dic": b"hello\thello\r\n",
		"DEUabbr.dic": b"Dr.\tdoktor\r\n",
	}
	path.mkdir()
	for name, data in contents.items():
		_ = (path / name).write_bytes(data)
	_ = (path / "README.md").write_text("Not vendored.\n", encoding="utf-8")
	_ = (path / "LICENSE.md").write_text("CC0 1.0 Universal\n", encoding="utf-8")
	return contents


def test_upstream_tree_can_be_vendored_and_verified_offline(tmp_path: Path) -> None:
	repo_root = tmp_path / "repo"
	repo_root.mkdir()
	lock_path = repo_root / "dictionarySources.lock.ini"
	_write_lock(lock_path)
	upstream_root = tmp_path / "upstream"
	original = _write_upstream_tree(upstream_root)
	lock = load_lock(lock_path)
	set_config = lock.sets[SET_ID]

	files = process_upstream_tree(upstream_root, set_config)
	write_vendored_sets(repo_root, lock_path, lock, {SET_ID: files})

	set_directory = repo_root / "addon" / "dictionaries" / "sets" / SET_ID
	assert {path.name for path in set_directory.iterdir()} == {
		"set.ini",
		"enuroot.dic",
		"enumain.dic",
		"deuabbr.dic",
	}
	assert (set_directory / "enuroot.dic").read_bytes() == original["ENURoot.dic"]
	assert (set_directory / "enumain.dic").read_bytes() == original["ENUmain.dic"]
	assert (set_directory / "deuabbr.dic").read_bytes() == original["DEUabbr.dic"]
	assert (
		(set_directory / "set.ini").read_text(encoding="utf-8")
		== f"""[set]
id = {SET_ID}
name = TestDictionaries
source_url = https://example.com/test-dictionaries
source_version = v1.0
source_revision = 0123456789abcdef0123456789abcdef01234567
attribution = Maintained by Test Contributors.
license = CC0-1.0
license_url = https://example.com/test-dictionaries/LICENSE.md
"""
	)
	assert (repo_root / "addon" / "dictionaries" / "contract.ini").read_text(
		encoding="utf-8",
	) == "[contract]\nformat = eci-dictionary-sets\nversion = 1\n"
	lock_text = lock_path.read_text(encoding="utf-8")
	for name, source_name in (
		("deuabbr.dic", "DEUabbr.dic"),
		("enumain.dic", "ENUmain.dic"),
		("enuroot.dic", "ENURoot.dic"),
	):
		assert f"{name} = {hashlib.sha256(original[source_name]).hexdigest()}" in lock_text

	assert verify_tree(repo_root, load_lock(lock_path)) == []


def _build_vendored_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
	repo_root = tmp_path / "repo"
	repo_root.mkdir()
	lock_path = repo_root / "dictionarySources.lock.ini"
	_write_lock(lock_path)
	upstream_root = tmp_path / "upstream"
	_ = _write_upstream_tree(upstream_root)
	lock = load_lock(lock_path)
	files = process_upstream_tree(upstream_root, lock.sets[SET_ID])
	write_vendored_sets(repo_root, lock_path, lock, {SET_ID: files})
	return repo_root, lock_path, upstream_root


def test_refresh_rejects_a_missing_license_file(tmp_path: Path) -> None:
	lock_path = tmp_path / "dictionarySources.lock.ini"
	_write_lock(lock_path)
	upstream_root = tmp_path / "upstream"
	_ = _write_upstream_tree(upstream_root)
	(upstream_root / "LICENSE.md").unlink()

	with pytest.raises(VendoringError, match="missing license file"):
		_ = process_upstream_tree(upstream_root, load_lock(lock_path).sets[SET_ID])


def test_refresh_rejects_a_license_without_the_cc0_marker(tmp_path: Path) -> None:
	lock_path = tmp_path / "dictionarySources.lock.ini"
	_write_lock(lock_path)
	upstream_root = tmp_path / "upstream"
	_ = _write_upstream_tree(upstream_root)
	_ = (upstream_root / "LICENSE.md").write_text("A different license.\n", encoding="utf-8")

	with pytest.raises(VendoringError, match="required CC0 marker"):
		_ = process_upstream_tree(upstream_root, load_lock(lock_path).sets[SET_ID])


def test_refresh_rejects_an_unsupported_license_value(tmp_path: Path) -> None:
	lock_path = tmp_path / "dictionarySources.lock.ini"
	_write_lock(lock_path, license_value="CC-BY-4.0")
	upstream_root = tmp_path / "upstream"
	_ = _write_upstream_tree(upstream_root)

	with pytest.raises(VendoringError, match="unsupported license"):
		_ = process_upstream_tree(upstream_root, load_lock(lock_path).sets[SET_ID])


def test_refresh_rejects_an_unsupported_voice_code(tmp_path: Path) -> None:
	lock_path = tmp_path / "dictionarySources.lock.ini"
	_write_lock(lock_path)
	upstream_root = tmp_path / "upstream"
	_ = _write_upstream_tree(upstream_root)
	_ = (upstream_root / "chsmain.dic").write_bytes(b"word\tword\r\n")

	with pytest.raises(VendoringError, match="Unsupported upstream dictionary filename"):
		_ = process_upstream_tree(upstream_root, load_lock(lock_path).sets[SET_ID])


def test_refresh_rejects_names_that_collide_after_canonicalization(tmp_path: Path) -> None:
	lock_path = tmp_path / "dictionarySources.lock.ini"
	_write_lock(lock_path)
	upstream_root = tmp_path / "upstream"
	_ = _write_upstream_tree(upstream_root)
	_ = (upstream_root / "enumain.DIC").write_bytes(b"other\tother\r\n")
	if len([path for path in upstream_root.iterdir() if path.name.casefold() == "enumain.dic"]) < 2:
		pytest.skip("The test filesystem is case-insensitive")

	with pytest.raises(VendoringError, match="maps to canonical filename"):
		_ = process_upstream_tree(upstream_root, load_lock(lock_path).sets[SET_ID])


def test_refresh_rejects_undecodable_dictionary_bytes(tmp_path: Path) -> None:
	lock_path = tmp_path / "dictionarySources.lock.ini"
	_write_lock(lock_path)
	upstream_root = tmp_path / "upstream"
	_ = _write_upstream_tree(upstream_root)
	_ = (upstream_root / "ENUmain.dic").write_bytes(b"word\t\x81\r\n")

	with pytest.raises(VendoringError, match="Dictionary 'ENUmain.dic' is invalid"):
		_ = process_upstream_tree(upstream_root, load_lock(lock_path).sets[SET_ID])


def test_refresh_vendors_soft_invalid_lines_verbatim_with_a_warning(tmp_path: Path) -> None:
	lock_path = tmp_path / "dictionarySources.lock.ini"
	_write_lock(lock_path)
	upstream_root = tmp_path / "upstream"
	_ = _write_upstream_tree(upstream_root)
	soft_invalid = (
		# An entry the editor's abbreviation rules reject (hyphen in the key).
		b"Dipl.-Ing.\tDiplomingenieur\r\n"
		# Two entries accidentally joined on one line, as shipped by upstream.
		+ b"ok\tokay\tok\tokay\r\n"
		# A blank line.
		+ b"\r\n"
		+ b"Dr.\tdoktor\r\n"
	)
	_ = (upstream_root / "DEUabbr.dic").write_bytes(soft_invalid)
	warnings: list[str] = []

	files = process_upstream_tree(upstream_root, load_lock(lock_path).sets[SET_ID], warnings)

	assert files["deuabbr.dic"] == soft_invalid
	assert len(warnings) == 1
	assert "DEUabbr.dic: 3 line(s) violate" in warnings[0]
	assert "'Dipl.-Ing.'" in warnings[0]
	assert "exactly one tab" in warnings[0]


def test_refresh_rejects_an_upstream_tree_without_dictionaries(tmp_path: Path) -> None:
	lock_path = tmp_path / "dictionarySources.lock.ini"
	_write_lock(lock_path)
	upstream_root = tmp_path / "upstream"
	_ = _write_upstream_tree(upstream_root)
	for path in upstream_root.iterdir():
		if path.suffix.lower() == ".dic":
			path.unlink()

	with pytest.raises(VendoringError, match="contains no top-level .dic files"):
		_ = process_upstream_tree(upstream_root, load_lock(lock_path).sets[SET_ID])


def test_verify_reports_tampered_dictionary_bytes(tmp_path: Path) -> None:
	repo_root, lock_path, _upstream_root = _build_vendored_tree(tmp_path)
	set_directory = repo_root / "addon" / "dictionaries" / "sets" / SET_ID
	_ = (set_directory / "enumain.dic").write_bytes(b"changed\tchanged\r\n")

	problems = verify_tree(repo_root, load_lock(lock_path))

	assert any("enumain.dic sha256 does not match" in problem for problem in problems)


def test_verify_reports_a_missing_listed_file(tmp_path: Path) -> None:
	repo_root, lock_path, _upstream_root = _build_vendored_tree(tmp_path)
	set_directory = repo_root / "addon" / "dictionaries" / "sets" / SET_ID
	(set_directory / "enumain.dic").unlink()

	problems = verify_tree(repo_root, load_lock(lock_path))

	assert any("enumain.dic is missing from the set directory" in problem for problem in problems)
	assert any("enumain.dic is listed in the lock but missing" in problem for problem in problems)


def test_verify_reports_an_extra_unlisted_file(tmp_path: Path) -> None:
	repo_root, lock_path, _upstream_root = _build_vendored_tree(tmp_path)
	set_directory = repo_root / "addon" / "dictionaries" / "sets" / SET_ID
	_ = (set_directory / "notes.txt").write_text("unexpected\n", encoding="utf-8")

	problems = verify_tree(repo_root, load_lock(lock_path))

	assert any("notes.txt is not listed in the source lock" in problem for problem in problems)


def test_verify_reports_a_noncanonical_listed_filename(tmp_path: Path) -> None:
	repo_root, lock_path, _upstream_root = _build_vendored_tree(tmp_path)
	set_directory = repo_root / "addon" / "dictionaries" / "sets" / SET_ID
	_ = (set_directory / "enumain.dic").rename(set_directory / "ENUmain.dic")
	lock_text = lock_path.read_text(encoding="utf-8").replace("enumain.dic = ", "ENUmain.dic = ")
	_ = lock_path.write_text(lock_text, encoding="utf-8", newline="\n")

	problems = verify_tree(repo_root, load_lock(lock_path))

	assert any("ENUmain.dic is not a canonical lowercase" in problem for problem in problems)


def test_verify_reports_set_metadata_that_diverges_from_the_lock(tmp_path: Path) -> None:
	repo_root, lock_path, _upstream_root = _build_vendored_tree(tmp_path)
	set_ini = repo_root / "addon" / "dictionaries" / "sets" / SET_ID / "set.ini"
	_ = set_ini.write_text(
		set_ini.read_text(encoding="utf-8").replace("name = TestDictionaries", "name = Edited"),
		encoding="utf-8",
		newline="\n",
	)

	problems = verify_tree(repo_root, load_lock(lock_path))

	assert any("field 'name' does not match" in problem for problem in problems)


@pytest.mark.parametrize("malformed", [False, True])
def test_verify_reports_a_missing_or_malformed_contract(tmp_path: Path, malformed: bool) -> None:
	repo_root, lock_path, _upstream_root = _build_vendored_tree(tmp_path)
	contract_path = repo_root / "addon" / "dictionaries" / "contract.ini"
	if malformed:
		_ = contract_path.write_text("not an ini file\n", encoding="utf-8")
	else:
		contract_path.unlink()

	problems = verify_tree(repo_root, load_lock(lock_path))

	assert any("contract.ini is missing or malformed" in problem for problem in problems)


def test_verify_reports_an_unknown_set_directory(tmp_path: Path) -> None:
	repo_root, lock_path, _upstream_root = _build_vendored_tree(tmp_path)
	sets_root = repo_root / "addon" / "dictionaries" / "sets"
	(sets_root / "github.example.unknown").mkdir()

	problems = verify_tree(repo_root, load_lock(lock_path))

	assert any("Unknown entry 'github.example.unknown'" in problem for problem in problems)


def test_verify_reports_an_empty_files_section(tmp_path: Path) -> None:
	repo_root, lock_path, _upstream_root = _build_vendored_tree(tmp_path)
	_write_lock(lock_path)

	problems = verify_tree(repo_root, load_lock(lock_path))

	assert any(f"[files {SET_ID}] must not be empty" in problem for problem in problems)
