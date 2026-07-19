"""Global plugin entry point for Eloquence Dictionary Manager."""

from typing import cast, override

import addonHandler
import globalPluginHandler
import globalVars
import gui
from gui import blockAction
import inputCore
from scriptHandler import script
import wx


# Keep NVDA's translator so the add-on can recognize a translated core menu label.
_nvdaGettext = _
addonHandler.initTranslation()

_SPEECH_DICTIONARIES_MENU_LABEL = _nvdaGettext("Speech &dictionaries")


def _normalizeMenuLabel(label: str) -> str:
	"""Normalize a wx menu label for comparison across mnemonic placement."""
	return label.replace("&", "").strip().casefold()


def _findSpeechDictionariesInsertionPosition(menu: wx.Menu) -> int | None:
	"""Return the position immediately after NVDA's speech dictionaries submenu."""
	expectedLabel = _normalizeMenuLabel(_SPEECH_DICTIONARIES_MENU_LABEL)
	items = cast(list[wx.MenuItem], menu.GetMenuItems())  # pyright: ignore[reportUnknownMemberType]
	for position, item in enumerate(items):
		if cast(wx.Menu | None, item.GetSubMenu()) is None:
			continue
		if _normalizeMenuLabel(item.GetItemLabelText()) == expectedLabel:
			return position + 1
	return None


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	# Translators: Script category for Eloquence Dictionary Manager commands in Input Gestures.
	scriptCategory = _("Eloquence Dictionary Manager")

	def __init__(self):
		super().__init__()
		self._preferencesMenu: wx.Menu | None = None
		self._menuItem: wx.MenuItem | None = None
		if globalVars.appArgs.secure:
			return

		mainFrame = gui.mainFrame
		if mainFrame is None:
			return
		self._preferencesMenu = mainFrame.sysTrayIcon.preferencesMenu
		self._menuItem = wx.MenuItem(
			self._preferencesMenu,
			wx.ID_ANY,
			# Translators: Label of the item in NVDA's Preferences menu that opens the dictionary editor.
			_("Eloquence &dictionaries..."),
		)
		insertionPosition = _findSpeechDictionariesInsertionPosition(self._preferencesMenu)
		# Assigning to "_" would shadow the module's gettext lookup, so use a throwaway name.
		if insertionPosition is None:
			_insertedItem = self._preferencesMenu.Append(self._menuItem)
		else:
			_insertedItem = self._preferencesMenu.Insert(insertionPosition, self._menuItem)
		mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self._openDialog, self._menuItem)  # pyright: ignore[reportUnknownMemberType]

	@override
	def terminate(self) -> None:
		super().terminate()
		if self._preferencesMenu is None or self._menuItem is None:
			return
		try:
			_removedItem = self._preferencesMenu.Remove(self._menuItem)
		except (RuntimeError, AttributeError):
			# The menu may already have been destroyed while NVDA is shutting down.
			pass
		self._menuItem = None
		self._preferencesMenu = None

	@blockAction.when(blockAction.Context.SECURE_MODE)
	def _openDialog(self, _event: wx.CommandEvent | None = None) -> None:
		from .editor import EloquenceDictionariesDialog

		mainFrame = gui.mainFrame
		if mainFrame is None:
			return
		mainFrame.popupSettingsDialog(EloquenceDictionariesDialog)  # pyright: ignore[reportUnknownMemberType]

	@script(
		# Translators: Description of the command that opens the Eloquence dictionary editor.
		description=_("Opens the Eloquence Dictionaries dialog."),
	)
	@blockAction.when(blockAction.Context.SECURE_MODE)
	def script_openEloquenceDictionaries(self, _gesture: inputCore.InputGesture) -> None:
		wx.CallAfter(self._openDialog)
