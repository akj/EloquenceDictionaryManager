"""Refresh and verify pinned Managed Dictionary Sets."""

from __future__ import annotations

import argparse
import configparser
import hashlib
import json
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, NoReturn, cast, override


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT / "addon" / "globalPlugins" / "eloquenceDictionaryManager"
if str(PACKAGE_PARENT) not in sys.path:
	sys.path.insert(0, str(PACKAGE_PARENT))

from ecidic import DictionaryFilename, Entry, parse_dictionary_filename, validate_entry  # noqa: E402


SET_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SET_SECTION_PREFIX = "set "
FILES_SECTION_PREFIX = "files "
SET_LOCK_FIELDS = (
	"github_repository",
	"name",
	"source_url",
	"source_version",
	"source_revision",
	"attribution",
	"license",
	"license_url",
	"license_file",
	"license_sha256",
)
SET_INI_FIELDS = (
	"id",
	"name",
	"source_url",
	"source_version",
	"source_revision",
	"attribution",
	"license",
	"license_url",
)
CONTRACT_TEXT = "[contract]\nformat = eci-dictionary-sets\nversion = 1\n"
CC0_LICENSE = "CC0-1.0"
USER_AGENT = "EloquenceDictionaryManager vendored_sets.py"


class VendoringError(ValueError):
	"""Raised when a source lock or upstream set cannot be vendored safely."""


class CliArgumentParser(argparse.ArgumentParser):
	"""An argument parser whose invalid input follows the tool's exit-1 contract."""

	@override
	def error(self, message: str) -> NoReturn:
		raise VendoringError(f"Invalid command line: {message}")


class CaseSensitiveConfigParser(configparser.ConfigParser):
	"""A ConfigParser that preserves dictionary filename casing."""

	@override
	def optionxform(self, optionstr: str) -> str:
		return optionstr


@dataclass(frozen=True, slots=True)
class SetConfig:
	"""Maintainer-authored metadata for one pinned Managed Dictionary Set."""

	id: str
	github_repository: str
	name: str
	source_url: str
	source_version: str
	source_revision: str
	attribution: str
	license: str
	license_url: str
	license_file: str
	license_sha256: str


@dataclass(frozen=True, slots=True)
class SourceLock:
	"""Parsed source metadata and generated hashes from the repository lock."""

	sets: dict[str, SetConfig]
	files: dict[str, dict[str, str]]


def _new_parser() -> CaseSensitiveConfigParser:
	return CaseSensitiveConfigParser(interpolation=None)


def _validate_set_id(set_id: str) -> None:
	if SET_ID_PATTERN.fullmatch(set_id) is None:
		raise VendoringError(
			f"Managed Dictionary Set ID {set_id!r} does not match {SET_ID_PATTERN.pattern}.",
		)


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
		raise VendoringError(f"[{section}] has invalid fields ({'; '.join(details)}).")
	values = {field: parser.get(section, field) for field in required_fields}
	for field, value in values.items():
		if not value:
			raise VendoringError(f"[{section}] field {field!r} must not be empty.")
	return values


