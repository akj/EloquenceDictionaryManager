from __future__ import annotations

import builtins
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import call, Mock

import pytest

from ecidic.preview import is_eloquence_active


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


def test_eloquence_is_active() -> None:
	assert is_eloquence_active("eloquence")


@pytest.mark.parametrize("synth_name", [None, "", "espeak", "Eloquence"])
def test_other_synth_names_are_not_active(synth_name: str | None) -> None:
	assert not is_eloquence_active(synth_name)


def test_preview_does_not_cancel_speech_when_eloquence_is_inactive(editor_module: ModuleType) -> None:
	synth = Mock(name="synth")
	synth.name = "espeak"
	editor_module.synthDriverHandler.getSynth.return_value = synth

	editor_module.EntryDialog._preview(object(), "test pronunciation")

	editor_module.speech.cancelSpeech.assert_not_called()
	synth.speak.assert_not_called()
	editor_module.ui.message.assert_called_once_with(
		"Preview unavailable: Eloquence is not the active synthesizer.",
	)


def test_preview_cancels_speech_before_speaking_with_eloquence(editor_module: ModuleType) -> None:
	call_order = Mock()
	synth = Mock(name="synth")
	synth.name = "eloquence"
	editor_module.speech.cancelSpeech.side_effect = call_order.cancelSpeech
	synth.speak.side_effect = call_order.speak
	editor_module.synthDriverHandler.getSynth.return_value = synth

	editor_module.EntryDialog._preview(object(), "test pronunciation")

	assert call_order.mock_calls == [
		call.cancelSpeech(),
		call.speak(["test pronunciation"]),
	]
	editor_module.ui.message.assert_not_called()
