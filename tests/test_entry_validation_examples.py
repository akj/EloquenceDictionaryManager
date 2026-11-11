"""Check the published entry-validation examples against the editor's validator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import NotRequired, TypedDict

import pytest

from ecidic import Entry, ValidationCode, WarningCode, entry_warnings, validate_entry

EXAMPLES_PATH = Path(__file__).resolve().parents[1] / "docs" / "entry-validation-examples.json"


class _Example(TypedDict):
	voice: str
	slot: str
	key: str
	value: str
	expected: str
	warning: NotRequired[str]
	note: NotRequired[str]


class _ExamplesFile(TypedDict):
	about: str
	reasons: dict[str, str]
	warnings: dict[str, str]
	examples: list[_Example]


EXAMPLES_FILE: _ExamplesFile = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))
EXAMPLES = EXAMPLES_FILE["examples"]


def _example_id(example: _Example) -> str:
	return f"{example['voice']}{example['slot']}:{example['key']!r}->{example['value']!r}"


def test_reasons_name_every_validation_code_and_nothing_else() -> None:
	assert set(EXAMPLES_FILE["reasons"]) == {code.value for code in ValidationCode}


def test_warnings_name_every_warning_code_and_nothing_else() -> None:
	assert set(EXAMPLES_FILE["warnings"]) == {code.value for code in WarningCode}


def test_every_reason_has_at_least_one_example() -> None:
	used = {example["expected"] for example in EXAMPLES}

	assert set(EXAMPLES_FILE["reasons"]) - used == set()


def test_every_warning_has_at_least_one_example() -> None:
	used = {example["warning"] for example in EXAMPLES if "warning" in example}

	assert set(EXAMPLES_FILE["warnings"]) - used == set()


@pytest.mark.parametrize("example", EXAMPLES, ids=_example_id)
def test_example_matches_validate_entry(example: _Example) -> None:
	assert set(example) - {"note", "warning"} == {"voice", "slot", "key", "value", "expected"}
	expected = example["expected"]
	assert expected == "valid" or expected in EXAMPLES_FILE["reasons"]
	warning = example.get("warning")
	assert warning is None or (expected == "valid" and warning in EXAMPLES_FILE["warnings"])
	entry = Entry(example["key"], example["value"])

	issues = validate_entry(entry, example["slot"], example["voice"])
	warnings = entry_warnings(entry, example["slot"], example["voice"])

	assert [issue.code.value for issue in issues] == ([] if expected == "valid" else [expected])
	assert [found.code.value for found in warnings] == ([] if warning is None else [warning])
