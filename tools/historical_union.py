"""Refresh and verify the migration scanner's pinned historical-line union."""

from __future__ import annotations

import argparse
import configparser
import hashlib
import io
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, cast, override


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT / "addon" / "globalPlugins" / "eloquenceDictionaryManager"
if str(PACKAGE_PARENT) not in sys.path:
	sys.path.insert(0, str(PACKAGE_PARENT))

from ecidic import (  # noqa: E402
	LANGUAGES,
	Language,
	Slot,
	historical_artifact_name,
	historical_line_digest,
	parse_dictionary_filename,
	validate_historical_artifact,
)


FORMAT_SECTION = "historicalUnion"
FORMAT_NAME = "eci-historical-union"
FORMAT_VERSION = "1"
FORMAT_FIELDS = (
	"format",
	"version",
	"digest",
	"normalized_line_encoding",
	"artifact_encoding",
	"data_status",
)
FORMAT_VALUES = {
	"format": FORMAT_NAME,
	"version": FORMAT_VERSION,
	"digest": "sha256",
	"normalized_line_encoding": "utf-8",
	"artifact_encoding": "sorted-concatenated-raw-sha256",
}
REPOSITORY_SECTION_PREFIX = "repository "
REPOSITORY_FIELDS = ("url", "head_revision", "reachable_commit_count", "reachable_commits_sha256")
ARTIFACTS_SECTION = "artifacts"
SHA1_LENGTH = 40
SHA256_LENGTH = 64
PLACEHOLDER_REVISION = "0" * SHA1_LENGTH

type UnionKey = tuple[str, Slot]
type HistoricalDigests = dict[UnionKey, set[bytes]]


class HistoricalUnionError(ValueError):
	"""Raised when history cannot be collected or an artifact lock is invalid."""


class CliArgumentParser(argparse.ArgumentParser):
	"""An argument parser whose invalid input follows the tool's exit-1 contract."""

	@override
	def error(self, message: str) -> NoReturn:
		raise HistoricalUnionError(f"Invalid command line: {message}")


class CaseSensitiveConfigParser(configparser.ConfigParser):
	"""A ConfigParser that preserves artifact filename casing."""

	@override
	def optionxform(self, optionstr: str) -> str:
		return optionstr


@dataclass(frozen=True, slots=True)
class RepositorySource:
	"""One full-history upstream included in the combined union."""

	id: str
	url: str


@dataclass(frozen=True, slots=True)
class RepositoryState:
	"""The exact reachable history observed while refreshing one upstream."""

	source: RepositorySource
	head_revision: str
	reachable_commit_count: int
	reachable_commits_sha256: str


@dataclass(frozen=True, slots=True)
class HistoricalUnionLock:
	"""Parsed generation metadata and hashes for the committed artifacts."""

	data_status: str
	repositories: dict[str, RepositoryState]
	artifacts: dict[str, str]


UPSTREAM_REPOSITORIES = (
	RepositorySource(
		id="github.eigencrow.ibmtts-dictionaries",
		url="https://github.com/eigencrow/IBMTTSDictionaries.git",
	),
	RepositorySource(
		id="github.mohamed00.alt-ibmtts-dictionaries",
		url="https://github.com/mohamed00/AltIBMTTSDictionaries.git",
	),
)


def _new_parser() -> CaseSensitiveConfigParser:
	return CaseSensitiveConfigParser(interpolation=None)


def _is_lower_hex(value: str, length: int) -> bool:
	return len(value) == length and all(character in "0123456789abcdef" for character in value)


def _section_values(
	parser: configparser.ConfigParser,
	section: str,
	required_fields: Sequence[str],
) -> dict[str, str]:
	actual_fields = tuple(parser.options(section))
	if set(actual_fields) != set(required_fields):
		missing = sorted(set(required_fields) - set(actual_fields))
		extra = sorted(set(actual_fields) - set(required_fields))
		details: list[str] = []
		if missing:
			details.append(f"missing {', '.join(missing)}")
		if extra:
			details.append(f"unexpected {', '.join(extra)}")
		raise HistoricalUnionError(f"[{section}] has invalid fields ({'; '.join(details)}).")
	values = {field: parser.get(section, field) for field in required_fields}
	for field, value in values.items():
		if not value:
			raise HistoricalUnionError(f"[{section}] field {field!r} must not be empty.")
	return values


