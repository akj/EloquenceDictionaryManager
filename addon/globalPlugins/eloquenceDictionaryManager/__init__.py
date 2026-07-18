"""Global plugin entry point for Eloquence Dictionary Manager."""

import addonHandler
import globalPluginHandler
import globalVars
import gui
from gui import blockAction, guiHelper
from gui.dpiScalingHelper import DpiScalingHelperMixinWithoutInit
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
	for position, item in enumerate(menu.GetMenuItems()):
		if item.GetSubMenu() is None:
			continue
		if _normalizeMenuLabel(item.GetItemLabelText()) == expectedLabel:
			return position + 1
	return None


class EloquenceDictionariesDialog(
	DpiScalingHelperMixinWithoutInit,
	wx.Dialog,
):
	"""Placeholder for the standalone Eloquence dictionary editor."""

	def __init__(self, parent: wx.Window):
		super().__init__(
			parent,
			# Translators: Title of the Eloquence dictionary editor dialog.
			title=_("Eloquence Dictionaries"),
			style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX,
		)

		mainSizer = wx.BoxSizer(wx.VERTICAL)
		sizerHelper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
		sizerHelper.addItem(
			wx.StaticText(
				self,
				# Translators: Placeholder text in the Eloquence dictionary editor dialog.
				label=_("This is a placeholder for the Eloquence dictionary editor."),
			),
		)
		closeButton = wx.Button(
			self,
			wx.ID_CLOSE,
			# Translators: Label of the button that closes the Eloquence dictionary editor dialog.
			label=_("&Close"),
		)
		closeButton.Bind(wx.EVT_BUTTON, self._onClose)
		sizerHelper.addDialogDismissButtons(closeButton, separated=True)

		mainSizer.Add(
			sizerHelper.sizer,
			proportion=1,
			flag=wx.EXPAND | wx.ALL,
			border=guiHelper.BORDER_FOR_DIALOGS,
		)
		self.SetSizer(mainSizer)
		mainSizer.Fit(self)
		self.SetMinSize(self.scaleSize((420, 180)))
		self.SetSize(self.scaleSize((560, 320)))
		self.CentreOnParent()
		closeButton.SetFocus()

	def _onClose(self, _event: wx.CommandEvent) -> None:
		self.EndModal(wx.ID_CLOSE)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	# Translators: Script category for Eloquence Dictionary Manager commands in Input Gestures.
	scriptCategory = _("Eloquence Dictionary Manager")

	def __init__(self):
		super().__init__()
		self._preferencesMenu: wx.Menu | None = None
		self._menuItem: wx.MenuItem | None = None
		if globalVars.appArgs.secure:
			return

		self._preferencesMenu = gui.mainFrame.sysTrayIcon.preferencesMenu
		self._menuItem = wx.MenuItem(
			self._preferencesMenu,
			wx.ID_ANY,
			# Translators: Label of the item in NVDA's Preferences menu that opens the dictionary editor.
			_("Eloquence &dictionaries..."),
		)
		insertionPosition = _findSpeechDictionariesInsertionPosition(self._preferencesMenu)
		if insertionPosition is None:
			self._preferencesMenu.Append(self._menuItem)
		else:
			self._preferencesMenu.Insert(insertionPosition, self._menuItem)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self._openDialog, self._menuItem)

	def terminate(self) -> None:
		super().terminate()
		if self._preferencesMenu is None or self._menuItem is None:
			return
		try:
			self._preferencesMenu.Remove(self._menuItem)
		except (RuntimeError, AttributeError):
			# The menu may already have been destroyed while NVDA is shutting down.
			pass
		self._menuItem = None
		self._preferencesMenu = None

	@blockAction.when(blockAction.Context.SECURE_MODE)
	def _openDialog(self, _event: wx.CommandEvent | None = None) -> None:
		gui.mainFrame.prePopup()
		dialog: EloquenceDictionariesDialog | None = None
		try:
			dialog = EloquenceDictionariesDialog(gui.mainFrame)
			dialog.ShowModal()
		finally:
			if dialog is not None:
				dialog.Destroy()
			gui.mainFrame.postPopup()

	@script(
		# Translators: Description of the command that opens the Eloquence dictionary editor.
		description=_("Opens the Eloquence Dictionaries dialog."),
	)
	@blockAction.when(blockAction.Context.SECURE_MODE)
	def script_openEloquenceDictionaries(self, _gesture: inputCore.InputGesture) -> None:
		wx.CallAfter(self._openDialog)
