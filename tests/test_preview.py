from __future__ import annotations

import builtins
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import call, Mock

import pytest

from ecidic.preview import can_preview, play_new, PlayNew


EDITOR_PATH = (
	Path(__file__).resolve().parents[1]
	/ "addon"
	/ "globalPlugins"
	/ "eloquenceDictionaryManager"
	/ "editor.py"
)


def _module(name: str, **attributes: object) -> ModuleType:
	module = ModuleType(name)
	for attribute_name, value in attributes.items():
		setattr(module, attribute_name, value)
	return module


def _identity(message: str) -> str:
	return message


@pytest.fixture
def editor_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
	package_name = "_eloquence_dictionary_manager_preview_test"
	package = _module(package_name, CONFIG_SECTION="eloquenceDictionaryManager")
	package.__path__ = [str(EDITOR_PATH.parent)]
	monkeypatch.setitem(sys.modules, package_name, package)

	wx = _module("wx", Dialog=type("Dialog", (), {}))
	gui_helper = _module("gui.guiHelper")
	nvda_controls = _module(
		"gui.nvdaControls",
		_CheckListCtrl=type("_CheckListCtrl", (), {}),
		AutoWidthColumnListCtrl=type("AutoWidthColumnListCtrl", (), {}),
	)
	settings_dialogs = _module(
		"gui.settingsDialogs",
		SettingsDialog=type("SettingsDialog", (), {}),
	)
	gui = _module("gui", guiHelper=gui_helper)

	stub_modules = {
		"addonHandler": _module("addonHandler", initTranslation=lambda: None, AddonError=Exception),
		"config": _module("config"),
		"gui": gui,
		"gui.guiHelper": gui_helper,
		"gui.nvdaControls": nvda_controls,
		"gui.settingsDialogs": settings_dialogs,
		"logHandler": _module("logHandler", log=Mock()),
		"NVDAState": _module("NVDAState"),
		"speech": _module("speech", cancelSpeech=Mock()),
		"synthDriverHandler": _module("synthDriverHandler", getSynth=Mock()),
		"ui": _module("ui", message=Mock()),
		"wx": wx,
	}
	for name, module in stub_modules.items():
		monkeypatch.setitem(sys.modules, name, module)
	monkeypatch.setattr(builtins, "_", _identity, raising=False)

	module_name = f"{package_name}.editor"
	spec = importlib.util.spec_from_file_location(module_name, EDITOR_PATH)
	assert spec is not None and spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, module_name, module)
	spec.loader.exec_module(module)
	return module


@pytest.mark.parametrize(
	("synth_name", "expected"),
	[
		("eloquence", True),
		("openevv", True),
		("reloqC", False),
		(None, False),
		("", False),
		("espeak", False),
		("Eloquence", False),
		("OpenEVV", False),
	],
)
def test_can_preview(synth_name: str | None, expected: bool) -> None:
	assert can_preview(synth_name) is expected


def _synth(name: str, **attributes: object) -> SimpleNamespace:
	return SimpleNamespace(name=name, **attributes)


def _say_nothing(_pronunciation: str) -> None:
	pass


@pytest.mark.parametrize(
	("synth", "pronunciation", "expected"),
	[
		(None, "`[.1Ar.0min]", PlayNew.UNAVAILABLE),
		(_synth("espeak"), "plain", PlayNew.UNAVAILABLE),
		(
			_synth("espeak", previewEciPronunciation=_say_nothing),
			"`[.1Ar.0min]",
			PlayNew.PREVIEW_METHOD,
		),
		(
			_synth("eloquence", backquoteVoiceTags=False, previewEciPronunciation=_say_nothing),
			"`[.1Ar.0min]",
			PlayNew.PREVIEW_METHOD,
		),
		(_synth("eloquence", previewEciPronunciation="not callable"), "plain", PlayNew.SPEAK),
		(_synth("eloquence", backquoteVoiceTags=False), "`[.1Ar.0min]", PlayNew.NEEDS_VOICE_TAGS),
		(_synth("eloquence", backquoteVoiceTags=False), "em `0 box", PlayNew.NEEDS_VOICE_TAGS),
		(_synth("eloquence", backquoteVoiceTags=True), "`[.1Ar.0min]", PlayNew.SPEAK),
		(_synth("eloquence", backquoteVoiceTags=False), "junior grade", PlayNew.SPEAK),
		(_synth("eloquence", voiceTags=True), "`[.1Ar.0min]", PlayNew.NEEDS_VOICE_TAGS),
		(_synth("openevv", voiceTags=False), "`[.1Ar.0min]", PlayNew.NEEDS_VOICE_TAGS),
		(_synth("openevv", voiceTags=True), "`[.1Ar.0min]", PlayNew.SPEAK),
		(_synth("openevv", backquoteVoiceTags=True), "`[.1Ar.0min]", PlayNew.NEEDS_VOICE_TAGS),
		(_synth("openevv"), "`[.1Ar.0min]", PlayNew.NEEDS_VOICE_TAGS),
	],
)
def test_play_new_reads_the_synths_own_voice_tag_setting(
	synth: object,
	pronunciation: str,
	expected: PlayNew,
) -> None:
	assert play_new(synth, pronunciation) is expected


