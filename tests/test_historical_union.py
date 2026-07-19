from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from ecidic import (
	HistoricalUnion,
	Slot,
	historical_artifact_name,
	historical_line_digest,
	normalize_historical_line,
)
from historical_union import (
	UPSTREAM_REPOSITORIES,
	RepositorySource,
	RepositoryState,
	collect_repository_history,
	empty_historical_digests,
	extract_line_digests,
	load_lock,
	verify_tree,
	write_historical_union,
)


def test_normalization_preserves_pair_text_and_only_casefolds_root_keys() -> None:
	assert normalize_historical_line("Word", " value  ", Slot.MAIN) == b"Word\t value  "
	assert normalize_historical_line("Word", " value  ", Slot.ABBREVIATION) == b"Word\t value  "
	assert normalize_historical_line("Stra\u00dfe", " value  ", Slot.ROOT) == b"strasse\t value  "
	assert historical_line_digest("Stra\u00dfe", "value", Slot.ROOT) == historical_line_digest(
		"STRASSE",
		"value",
		Slot.ROOT,
	)
	assert historical_line_digest("Word", "value", Slot.MAIN) != historical_line_digest(
		"word",
		"value",
		Slot.MAIN,
	)
	assert historical_line_digest("Word", "value ", Slot.MAIN) != historical_line_digest(
		"Word",
		"value",
		Slot.MAIN,
	)


def test_extraction_canonicalizes_line_endings_and_skips_malformed_lines() -> None:
	data = (
		b"First\tvalue with space \r\n"
		b"Second\tvalue\n"
		b"no separator\r\n"
		b"too\tmany\ttabs\n"
		b"bare\treturn\rnext\tvalue\n"
		b"\r\n"
	)

	assert extract_line_digests(data, "enu", Slot.MAIN) == {
		historical_line_digest("First", "value with space ", Slot.MAIN),
		historical_line_digest("Second", "value", Slot.MAIN),
	}
	assert extract_line_digests(b"Word\tvalue\r\n", "enu", Slot.MAIN) == extract_line_digests(
		b"Word\tvalue\n",
		"enu",
		Slot.MAIN,
	)
	assert extract_line_digests(b"word\t\tpron\r\n", "enu", Slot.MAIN) == extract_line_digests(
		b"word\tpron\r\n",
		"enu",
		Slot.MAIN,
	)
	assert extract_line_digests(b"a\tb\tc\r\n", "enu", Slot.MAIN) == set()
	assert extract_line_digests(b"no separator\r\n", "enu", Slot.MAIN) == set()


def _write_digest_file(root: Path, language: str, slot: Slot, *digests: bytes) -> None:
	root.mkdir(parents=True, exist_ok=True)
	_ = (root / historical_artifact_name(language, slot)).write_bytes(b"".join(sorted(set(digests))))


def test_loader_membership_is_fast_normalized_and_isolated_by_language_and_slot(tmp_path: Path) -> None:
	root = tmp_path / "historicalUnion"
	main_digest = historical_line_digest("Exact", "value ", Slot.MAIN)
	root_digest = historical_line_digest("MixedCase", "root value", Slot.ROOT)
	_write_digest_file(root, "enu", Slot.MAIN, main_digest)
	_write_digest_file(root, "enu", Slot.ROOT, root_digest)
	_write_digest_file(root, "deu", Slot.MAIN)
	union = HistoricalUnion(root)

	assert union.contains("enu", Slot.MAIN, "Exact", "value ")
	assert not union.contains("enu", Slot.MAIN, "exact", "value ")
	assert not union.contains("enu", Slot.MAIN, "Exact", "value")
	assert union.contains("enu", Slot.ROOT, "mixedcase", "root value")
	assert union.contains("enu", Slot.ROOT, "MIXEDCASE", "root value")
	assert not union.contains("enu", Slot.MAIN, "MixedCase", "root value")
	assert not union.contains("deu", Slot.MAIN, "Exact", "value ")


def _repository_states() -> list[RepositoryState]:
	return [
		RepositoryState(
			source=source,
			head_revision=f"{index}" * 40,
			reachable_commit_count=index,
			reachable_commits_sha256=f"{index}" * 64,
		)
		for index, source in enumerate(UPSTREAM_REPOSITORIES, start=1)
	]


def test_offline_verify_passes_for_matching_artifacts_and_reports_tampering(tmp_path: Path) -> None:
	repo_root = tmp_path / "repo"
	repo_root.mkdir()
	lock_path = repo_root / "historicalUnion.lock.ini"
	digests = empty_historical_digests()
	digests[("enu", Slot.MAIN)].add(historical_line_digest("present", "value", Slot.MAIN))
	write_historical_union(repo_root, lock_path, _repository_states(), digests)
	lock = load_lock(lock_path)

	assert verify_tree(repo_root, lock) == []
	artifact = repo_root / "addon" / "dictionaries" / "historicalUnion" / "enumain.sha256"
	_ = artifact.write_bytes(artifact.read_bytes() + hashlib.sha256(b"tampered").digest())

	problems = verify_tree(repo_root, lock)
	assert any("enumain.sha256 sha256 does not match" in problem for problem in problems)


def _git(repository: Path, *arguments: str) -> None:
	_ = subprocess.run(
		["git", *arguments],
		cwd=repository,
		check=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)


def test_history_walk_includes_commits_reachable_only_from_another_branch(tmp_path: Path) -> None:
	repository = tmp_path / "upstream"
	repository.mkdir()
	_git(repository, "init", "-b", "main")
	_git(repository, "config", "user.name", "Test")
	_git(repository, "config", "user.email", "test@example.com")
	_ = (repository / "ENUmain.dic").write_bytes(b"main\tvalue\r\n")
	_git(repository, "add", "ENUmain.dic")
	_git(repository, "commit", "-m", "main version")
	_git(repository, "switch", "-c", "historical")
	_ = (repository / "ENUmain.dic").write_bytes(b"branch\tvalue\n")
	_git(repository, "add", "ENUmain.dic")
	_git(repository, "commit", "-m", "branch-only version")
	_git(repository, "switch", "main")

	digests = empty_historical_digests()
	state = collect_repository_history(
		repository,
		RepositorySource(id="test", url="local"),
		digests,
	)

	assert state.reachable_commit_count == 2
	assert historical_line_digest("main", "value", Slot.MAIN) in digests[("enu", Slot.MAIN)]
	assert historical_line_digest("branch", "value", Slot.MAIN) in digests[("enu", Slot.MAIN)]