def load_lock(path: Path) -> SourceLock:
	"""Parse and validate a vendored-source lock file."""

	parser = _new_parser()
	try:
		with path.open("r", encoding="utf-8") as lock_file:
			parser.read_file(lock_file)
	except (OSError, UnicodeError, configparser.Error) as error:
		raise VendoringError(f"Could not read source lock {path}: {error}") from error
	if parser.defaults():
		raise VendoringError("Source lock must not contain a [DEFAULT] section.")

	set_ids: list[str] = []
	file_ids: list[str] = []
	for section in parser.sections():
		if section.startswith(SET_SECTION_PREFIX):
			set_id = section.removeprefix(SET_SECTION_PREFIX)
			_validate_set_id(set_id)
			set_ids.append(set_id)
		elif section.startswith(FILES_SECTION_PREFIX):
			set_id = section.removeprefix(FILES_SECTION_PREFIX)
			_validate_set_id(set_id)
			file_ids.append(set_id)
		else:
			raise VendoringError(f"Source lock contains unsupported section [{section}].")
	if not set_ids:
		raise VendoringError("Source lock does not define any [set <id>] sections.")
	if set(set_ids) != set(file_ids):
		missing = sorted(set(set_ids) - set(file_ids))
		extra = sorted(set(file_ids) - set(set_ids))
		details: list[str] = []
		if missing:
			details.append(f"missing [files] sections for {', '.join(missing)}")
		if extra:
			details.append(f"orphan [files] sections for {', '.join(extra)}")
		raise VendoringError(f"Source lock set/file sections disagree ({'; '.join(details)}).")

	sets: dict[str, SetConfig] = {}
	files: dict[str, dict[str, str]] = {}
	for set_id in set_ids:
		values = _section_values(parser, f"{SET_SECTION_PREFIX}{set_id}", SET_LOCK_FIELDS)
		if REVISION_PATTERN.fullmatch(values["source_revision"]) is None:
			raise VendoringError(
				f"[set {set_id}] source_revision must be a full lowercase 40-hex commit SHA.",
			)
		if SHA256_PATTERN.fullmatch(values["license_sha256"]) is None:
			raise VendoringError(
				f"[set {set_id}] license_sha256 must be a lowercase 64-hex SHA-256 digest.",
			)
		sets[set_id] = SetConfig(id=set_id, **values)
		files[set_id] = dict(parser.items(f"{FILES_SECTION_PREFIX}{set_id}"))
	return SourceLock(sets=sets, files=files)


def _set_ini_values(set_config: SetConfig) -> dict[str, str]:
	"""Map the lock metadata onto the eight required ``set.ini`` fields."""

	return {field: getattr(set_config, field) for field in SET_INI_FIELDS}


def generate_set_ini_text(set_config: SetConfig) -> str:
	"""Generate canonical installed metadata for one managed set."""

	values = _set_ini_values(set_config)
	return "[set]\n" + "".join(f"{field} = {values[field]}\n" for field in SET_INI_FIELDS)


def _decode_dictionary_bytes(name: str, data: bytes) -> tuple[DictionaryFilename, str]:
	"""Fail closed on an unsupported filename or bytes outside the code page."""

	try:
		filename = parse_dictionary_filename(name)
		text = data.decode(filename.language.encoding, errors="strict")
	except (ValueError, UnicodeError) as error:
		raise VendoringError(f"Dictionary {name!r} is invalid: {error}") from error
	return filename, text


def _validate_dictionary_bytes(name: str, data: bytes) -> list[str]:
	"""Validate fail-closed corruption signs; return soft per-line warnings.

	The engine ignores individually malformed lines and invalid entries at
	lookup time, and upstream sets knowingly ship a few, so line structure and
	editor-grade entry rules must not block vendoring content verbatim — they
	are surfaced to the maintainer as warnings instead. Undecodable bytes and
	unsupported filenames still abort the refresh.
	"""

	filename, text = _decode_dictionary_bytes(name, data)
	examples: list[str] = []
	invalid_count = 0

	def note(line_number: int, message: str) -> None:
		nonlocal invalid_count
		invalid_count += 1
		if len(examples) < 3:
			examples.append(f"line {line_number}: {message}")

	lines = text.replace("\r\n", "\n").split("\n")
	if lines and lines[-1] == "":
		_ = lines.pop()
	for line_number, line in enumerate(lines, start=1):
		if not line or "\r" in line:
			note(line_number, "the line is blank or has an unsupported line ending")
			continue
		if line.count("\t") != 1:
			note(line_number, "the line does not contain exactly one tab")
			continue
		key, value = line.split("\t")
		issues = validate_entry(Entry(key=key, value=value), filename.slot, filename.language)
		if issues:
			note(line_number, f"{key!r}: {issues[0].message}")
	if not invalid_count:
		return []
	return [
		f"{name}: {invalid_count} line(s) violate the dictionary format or editor validation "
		+ f"rules and will be ignored by the engine at lookup time ({'; '.join(examples)})",
	]