def _play_new_dialog(editor_module: ModuleType, pronunciation: str, *, slot: str = "MAIN") -> Mock:
	dialog = Mock()
	dialog._language = "enu"
	dialog._word_control.GetValue.return_value = "Armin"
	dialog._pronunciation_control.GetValue.return_value = pronunciation
	dialog._selectedSlot.return_value = getattr(editor_module.Slot, slot)
	return dialog


@pytest.mark.parametrize(
	("pronunciation", "message"),
	[
		("`p20000 Armin", "A backquote can only start a phonetic string"),
		("`[.1Ar.0min", "The phonetic string is not closed"),
		("   ", "A pronunciation is required."),
	],
)
def test_play_new_announces_an_invalid_pronunciation_and_speaks_nothing(
	editor_module: ModuleType,
	pronunciation: str,
	message: str,
) -> None:
	synth = Mock(name="synth", spec=["name", "speak", "backquoteVoiceTags", "previewEciPronunciation"])
	synth.name = "eloquence"
	synth.backquoteVoiceTags = True
	editor_module.synthDriverHandler.getSynth.return_value = synth

	editor_module.EntryDialog._onPlayNew(_play_new_dialog(editor_module, pronunciation), Mock())

	synth.speak.assert_not_called()
	synth.previewEciPronunciation.assert_not_called()
	editor_module.speech.cancelSpeech.assert_not_called()
	editor_module.ui.message.assert_called_once()
	assert editor_module.ui.message.call_args.args[0].startswith(message)


def test_play_new_ignores_word_problems_and_checks_the_pronunciation_without_a_word(
	editor_module: ModuleType,
) -> None:
	synth = Mock(name="synth", spec=["name", "speak", "backquoteVoiceTags"])
	synth.name = "eloquence"
	synth.backquoteVoiceTags = True
	editor_module.synthDriverHandler.getSynth.return_value = synth
	dialog = _play_new_dialog(editor_module, "`v1", slot="ROOT")
	dialog._word_control.GetValue.return_value = ""

	editor_module.EntryDialog._onPlayNew(dialog, Mock())

	synth.speak.assert_not_called()
	assert editor_module.ui.message.call_args.args[0].startswith("A backquote can only start")


def test_play_new_calls_the_synths_preview_method_with_the_stripped_pronunciation(
	editor_module: ModuleType,
) -> None:
	call_order = Mock()
	synth = Mock(name="synth", spec=["name", "speak", "backquoteVoiceTags", "previewEciPronunciation"])
	synth.name = "eloquence"
	synth.backquoteVoiceTags = False
	editor_module.speech.cancelSpeech.side_effect = call_order.cancelSpeech
	synth.previewEciPronunciation.side_effect = call_order.previewEciPronunciation
	editor_module.synthDriverHandler.getSynth.return_value = synth

	editor_module.EntryDialog._onPlayNew(_play_new_dialog(editor_module, " `[.1Ar.0min] "), Mock())

	assert call_order.mock_calls == [
		call.cancelSpeech(),
		call.previewEciPronunciation("`[.1Ar.0min]"),
	]
	synth.speak.assert_not_called()
	editor_module.ui.message.assert_not_called()


