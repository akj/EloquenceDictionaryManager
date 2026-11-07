"""NVDA-independent preview availability logic."""

from __future__ import annotations

#: NVDA synth driver names whose engines read EDM's managed sets and personal overlay.
PREVIEW_SYNTHS = frozenset({"eloquence", "openevv"})


def can_preview(synth_name: str | None) -> bool:
	"""Return whether the named synthesizer speaks with EDM's entries applied."""
	return synth_name in PREVIEW_SYNTHS