def process_upstream_tree(
	extract_dir: Path,
	set_config: SetConfig,
	warnings: list[str] | None = None,
) -> dict[str, bytes]:
	"""Validate a downloaded upstream root and return canonical verbatim files."""

	if set_config.license != CC0_LICENSE:
		raise VendoringError(
			f"Set {set_config.id!r} uses unsupported license {set_config.license!r}; only "
			+ f"{CC0_LICENSE} is currently allowed.",
		)
	if Path(set_config.license_file).name != set_config.license_file:
		raise VendoringError(
			f"Set {set_config.id!r} license_file must name a file in the archive root.",
		)
	license_path = extract_dir / set_config.license_file
	if not license_path.is_file():
		raise VendoringError(
			f"Set {set_config.id!r} is missing license file {set_config.license_file!r}.",
		)
	try:
		license_bytes = license_path.read_bytes()
	except OSError as error:
		raise VendoringError(f"Could not read license file {license_path}: {error}") from error
	license_hash = hashlib.sha256(license_bytes).hexdigest()
	if license_hash != set_config.license_sha256:
		raise VendoringError(
			f"Set {set_config.id!r} license file hashes to {license_hash}, not the pinned "
			+ "license_sha256. Review the upstream license change and update the lock deliberately.",
		)

	result: dict[str, bytes] = {}
	for path in sorted(extract_dir.iterdir(), key=lambda item: item.name.casefold()):
		if not path.is_file() or path.suffix.lower() != ".dic":
			continue
		try:
			parsed = parse_dictionary_filename(path.name)
		except ValueError as error:
			raise VendoringError(
				f"Unsupported upstream dictionary filename {path.name!r}: {error}",
			) from error
		canonical_name = parsed.canonical_name
		if canonical_name in result:
			raise VendoringError(
				f"More than one upstream file maps to canonical filename {canonical_name!r}.",
			)
		try:
			data = path.read_bytes()
		except OSError as error:
			raise VendoringError(f"Could not read dictionary {path}: {error}") from error
		file_warnings = _validate_dictionary_bytes(path.name, data)
		if warnings is not None:
			warnings.extend(file_warnings)
		result[canonical_name] = data
	if not result:
		raise VendoringError(f"Set {set_config.id!r} contains no top-level .dic files.")
	return result


def _write_lock(path: Path, lock: SourceLock, files_by_set: Mapping[str, Mapping[str, bytes]]) -> None:
	parser = _new_parser()
	for set_id, set_config in lock.sets.items():
		set_section = f"{SET_SECTION_PREFIX}{set_id}"
		parser.add_section(set_section)
		for field in SET_LOCK_FIELDS:
			parser.set(set_section, field, getattr(set_config, field))
		files_section = f"{FILES_SECTION_PREFIX}{set_id}"
		parser.add_section(files_section)
		for filename, data in sorted(files_by_set[set_id].items()):
			parser.set(files_section, filename, hashlib.sha256(data).hexdigest())
	try:
		with path.open("w", encoding="utf-8", newline="\n") as lock_file:
			parser.write(lock_file, space_around_delimiters=True)
	except OSError as error:
		raise VendoringError(f"Could not rewrite source lock {path}: {error}") from error


def write_vendored_sets(
	repo_root: Path,
	lock_path: Path,
	lock: SourceLock,
	files_by_set: Mapping[str, Mapping[str, bytes]],
) -> None:
	"""Replace the installed dictionary tree and generated lock hashes."""

	if set(files_by_set) != set(lock.sets):
		raise VendoringError("Processed set IDs do not match the source lock.")
	dictionaries_root = repo_root / "addon" / "dictionaries"
	sets_root = dictionaries_root / "sets"
	sets_root.mkdir(parents=True, exist_ok=True)
	for entry in sets_root.iterdir():
		if entry.name not in lock.sets:
			if entry.is_dir():
				shutil.rmtree(entry)
			else:
				entry.unlink()
	_ = (dictionaries_root / "contract.ini").write_text(
		CONTRACT_TEXT,
		encoding="utf-8",
		newline="\n",
	)
	for set_id, set_config in lock.sets.items():
		set_directory = sets_root / set_id
		if set_directory.exists():
			shutil.rmtree(set_directory)
		set_directory.mkdir()
		_ = (set_directory / "set.ini").write_text(
			generate_set_ini_text(set_config),
			encoding="utf-8",
			newline="\n",
		)
		for filename, data in sorted(files_by_set[set_id].items()):
			_ = (set_directory / filename).write_bytes(data)
	_write_lock(lock_path, lock, files_by_set)