def test_play_new_explains_why_a_phonetic_pronunciation_cannot_play_with_voice_tags_off(
	editor_module: ModuleType,
) -> None:
	synth = Mock(name="synth", spec=["name", "speak", "voiceTags"])
	synth.name = "openevv"
	synth.voiceTags = False
	editor_module.synthDriverHandler.getSynth.return_value = synth

	editor_module.EntryDialog._onPlayNew(_play_new_dialog(editor_module, "`[.1Ar.0min]"), Mock())

	synth.speak.assert_not_called()
	editor_module.speech.cancelSpeech.assert_not_called()
	editor_module.ui.message.assert_called_once_with(
		"To hear pronunciations with phonetic strings or other backquote codes, turn on backquote "
		+ "voice tags in Voice settings.",
	)


@pytest.mark.parametrize(
	("voice_tags", "pronunciation"),
	[(True, "`[.1Ar.0min]"), (False, "are min")],
)
def test_play_new_speaks_when_the_synth_would_pass_the_pronunciation_through(
	editor_module: ModuleType,
	voice_tags: bool,
	pronunciation: str,
) -> None:
	synth = Mock(name="synth", spec=["name", "speak", "backquoteVoiceTags"])
	synth.name = "eloquence"
	synth.backquoteVoiceTags = voice_tags
	editor_module.synthDriverHandler.getSynth.return_value = synth

	editor_module.EntryDialog._onPlayNew(_play_new_dialog(editor_module, pronunciation), Mock())

	synth.speak.assert_called_once_with([pronunciation])
	editor_module.ui.message.assert_not_called()


def test_play_new_is_unavailable_with_another_synth(editor_module: ModuleType) -> None:
	synth = Mock(name="synth", spec=["name", "speak"])
	synth.name = "espeak"
	editor_module.synthDriverHandler.getSynth.return_value = synth

	editor_module.EntryDialog._onPlayNew(_play_new_dialog(editor_module, "are min"), Mock())

	synth.speak.assert_not_called()
	editor_module.ui.message.assert_called_once_with(
		"Preview unavailable: switch to Eloquence or OpenEVV to hear pronunciations.",
	)


def test_preview_does_not_cancel_speech_when_synth_cannot_preview(editor_module: ModuleType) -> None:
	synth = Mock(name="synth")
	synth.name = "espeak"
	editor_module.synthDriverHandler.getSynth.return_value = synth

	editor_module.EntryDialog._preview(object(), "test pronunciation")

	editor_module.speech.cancelSpeech.assert_not_called()
	synth.speak.assert_not_called()
	editor_module.ui.message.assert_called_once_with(
		"Preview unavailable: switch to Eloquence or OpenEVV to hear pronunciations.",
	)


@pytest.mark.parametrize("synth_name", ["eloquence", "openevv"])
def test_preview_cancels_speech_before_speaking_with_previewing_synth(
	editor_module: ModuleType,
	synth_name: str,
) -> None:
	call_order = Mock()
	synth = Mock(name="synth")
	synth.name = synth_name
	editor_module.speech.cancelSpeech.side_effect = call_order.cancelSpeech
	synth.speak.side_effect = call_order.speak
	editor_module.synthDriverHandler.getSynth.return_value = synth

	editor_module.EntryDialog._preview(object(), "test pronunciation")

	assert call_order.mock_calls == [
		call.cancelSpeech(),
		call.speak(["test pronunciation"]),
	]
	editor_module.ui.message.assert_not_called()


def _entry_dialog(editor_module: ModuleType, language: str, word: str, pronunciation: str) -> Mock:
	editor_module.wx.MessageBox = Mock()
	editor_module.wx.OK = 4
	editor_module.wx.ICON_WARNING = 256
	editor_module.wx.ID_OK = 5100
	dialog = Mock()
	dialog._language = language
	dialog._word_control.GetValue.return_value = word
	dialog._pronunciation_control.GetValue.return_value = pronunciation
	dialog._selectedSlot.return_value = editor_module.Slot.ABBREVIATION
	return dialog


def test_entry_dialog_refuses_an_entry_eloquence_would_never_use(editor_module: ModuleType) -> None:
	dialog = _entry_dialog(editor_module, "enu", "Lt.-Col.", "lieutenant colonel")

	editor_module.EntryDialog.onOk(dialog, Mock())

	editor_module.wx.MessageBox.assert_called_once_with(
		"Eloquence would never use this entry, because English abbreviations with a hyphen, slash "
		+ "or ampersand never match. Use an Exact word entry instead.",
		"Dictionary Entry Error",
		4 | 256,
		dialog,
	)
	dialog._word_control.SetFocus.assert_called_once_with()
	dialog.EndModal.assert_not_called()