def artifact_names() -> tuple[str, ...]:
	"""Return all 30 deterministic artifact filenames."""

	return tuple(
		sorted(historical_artifact_name(language, slot) for language in LANGUAGES.values() for slot in Slot),
	)


def empty_historical_digests() -> HistoricalDigests:
	"""Create an empty bucket for every supported language and slot."""

	return {(language.code, slot): set() for language in LANGUAGES.values() for slot in Slot}


def extract_line_digests(data: bytes, language: Language | str, slot: Slot) -> set[bytes]:
	"""Decode one historical dictionary blob and hash every well-formed line.

	Both LF and CRLF are canonicalized away. Blank lines, lines with a bare
	carriage return, and lines without a tab are silently skipped. After splitting
	on the first tab, leading tabs in the value are normalized away; a remaining
	value tab marks the line as malformed and it is skipped.
	"""

	language_record = LANGUAGES[language] if isinstance(language, str) else language
	try:
		text = data.decode(language_record.encoding, errors="strict")
	except UnicodeDecodeError as error:
		raise HistoricalUnionError(
			f"Historical dictionary bytes for {language_record.code} are not valid "
			+ f"{language_record.encoding} at byte {error.start}.",
		) from error
	digests: set[bytes] = set()
	for line in text.replace("\r\n", "\n").split("\n"):
		if not line or "\r" in line or "\t" not in line:
			continue
		key, value = line.split("\t", maxsplit=1)
		value = value.lstrip("\t")
		if "\t" in value:
			continue
		digests.add(historical_line_digest(key, value, slot))
	return digests


def _run_git(arguments: Sequence[str], *, cwd: Path | None = None) -> bytes:
	completed = subprocess.run(
		["git", *arguments],
		cwd=cwd,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		check=False,
	)
	if completed.returncode:
		command = " ".join(("git", *arguments))
		details = completed.stderr.decode("utf-8", errors="replace").strip()
		raise HistoricalUnionError(f"{command} failed with exit {completed.returncode}: {details}")
	return completed.stdout


def _iter_git_blobs(repository: Path, object_ids: Sequence[str]) -> Iterator[tuple[str, bytes]]:
	"""Read many blobs through one bounded-memory ``git cat-file --batch`` process."""

	with (
		tempfile.TemporaryFile(mode="w+b") as request_file,
		tempfile.TemporaryFile(
			mode="w+b",
		) as response_file,
	):
		request = "".join(f"{object_id}\n" for object_id in object_ids).encode("ascii")
		_ = request_file.write(request)
		_ = request_file.seek(0)
		completed = subprocess.run(
			["git", "cat-file", "--batch"],
			cwd=repository,
			stdin=request_file,
			stdout=response_file,
			stderr=subprocess.PIPE,
			check=False,
		)
		if completed.returncode:
			details = completed.stderr.decode("utf-8", errors="replace").strip()
			raise HistoricalUnionError(
				f"git cat-file --batch failed with exit {completed.returncode}: {details}",
			)
		_ = response_file.seek(0)
		for requested_id in object_ids:
			header = response_file.readline().removesuffix(b"\n").split()
			if len(header) != 3 or header[1] != b"blob":
				raise HistoricalUnionError(f"Git object {requested_id} is missing or is not a blob.")
			try:
				returned_id = header[0].decode("ascii")
				size = int(header[2])
			except (UnicodeDecodeError, ValueError) as error:
				raise HistoricalUnionError("git cat-file --batch returned malformed metadata.") from error
			if returned_id != requested_id:
				raise HistoricalUnionError(
					f"git cat-file --batch returned {returned_id} when {requested_id} was requested.",
				)
			data = response_file.read(size)
			if len(data) != size or response_file.read(1) != b"\n":
				raise HistoricalUnionError(f"git cat-file --batch truncated blob {requested_id}.")
			yield returned_id, data
		if response_file.read(1):
			raise HistoricalUnionError("git cat-file --batch returned unexpected trailing bytes.")


def clone_repository(source: RepositorySource, destination: Path) -> None:
	"""Clone every remote ref and all history into a temporary bare mirror."""

	_ = _run_git(("clone", "--mirror", source.url, str(destination)))


