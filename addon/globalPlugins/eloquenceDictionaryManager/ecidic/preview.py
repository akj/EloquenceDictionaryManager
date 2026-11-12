"""NVDA-independent preview availability logic."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

#: NVDA synth driver names whose engines read EDM's managed sets and personal overlay, each
#: mapped to its driver setting that lets backquote codes in spoken text reach the engine.
#: Both drivers turn every backquote into a space while that setting is off.
PREVIEW_SYNTHS: Mapping[str, str] = {
	"eloquence": "backquoteVoiceTags",
	"openevv": "voiceTags",
}

#: The optional synth driver method that speaks one dictionary pronunciation once,
#: honouring the backquote codes a valid entry may carry, whatever the synth's settings.
PREVIEW_METHOD = "previewEciPronunciation"


class PlayNew(Enum):
	"""How Play new previews a valid pronunciation with the loaded synth."""

	PREVIEW_METHOD = "previewMethod"
	"""Call the synth's ``previewEciPronunciation`` method."""
	SPEAK = "speak"
	"""Speak the pronunciation as ordinary text."""
	NEEDS_VOICE_TAGS = "needsVoiceTags"
	"""Speak nothing: the synth would turn the pronunciation's backquotes into spaces."""
	UNAVAILABLE = "unavailable"
	"""Speak nothing: the synth does not read EDM's entries."""


def can_preview(synth_name: str | None) -> bool:
	"""Return whether the named synthesizer speaks with EDM's entries applied."""
	return synth_name in PREVIEW_SYNTHS


def play_new(synth: object | None, pronunciation: str) -> PlayNew:
	"""Decide how to preview a valid *pronunciation* with the loaded *synth*.

	EDM reads a synth's voice tag setting and never changes it.
	"""

	if synth is None:
		return PlayNew.UNAVAILABLE
	if callable(getattr(synth, PREVIEW_METHOD, None)):
		return PlayNew.PREVIEW_METHOD
	setting = PREVIEW_SYNTHS.get(getattr(synth, "name", None) or "")
	if setting is None:
		return PlayNew.UNAVAILABLE
	if "`" in pronunciation and not getattr(synth, setting, False):
		return PlayNew.NEEDS_VOICE_TAGS
	return PlayNew.SPEAK