def test_entry_dialog_saves_a_german_abbreviation_with_a_hyphen(editor_module: ModuleType) -> None:
	dialog = _entry_dialog(editor_module, "deu", "Dipl.-Ing.", "Diplomingenieur")

	editor_module.EntryDialog.onOk(dialog, Mock())

	editor_module.wx.MessageBox.assert_not_called()
	dialog.EndModal.assert_called_once_with(5100)
	assert dialog.entry == editor_module.Entry("Dipl.-Ing.", "Diplomingenieur")


def _entries_dialog(editor_module: ModuleType, overlay: object, selected: int) -> Any:
	Entry, Slot = editor_module.Entry, editor_module.Slot
	managed_set = editor_module.ManagedSet(
		id="github.example.set",
		name="Example Set",
		source_url="https://example.com/source",
		source_version="v2",
		source_revision="0123456789abcdef0123456789abcdef01234567",
		attribution="Example contributors",
		license="CC0-1.0",
		license_url="https://example.com/license",
		_entries={
			("enu", Slot.MAIN): (
				Entry("Apple", "apple"),
				Entry("GUI", "gooey"),
				Entry("Gui", "ghee"),
				Entry("Zulu", "zulu"),
			),
		},
	)
	dialog_class = editor_module.EloquenceDictionariesDialog
	dialog = dialog_class.__new__(dialog_class)
	dialog._managed_sets = (managed_set,)
	dialog._overlay = overlay
	dialog._views = {}
	dialog._rows = ()
	dialog._language_codes = ("enu",)
	dialog._show_filters = tuple(editor_module.ShowFilter)
	dialog._slot_labels = editor_module._slot_labels()
	dialog._language_choice = Mock()
	dialog._language_choice.GetSelection.return_value = 0
	dialog._set_choice = Mock()
	dialog._set_choice.GetSelection.return_value = 0
	dialog._filter_control = Mock()
	dialog._filter_control.GetValue.return_value = ""
	dialog._show_choice = Mock()
	dialog._show_choice.GetSelection.return_value = 0
	dialog._entry_list = Mock()
	dialog._entry_list.GetFirstSelected.return_value = selected
	dialog._remove_all_button = Mock()
	dialog.Layout = Mock()
	dialog._edit_button = Mock()
	dialog._set_details_button = Mock()
	dialog._remove_button = Mock()
	dialog._refresh_rows()
	return dialog


def test_removing_a_root_override_focuses_the_restored_main_entry(editor_module: ModuleType) -> None:
	Entry, Slot = editor_module.Entry, editor_module.Slot
	overlay = sys.modules[f"{editor_module.__package__}.ecidic.overlay"].PersonalOverlay.from_entries(
		[
			("enu", Slot.MAIN, Entry("Aardvark", "personal")),
			("enu", Slot.MAIN, Entry("Gui", "personal ghee")),
			("enu", Slot.ROOT, Entry("gui", "gee you eye")),
		],
	)
	dialog = _entries_dialog(editor_module, overlay, selected=3)
	assert [(row.word, row.slot, row.kind.value) for row in dialog._rows] == [
		("Aardvark", Slot.MAIN, "personal"),
		("Apple", Slot.MAIN, "managed"),
		("Gui", Slot.MAIN, "override"),
		("gui", Slot.ROOT, "override"),
		("Zulu", Slot.MAIN, "managed"),
	]

	dialog._onRemove(Mock())

	assert [(row.word, row.slot, row.kind.value) for row in dialog._rows] == [
		("Aardvark", Slot.MAIN, "personal"),
		("Apple", Slot.MAIN, "managed"),
		("GUI", Slot.MAIN, "managed"),
		("Gui", Slot.MAIN, "override"),
		("Zulu", Slot.MAIN, "managed"),
	]
	assert dialog._entry_list.Focus.call_args_list[-1] == call(2)
	assert dialog._entry_list.Select.call_args_list[-1] == call(2)
	dialog._entry_list.SetFocus.assert_called_once_with()