def collect_repository_history(
	repository: Path,
	source: RepositorySource,
	digests: HistoricalDigests,
) -> RepositoryState:
	"""Walk every commit reachable from every mirrored ref and merge its dictionary blobs."""

	commit_lines = _run_git(("rev-list", "--all"), cwd=repository).decode("ascii").splitlines()
	commits = sorted(set(commit_lines))
	if not commits or any(not _is_lower_hex(commit, SHA1_LENGTH) for commit in commits):
		raise HistoricalUnionError(f"Repository {source.url} has no valid reachable commits.")
	head_revision = _run_git(("rev-parse", "HEAD"), cwd=repository).decode("ascii").strip()
	if head_revision not in commits:
		raise HistoricalUnionError(
			f"Default-branch revision {head_revision} is not among the reachable commits for {source.url}.",
		)

	# Every file state must first appear as the new side of some reachable
	# commit's diff. --root includes files in root commits; -m exposes merge
	# results against each parent; --no-renames makes every record one-path.
	# This walks the same complete commit graph as rev-list above without
	# spawning one ls-tree process per commit.
	raw_log = _run_git(
		("log", "--all", "--format=", "--raw", "-z", "--no-abbrev", "--root", "-m", "--no-renames"),
		cwd=repository,
	)
	fields = raw_log.split(b"\0")
	blob_targets: dict[str, set[UnionKey]] = {}
	index = 0
	while index < len(fields):
		header = fields[index].lstrip(b"\n")
		index += 1
		if not header:
			continue
		if not header.startswith(b":") or index >= len(fields):
			raise HistoricalUnionError(f"Could not parse raw git history in {source.url}.")
		path_bytes = fields[index]
		index += 1
		metadata = header.split()
		if len(metadata) != 5:
			raise HistoricalUnionError(f"Could not parse raw git metadata in {source.url}.")
		_old_mode, new_mode, _old_id, new_id, _status = metadata
		if new_mode not in {b"100644", b"100755"}:
			continue
		try:
			path = path_bytes.decode("utf-8", errors="strict")
			filename = parse_dictionary_filename(Path(path).name)
			blob_id = new_id.decode("ascii")
		except (UnicodeDecodeError, ValueError):
			continue
		blob_targets.setdefault(blob_id, set()).add((filename.language.code, filename.slot))

	for blob_id, data in _iter_git_blobs(repository, sorted(blob_targets)):
		targets = blob_targets[blob_id]
		for language_code, slot in targets:
			digests[(language_code, slot)].update(extract_line_digests(data, language_code, slot))

	commit_manifest = "".join(f"{commit}\n" for commit in commits).encode("ascii")
	return RepositoryState(
		source=source,
		head_revision=head_revision,
		reachable_commit_count=len(commits),
		reachable_commits_sha256=hashlib.sha256(commit_manifest).hexdigest(),
	)


def _artifact_bytes(digests: Mapping[UnionKey, set[bytes]], language: str, slot: Slot) -> bytes:
	values = digests.get((language, slot), set())
	if any(len(digest) != hashlib.sha256().digest_size for digest in values):
		raise HistoricalUnionError(f"Invalid digest size in historical union for {language}/{slot.value}.")
	return b"".join(sorted(values))


def _write_lock(
	path: Path,
	repository_states: Sequence[RepositoryState],
	artifact_hashes: Mapping[str, str],
	*,
	data_status: str,
) -> None:
	parser = _new_parser()
	parser.add_section(FORMAT_SECTION)
	for field, value in FORMAT_VALUES.items():
		parser.set(FORMAT_SECTION, field, value)
	parser.set(FORMAT_SECTION, "data_status", data_status)
	for state in repository_states:
		section = f"{REPOSITORY_SECTION_PREFIX}{state.source.id}"
		parser.add_section(section)
		parser.set(section, "url", state.source.url)
		parser.set(section, "head_revision", state.head_revision)
		parser.set(section, "reachable_commit_count", str(state.reachable_commit_count))
		parser.set(section, "reachable_commits_sha256", state.reachable_commits_sha256)
	parser.add_section(ARTIFACTS_SECTION)
	for name, digest in sorted(artifact_hashes.items()):
		parser.set(ARTIFACTS_SECTION, name, digest)
	buffer = io.StringIO()
	parser.write(buffer, space_around_delimiters=True)
	try:
		_ = path.write_text(
			buffer.getvalue().rstrip("\n") + "\n",
			encoding="utf-8",
			newline="\n",
		)
	except OSError as error:
		raise HistoricalUnionError(f"Could not write historical-union lock {path}: {error}") from error