def _read_ini(path: Path) -> tuple[CaseSensitiveConfigParser | None, str | None]:
	parser = _new_parser()
	try:
		with path.open("r", encoding="utf-8") as ini_file:
			parser.read_file(ini_file)
	except (OSError, UnicodeError, configparser.Error) as error:
		return None, str(error)
	return parser, None


def _verify_contract(dictionaries_root: Path) -> list[str]:
	path = dictionaries_root / "contract.ini"
	parser, error = _read_ini(path)
	if parser is None:
		return [f"contract.ini is missing or malformed: {error}"]
	problems: list[str] = []
	if parser.defaults():
		problems.append("contract.ini must not contain a [DEFAULT] section")
	if parser.sections() != ["contract"]:
		problems.append("contract.ini must contain exactly one [contract] section")
	elif set(parser.options("contract")) != {"format", "version"}:
		problems.append("contract.ini [contract] must contain exactly format and version")
	else:
		if parser.get("contract", "format") != "eci-dictionary-sets":
			problems.append("contract.ini format must be 'eci-dictionary-sets'")
		if parser.get("contract", "version") != "1":
			problems.append("contract.ini version must be '1'")
	return problems


def _directory_names(path: Path) -> set[str]:
	try:
		return {entry.name for entry in path.iterdir()}
	except OSError:
		return set()


def _verify_set_ini(path: Path, set_config: SetConfig) -> list[str]:
	parser, error = _read_ini(path)
	if parser is None:
		return [f"{set_config.id}/set.ini is missing or malformed: {error}"]
	if parser.sections() != ["set"]:
		return [f"{set_config.id}/set.ini must contain exactly one [set] section"]
	problems: list[str] = []
	if parser.defaults():
		problems.append(f"{set_config.id}/set.ini must not contain a [DEFAULT] section")
	actual_fields = set(parser.options("set"))
	if actual_fields != set(SET_INI_FIELDS):
		problems.append(f"{set_config.id}/set.ini must contain exactly the eight required fields")
	values = _set_ini_values(set_config)
	for field in SET_INI_FIELDS:
		if field in actual_fields and parser.get("set", field) != values[field]:
			problems.append(f"{set_config.id}/set.ini field {field!r} does not match the source lock")
	return problems


def _verify_dictionary(path: Path, expected_hash: str, set_id: str, listed_name: str) -> list[str]:
	problems: list[str] = []
	try:
		parsed = parse_dictionary_filename(listed_name)
	except ValueError as error:
		return [f"{set_id}/{listed_name} is not a supported dictionary filename: {error}"]
	if listed_name != parsed.canonical_name:
		problems.append(f"{set_id}/{listed_name} is not a canonical lowercase dictionary filename")
	if not path.is_file():
		problems.append(f"{set_id}/{listed_name} is listed in the lock but missing")
		return problems
	try:
		data = path.read_bytes()
	except OSError as error:
		problems.append(f"{set_id}/{listed_name} could not be read: {error}")
		return problems
	actual_hash = hashlib.sha256(data).hexdigest()
	if actual_hash != expected_hash:
		problems.append(f"{set_id}/{listed_name} sha256 does not match the source lock")
	try:
		_ = data.decode(parsed.language.encoding, errors="strict")
	except UnicodeError as error:
		problems.append(f"{set_id}/{listed_name} contains undecodable dictionary bytes: {error}")
	return problems


