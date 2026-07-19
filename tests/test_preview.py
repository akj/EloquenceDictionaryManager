from __future__ import annotations

import pytest

from ecidic.preview import is_eloquence_active


def test_eloquence_is_active() -> None:
	assert is_eloquence_active("eloquence")


@pytest.mark.parametrize("synth_name", [None, "", "espeak", "Eloquence"])
def test_other_synth_names_are_not_active(synth_name: str | None) -> None:
	assert not is_eloquence_active(synth_name)