def write_historical_union(
	repo_root: Path,
	lock_path: Path,
	repository_states: Sequence[RepositoryState],
	digests: Mapping[UnionKey, set[bytes]],
	*,
	data_status: str = "complete",
) -> None:
	"""Write all deterministic binary artifacts and their companion lock."""

	if data_status not in {"complete", "placeholder"}:
		raise HistoricalUnionError(f"Unsupported historical-union data status {data_status!r}.")
	expected_sources = {source.id for source in UPSTREAM_REPOSITORIES}
	actual_sources = {state.source.id for state in repository_states}
	if actual_sources != expected_sources or len(repository_states) != len(expected_sources):
		raise HistoricalUnionError("Repository states do not match the required historical upstreams.")
	expected_keys = {(language.code, slot) for language in LANGUAGES.values() for slot in Slot}
	if set(digests) - expected_keys:
		raise HistoricalUnionError("Historical union contains an unsupported language or slot.")

	artifact_root = repo_root / "addon" / "dictionaries" / "historicalUnion"
	artifact_root.mkdir(parents=True, exist_ok=True)
	expected_names = set(artifact_names())
	for entry in artifact_root.iterdir():
		if entry.name in expected_names:
			continue
		if entry.is_dir():
			shutil.rmtree(entry)
		else:
			entry.unlink()
	artifact_hashes: dict[str, str] = {}
	for language in LANGUAGES.values():
		for slot in Slot:
			name = historical_artifact_name(language, slot)
			data = _artifact_bytes(digests, language.code, slot)
			_ = (artifact_root / name).write_bytes(data)
			artifact_hashes[name] = hashlib.sha256(data).hexdigest()
	_write_lock(
		lock_path,
		sorted(repository_states, key=lambda state: state.source.id),
		artifact_hashes,
		data_status=data_status,
	)


def load_lock(path: Path) -> HistoricalUnionLock:
	"""Parse and strictly validate historical-union generation metadata."""

	parser = _new_parser()
	try:
		with path.open("r", encoding="utf-8") as lock_file:
			parser.read_file(lock_file)
	except (OSError, UnicodeError, configparser.Error) as error:
		raise HistoricalUnionError(f"Could not read historical-union lock {path}: {error}") from error
	if parser.defaults():
		raise HistoricalUnionError("Historical-union lock must not contain a [DEFAULT] section.")
	expected_sections = {
		FORMAT_SECTION,
		ARTIFACTS_SECTION,
		*(f"{REPOSITORY_SECTION_PREFIX}{source.id}" for source in UPSTREAM_REPOSITORIES),
	}
	if set(parser.sections()) != expected_sections:
		raise HistoricalUnionError("Historical-union lock does not contain the required sections.")
	format_values = _section_values(parser, FORMAT_SECTION, FORMAT_FIELDS)
	for field, expected in FORMAT_VALUES.items():
		if format_values[field] != expected:
			raise HistoricalUnionError(
				f"[{FORMAT_SECTION}] field {field!r} must be {expected!r}.",
			)
	data_status = format_values["data_status"]
	if data_status not in {"complete", "placeholder"}:
		raise HistoricalUnionError(f"[{FORMAT_SECTION}] has invalid data_status {data_status!r}.")

	repositories: dict[str, RepositoryState] = {}
	for source in UPSTREAM_REPOSITORIES:
		section = f"{REPOSITORY_SECTION_PREFIX}{source.id}"
		values = _section_values(parser, section, REPOSITORY_FIELDS)
		if values["url"] != source.url:
			raise HistoricalUnionError(f"[{section}] URL does not match the required upstream.")
		if not _is_lower_hex(values["head_revision"], SHA1_LENGTH):
			raise HistoricalUnionError(f"[{section}] head_revision must be a lowercase 40-hex SHA.")
		if not _is_lower_hex(values["reachable_commits_sha256"], SHA256_LENGTH):
			raise HistoricalUnionError(
				f"[{section}] reachable_commits_sha256 must be a lowercase SHA-256 digest.",
			)
		try:
			commit_count = int(values["reachable_commit_count"])
		except ValueError as error:
			raise HistoricalUnionError(f"[{section}] reachable_commit_count must be an integer.") from error
		if commit_count < 0 or (data_status == "complete" and commit_count == 0):
			raise HistoricalUnionError(
				f"[{section}] reachable_commit_count is not valid for {data_status} data.",
			)
		repositories[source.id] = RepositoryState(
			source=source,
			head_revision=values["head_revision"],
			reachable_commit_count=commit_count,
			reachable_commits_sha256=values["reachable_commits_sha256"],
		)

	artifacts = dict(parser.items(ARTIFACTS_SECTION))
	if set(artifacts) != set(artifact_names()):
		raise HistoricalUnionError("[artifacts] must list exactly one file per language and slot.")
	for name, digest in artifacts.items():
		if not _is_lower_hex(digest, SHA256_LENGTH):
			raise HistoricalUnionError(f"[artifacts] {name!r} must have a lowercase SHA-256 digest.")
	return HistoricalUnionLock(data_status=data_status, repositories=repositories, artifacts=artifacts)


