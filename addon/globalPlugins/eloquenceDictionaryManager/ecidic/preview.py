"""NVDA-independent preview availability logic."""

from __future__ import annotations


def is_eloquence_active(synth_name: str | None) -> bool:
	"""Return whether the active synthesizer is Eloquence."""
	return synth_name == "eloquence"