def _verify_set(set_directory: Path, set_config: SetConfig, locked_files: Mapping[str, str]) -> list[str]:
	problems = _verify_set_ini(set_directory / "set.ini", set_config)
	if not locked_files:
		problems.append(f"[files {set_config.id}] must not be empty")
	expected_names = {"set.ini", *locked_files}
	actual_names = _directory_names(set_directory)
	for name in sorted(expected_names - actual_names):
		problems.append(f"{set_config.id}/{name} is missing from the set directory")
	for name in sorted(actual_names - expected_names):
		problems.append(f"{set_config.id}/{name} is not listed in the source lock")
	actual_paths = {path.name: path for path in set_directory.iterdir()} if set_directory.is_dir() else {}
	for filename, expected_hash in locked_files.items():
		path = actual_paths.get(filename, set_directory / filename)
		problems.extend(_verify_dictionary(path, expected_hash, set_config.id, filename))
	return problems


def verify_tree(repo_root: Path, lock: SourceLock) -> list[str]:
	"""Return every problem in the installed directory contract tree."""

	problems: list[str] = []
	dictionaries_root = repo_root / "addon" / "dictionaries"
	if not dictionaries_root.is_dir():
		return ["addon/dictionaries is missing"]
	expected_dictionary_entries = {"contract.ini", "sets"}
	actual_dictionary_entries = _directory_names(dictionaries_root)
	for name in sorted(expected_dictionary_entries - actual_dictionary_entries):
		problems.append(f"addon/dictionaries/{name} is missing")
	for name in sorted(actual_dictionary_entries - expected_dictionary_entries):
		problems.append(f"addon/dictionaries/{name} is unexpected")
	problems.extend(_verify_contract(dictionaries_root))

	sets_root = dictionaries_root / "sets"
	if not sets_root.is_dir():
		problems.append("addon/dictionaries/sets is missing or is not a directory")
		return problems
	actual_set_names = _directory_names(sets_root)
	expected_set_names = set(lock.sets)
	for set_id in sorted(expected_set_names - actual_set_names):
		problems.append(f"Managed Dictionary Set directory {set_id!r} is missing")
	for set_id in sorted(actual_set_names - expected_set_names):
		problems.append(f"Unknown entry {set_id!r} exists under addon/dictionaries/sets")
	for set_id, set_config in lock.sets.items():
		set_directory = sets_root / set_id
		if not set_directory.exists():
			continue
		if not set_directory.is_dir():
			problems.append(f"Managed Dictionary Set entry {set_id!r} is not a directory")
			continue
		problems.extend(_verify_set(set_directory, set_config, lock.files[set_id]))
	return problems


def _github_json(url: str) -> Mapping[str, object]:
	request = urllib.request.Request(
		url,
		headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT},
	)
	with cast(BinaryIO, urllib.request.urlopen(request)) as response:
		payload = json.load(response)
	if not isinstance(payload, dict):
		raise VendoringError(f"GitHub returned an unexpected response for {url}.")
	return cast(dict[str, object], payload)


def _required_mapping(value: object, context: str) -> Mapping[str, object]:
	if not isinstance(value, dict):
		raise VendoringError(f"GitHub response is missing object {context!r}.")
	return cast(dict[str, object], value)


def _required_string(mapping: Mapping[str, object], key: str, context: str) -> str:
	value = mapping.get(key)
	if not isinstance(value, str):
		raise VendoringError(f"GitHub response is missing string {context}.{key}.")
	return value


def resolve_tag_commit(set_config: SetConfig) -> str:
	"""Resolve a GitHub tag ref, peeling annotated tags to a commit SHA."""

	repository = urllib.parse.quote(set_config.github_repository, safe="/")
	tag = urllib.parse.quote(set_config.source_version, safe="")
	url = f"https://api.github.com/repos/{repository}/git/ref/tags/{tag}"
	payload = _github_json(url)
	git_object = _required_mapping(payload.get("object"), "object")
	object_type = _required_string(git_object, "type", "object")
	sha = _required_string(git_object, "sha", "object")
	while object_type == "tag":
		payload = _github_json(f"https://api.github.com/repos/{repository}/git/tags/{sha}")
		git_object = _required_mapping(payload.get("object"), "object")
		object_type = _required_string(git_object, "type", "object")
		sha = _required_string(git_object, "sha", "object")
	if object_type != "commit":
		raise VendoringError(
			f"GitHub tag {set_config.source_version!r} resolves to unsupported object type {object_type!r}.",
		)
	return sha