def verify_tree(repo_root: Path, lock: HistoricalUnionLock) -> list[str]:
	"""Verify committed artifacts against the lock without git or network access."""

	artifact_root = repo_root / "addon" / "dictionaries" / "historicalUnion"
	if not artifact_root.is_dir():
		return ["addon/dictionaries/historicalUnion is missing"]
	problems: list[str] = []
	actual_names = {path.name for path in artifact_root.iterdir()}
	expected_names = set(lock.artifacts)
	for name in sorted(expected_names - actual_names):
		problems.append(f"historicalUnion/{name} is listed in the lock but missing")
	for name in sorted(actual_names - expected_names):
		problems.append(f"historicalUnion/{name} is not listed in the lock")
	for name, expected_hash in lock.artifacts.items():
		path = artifact_root / name
		if not path.is_file():
			continue
		try:
			data = path.read_bytes()
		except OSError as error:
			problems.append(f"historicalUnion/{name} could not be read: {error}")
			continue
		actual_hash = hashlib.sha256(data).hexdigest()
		if actual_hash != expected_hash:
			problems.append(f"historicalUnion/{name} sha256 does not match the historical-union lock")
		try:
			validate_historical_artifact(data, path)
		except ValueError as error:
			problems.append(str(error))
	return problems


def refresh(repo_root: Path, lock_path: Path) -> None:
	"""Clone both upstream histories, build their combined union, and pin the result."""

	digests = empty_historical_digests()
	states: list[RepositoryState] = []
	with tempfile.TemporaryDirectory(prefix="edm-historical-union-") as temporary:
		temporary_root = Path(temporary)
		for source in UPSTREAM_REPOSITORIES:
			repository = temporary_root / source.id
			clone_repository(source, repository)
			state = collect_repository_history(repository, source, digests)
			states.append(state)
			print(
				f"Walked {state.reachable_commit_count} reachable commit(s) from {source.id} "
				+ f"at default-branch revision {state.head_revision}.",
			)
	write_historical_union(repo_root, lock_path, states, digests)


def _build_parser() -> argparse.ArgumentParser:
	parser = CliArgumentParser(description=__doc__)
	_ = parser.add_argument(
		"--repo-root",
		type=Path,
		default=REPO_ROOT,
		help=argparse.SUPPRESS,
	)
	subparsers = parser.add_subparsers(dest="command", required=True)
	_ = subparsers.add_parser("refresh")
	_ = subparsers.add_parser("verify")
	return parser


def main(argv: Sequence[str] | None = None) -> int:
	"""Run the maintainer CLI and return its process exit status."""

	try:
		arguments = _build_parser().parse_args(argv)
		repo_root = cast(Path, arguments.repo_root).resolve()
		command = cast(str, arguments.command)
		lock_path = repo_root / "historicalUnion.lock.ini"
		if command == "refresh":
			refresh(repo_root, lock_path)
			lock = load_lock(lock_path)
			entry_count = sum(
				(repo_root / "addon" / "dictionaries" / "historicalUnion" / name).stat().st_size
				// hashlib.sha256().digest_size
				for name in lock.artifacts
			)
			print(f"Refreshed 30 historical-union artifact(s) containing {entry_count} digest(s).")
			return 0
		lock = load_lock(lock_path)
		problems = verify_tree(repo_root, lock)
		if problems:
			for problem in problems:
				print(f"ERROR: {problem}")
			return 1
		print(
			f"Verified {len(lock.artifacts)} historical-union artifact(s) against the lock "
			+ f"offline ({lock.data_status} data).",
		)
		return 0
	except (HistoricalUnionError, OSError) as error:
		print(f"ERROR: {error}")
		return 1


if __name__ == "__main__":
	raise SystemExit(main())