def download_source_archive(set_config: SetConfig, destination: Path) -> None:
	"""Download a pinned GitHub source archive to *destination*."""

	repository = urllib.parse.quote(set_config.github_repository, safe="/")
	revision = urllib.parse.quote(set_config.source_revision, safe="")
	url = f"https://codeload.github.com/{repository}/zip/{revision}"
	request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
	with cast(BinaryIO, urllib.request.urlopen(request)) as response, destination.open("wb") as archive:
		shutil.copyfileobj(response, archive)


def extract_source_archive(archive_path: Path, destination: Path) -> Path:
	"""Extract a source archive with exactly one safe top-level directory."""

	with zipfile.ZipFile(archive_path) as archive:
		members = archive.infolist()
		roots: set[str] = set()
		casefold_paths: set[tuple[str, ...]] = set()
		for member in members:
			if "\\" in member.filename:
				raise VendoringError(f"Archive contains unsafe path {member.filename!r}.")
			member_path = PurePosixPath(member.filename)
			if member_path.is_absolute() or ".." in member_path.parts:
				raise VendoringError(f"Archive contains unsafe path {member.filename!r}.")
			if member_path.parts:
				roots.add(member_path.parts[0])
				casefold_path = tuple(part.casefold() for part in member_path.parts)
				if casefold_path in casefold_paths:
					raise VendoringError(
						f"Archive contains entries that collide case-insensitively at {member.filename!r}.",
					)
				casefold_paths.add(casefold_path)
		if len(roots) != 1:
			raise VendoringError("Source archive must contain exactly one top-level directory.")
		archive.extractall(destination)
	root = destination / next(iter(roots))
	if not root.is_dir():
		raise VendoringError("Source archive top-level entry is not a directory.")
	return root


def refresh(repo_root: Path, lock_path: Path, lock: SourceLock) -> None:
	"""Fetch, validate, and replace every set pinned by *lock*."""

	processed: dict[str, dict[str, bytes]] = {}
	warnings: list[str] = []
	with tempfile.TemporaryDirectory(prefix="edm-vendored-sets-") as temporary:
		temporary_root = Path(temporary)
		for set_id, set_config in lock.sets.items():
			resolved_revision = resolve_tag_commit(set_config)
			if resolved_revision != set_config.source_revision:
				raise VendoringError(
					f"Upstream tag {set_config.source_version!r} resolves to {resolved_revision}, but the "
					+ f"lock pins {set_config.source_revision}. The tag and revision disagree; update the "
					+ "lock deliberately before refreshing.",
				)
			archive_path = temporary_root / f"{set_id}.zip"
			extract_directory = temporary_root / set_id
			extract_directory.mkdir()
			download_source_archive(set_config, archive_path)
			upstream_root = extract_source_archive(archive_path, extract_directory)
			processed[set_id] = process_upstream_tree(upstream_root, set_config, warnings)
	for warning in warnings:
		print(f"WARNING: {warning}")
	write_vendored_sets(repo_root, lock_path, lock, processed)


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
		lock_path = repo_root / "dictionarySources.lock.ini"
		lock = load_lock(lock_path)
		if command == "refresh":
			refresh(repo_root, lock_path, lock)
			print(f"Refreshed {len(lock.sets)} vendored dictionary set(s).")
			return 0
		problems = verify_tree(repo_root, lock)
		if problems:
			for problem in problems:
				print(f"ERROR: {problem}")
			return 1
		file_count = sum(len(files) for files in lock.files.values())
		print(f"Verified {len(lock.sets)} vendored dictionary set(s) and {file_count} dictionary file(s).")
		return 0
	except (VendoringError, OSError, urllib.error.URLError, zipfile.BadZipFile) as error:
		print(f"ERROR: {error}")
		return 1


if __name__ == "__main__":
	raise SystemExit(main())
