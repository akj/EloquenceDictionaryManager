"""Effective-entry editor dialog for Eloquence dictionaries."""

# The wx stubs leave many member types partially unknown, and wx GUI construction
# discards returned sizer items pervasively, so relax those two rules file-wide.
# pyright: reportUnknownMemberType=false, reportUnusedCallResult=false

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast, override

import addonHandler
from gui import guiHelper
from gui.nvdaControls import AutoWidthColumnListCtrl
from gui.settingsDialogs import SettingsDialog
from logHandler import log
import NVDAState
import speech
import synthDriverHandler
import ui
import wx

from .ecidic.artifact import export_edm_dict_artifact
from .ecidic.effective import EffectiveRow, EffectiveView, RowKind, ShowFilter
from .ecidic.languages import LANGUAGES
from .ecidic.model import Entry, Slot
from .ecidic.overlay import load_personal_overlay, save_personal_overlay
from .ecidic.parsing import DictionaryEncodingError, key_identity
from .ecidic.preview import is_eloquence_active
from .ecidic.sets import ManagedSet, discover_managed_sets
from .ecidic.validation import EntryValidationError, Field, normalize_entry, validate_entry


addonHandler.initTranslation()


def _language_display_names() -> dict[str, str]:
	return {
		# Translators: Display name for the American English Eloquence voice.
		"enu": _("English (US)"),
		# Translators: Display name for the British English Eloquence voice.
		"eng": _("English (UK)"),
		# Translators: Display name for the Castilian Spanish Eloquence voice.
		"esp": _("Spanish (Castilian)"),
		# Translators: Display name for the Latin American Spanish Eloquence voice.
		"esm": _("Spanish (Latin American)"),
		# Translators: Display name for the French Eloquence voice.
		"fra": _("French"),
		# Translators: Display name for the Canadian French Eloquence voice.
		"frc": _("French (Canadian)"),
		# Translators: Display name for the German Eloquence voice.
		"deu": _("German"),
		# Translators: Display name for the Italian Eloquence voice.
		"ita": _("Italian"),
		# Translators: Display name for the Brazilian Portuguese Eloquence voice.
		"ptb": _("Portuguese (Brazilian)"),
		# Translators: Display name for the Finnish Eloquence voice.
		"fin": _("Finnish"),
	}


def _slot_labels() -> dict[Slot, str]:
	return {
		# Translators: Type column value for an exact-word dictionary entry.
		Slot.MAIN: _("Exact word"),
		# Translators: Type column value for a word-root dictionary entry.
		Slot.ROOT: _("Word root"),
		# Translators: Type column value for an abbreviation dictionary entry.
		Slot.ABBREVIATION: _("Abbreviation"),
	}


def _entry_rules() -> dict[Slot, str]:
	return {
		Slot.MAIN: _(
			# Translators: Rules shown for an exact-word dictionary entry.
			'Matches the word exactly as written — capitalization counts, so "NASA" and "nasa" are separate entries. The word cannot contain spaces or end with punctuation. The pronunciation may be words, phonetic strings like `[.1kwi.0nwa], or emphasis codes `0 (flat) through `4 (strongest).',
		),
		Slot.ROOT: _(
			# Translators: Rules shown for a word-root dictionary entry.
			'Matches a word and all of its forms — "figure" also covers figures, figured, figuring — ignoring capitalization. Roots are stored in lowercase and can contain only letters. The pronunciation must be a single word or one phonetic string (`[...]).',
		),
		Slot.ABBREVIATION: _(
			# Translators: Rules shown for an abbreviation dictionary entry.
			'Matches an abbreviation written with letters and periods — capitalization counts. A trailing period is meaningful: "approx." matches only "approx.", while "approx" matches both "approx" and "approx.". The expansion must be plain words.',
		),
	}


_SLOT_ORDER = (Slot.MAIN, Slot.ROOT, Slot.ABBREVIATION)


def _available_provider_paths() -> tuple[Path, ...]:
	return tuple(
		Path(addon.path) for addon in addonHandler.getAvailableAddons() if not addon.isPendingInstall
	)


def _currentAddonVersion() -> str:
	"""Return this add-on's installed version, with a defensive development fallback."""

	try:
		version = cast(object, addonHandler.getCodeAddon().manifest["version"])
	except (addonHandler.AddonError, AttributeError, KeyError, TypeError):
		log.debugWarning(
			"Eloquence Dictionary Manager could not determine its installed version; using 0.0.0",
			exc_info=True,
		)
		return "0.0.0"
	if not isinstance(version, str) or not version:
		log.debugWarning(
			"Eloquence Dictionary Manager has no usable installed version; using 0.0.0",
		)
		return "0.0.0"
	return version


class EntryDialog(wx.Dialog):
	"""Modal editor for one Personal Dictionary Overlay entry."""

	def __init__(
		self,
		parent: wx.Window,
		title: str,
		language: str,
		*,
		slot: Slot = Slot.MAIN,
		entry: Entry | None = None,
		lock_type: bool = False,
		lock_word: bool = False,
	):
		super().__init__(parent, title=title)
		self._language = language
		self.entry: Entry | None = None
		self.slot = slot
		initial_entry = entry or Entry("", "")

		outer_sizer = wx.BoxSizer(wx.VERTICAL)
		sizer_helper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
		self._word_control = sizer_helper.addLabeledControl(
			# Translators: Label for the dictionary entry word field.
			_("&Word:"),
			wx.TextCtrl,
			value=initial_entry.key,
			size=(300, -1),
		)
		self._word_control.Enable(not lock_word)
		self._pronunciation_control = sizer_helper.addLabeledControl(
			# Translators: Label for the dictionary entry pronunciation field.
			_("&Pronunciation:"),
			wx.TextCtrl,
			value=initial_entry.value,
			size=(300, -1),
		)
		self._type_control = wx.RadioBox(
			self,
			# Translators: Label for choosing the dictionary entry type.
			label=_("&Type"),
			choices=[
				# Translators: Entry type choice for an exact-word dictionary entry.
				_("Exact word"),
				# Translators: Entry type choice for a word-root dictionary entry.
				_("Word root (matches all word forms)"),
				# Translators: Entry type choice for an abbreviation dictionary entry.
				_("Abbreviation"),
			],
			majorDimension=1,
			style=wx.RA_SPECIFY_COLS,
		)
		self._type_control.SetSelection(_SLOT_ORDER.index(slot))
		self._type_control.Enable(not lock_type)
		self._type_control.Bind(wx.EVT_RADIOBOX, self._onTypeChanged)
		sizer_helper.addItem(self._type_control)
		sizer_helper.addItem(
			wx.StaticText(
				self,
				# Translators: Label for the read-only dictionary entry rules text.
				label=_("Rule&s:"),
			),
		)
		self._rules_control = wx.TextCtrl(
			self,
			value=_entry_rules()[slot],
			size=cast("wx.Size", (440, 80)),
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_BESTWRAP,
		)
		sizer_helper.addItem(self._rules_control, flag=wx.EXPAND)

		preview_button_helper = guiHelper.ButtonHelper(orientation=wx.HORIZONTAL)
		self._play_current_button = preview_button_helper.addButton(
			parent=self,
			# Translators: Button for previewing how Eloquence currently speaks the word.
			label=_("Play &current"),
		)
		self._play_current_button.Bind(wx.EVT_BUTTON, self._onPlayCurrent)
		self._play_new_button = preview_button_helper.addButton(
			parent=self,
			# Translators: Button for previewing the pronunciation currently entered in the dialog.
			label=_("Play &new"),
		)
		self._play_new_button.Bind(wx.EVT_BUTTON, self._onPlayNew)
		sizer_helper.addItem(preview_button_helper)

		outer_sizer.Add(
			sizer_helper.sizer,
			proportion=1,
			flag=wx.EXPAND | wx.ALL,
			border=guiHelper.BORDER_FOR_DIALOGS,
		)
		outer_sizer.Add(wx.StaticLine(self), flag=wx.EXPAND)
		outer_sizer.Add(
			self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL),
			flag=wx.EXPAND | wx.ALL,
			border=guiHelper.BORDER_FOR_DIALOGS,
		)
		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
		self.SetSizerAndFit(outer_sizer)
		self.CentreOnParent()
		self._word_control.SetFocus()

	def _selectedSlot(self) -> Slot:
		return _SLOT_ORDER[self._type_control.GetSelection()]

	def _onTypeChanged(self, _event: wx.CommandEvent) -> None:
		self._rules_control.SetValue(_entry_rules()[self._selectedSlot()])

	def _preview(self, pronunciation: str) -> None:
		speech.cancelSpeech()
		synth = synthDriverHandler.getSynth()
		if synth is not None and is_eloquence_active(synth.name):
			synth.speak([pronunciation])
			return
		ui.message(
			# Translators: Message announced when a pronunciation preview cannot use Eloquence.
			_("Preview unavailable: Eloquence is not the active synthesizer."),
		)

	def _onPlayCurrent(self, _event: wx.CommandEvent) -> None:
		self._preview(self._word_control.GetValue())

	def _onPlayNew(self, _event: wx.CommandEvent) -> None:
		self._preview(self._pronunciation_control.GetValue())

	def onOk(self, _event: wx.CommandEvent) -> None:
		entry = Entry(
			key=self._word_control.GetValue().strip(),
			value=self._pronunciation_control.GetValue().strip(),
		)
		slot = self._selectedSlot()
		issues = validate_entry(entry, slot, self._language)
		if issues:
			issue = issues[0]
			wx.MessageBox(
				issue.message,
				# Translators: Title of a validation warning in the dictionary entry dialog.
				_("Dictionary Entry Error"),
				wx.OK | wx.ICON_WARNING,
				self,
			)
			if issue.field is Field.KEY:
				self._word_control.SetFocus()
			else:
				self._pronunciation_control.SetFocus()
			return
		self.entry = normalize_entry(entry, slot)
		self.slot = slot
		self.EndModal(wx.ID_OK)


class SetDetailsDialog(wx.Dialog):
	"""Read-only provenance details for one Managed Dictionary Set."""

	def __init__(self, parent: wx.Window, managed_set: ManagedSet):
		# Translators: Title of the dialog showing Managed Dictionary Set provenance details.
		super().__init__(parent, title=_("Managed Dictionary Set Details"))

		outer_sizer = wx.BoxSizer(wx.VERTICAL)
		sizer_helper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
		self._name_control = sizer_helper.addLabeledControl(
			# Translators: Label for the Managed Dictionary Set name.
			_("&Name:"),
			wx.TextCtrl,
			value=managed_set.name,
			size=cast("wx.Size", (440, -1)),
			style=wx.TE_READONLY,
		)
		sizer_helper.addLabeledControl(
			# Translators: Label for the Managed Dictionary Set attribution or legal notice.
			_("&Attribution:"),
			wx.TextCtrl,
			value=managed_set.attribution,
			size=cast("wx.Size", (440, 80)),
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_BESTWRAP,
		)
		sizer_helper.addLabeledControl(
			# Translators: Label for the Managed Dictionary Set source URL.
			_("Source &URL:"),
			wx.TextCtrl,
			value=managed_set.source_url,
			size=cast("wx.Size", (440, -1)),
			style=wx.TE_READONLY,
		)
		sizer_helper.addLabeledControl(
			# Translators: Label for the Managed Dictionary Set license identifier.
			_("&License:"),
			wx.TextCtrl,
			value=managed_set.license,
			size=cast("wx.Size", (440, -1)),
			style=wx.TE_READONLY,
		)
		sizer_helper.addLabeledControl(
			# Translators: Label for the Managed Dictionary Set license URL.
			_("L&icense URL:"),
			wx.TextCtrl,
			value=managed_set.license_url,
			size=cast("wx.Size", (440, -1)),
			style=wx.TE_READONLY,
		)
		sizer_helper.addLabeledControl(
			# Translators: Label for the Managed Dictionary Set source version.
			_("Source &version:"),
			wx.TextCtrl,
			value=managed_set.source_version,
			size=cast("wx.Size", (440, -1)),
			style=wx.TE_READONLY,
		)
		sizer_helper.addLabeledControl(
			# Translators: Label for the full Managed Dictionary Set source revision.
			_("Source &revision:"),
			wx.TextCtrl,
			value=managed_set.source_revision,
			size=cast("wx.Size", (440, -1)),
			style=wx.TE_READONLY,
		)

		outer_sizer.Add(
			sizer_helper.sizer,
			proportion=1,
			flag=wx.EXPAND | wx.ALL,
			border=guiHelper.BORDER_FOR_DIALOGS,
		)
		outer_sizer.Add(wx.StaticLine(self), flag=wx.EXPAND)
		outer_sizer.Add(
			self.CreateStdDialogButtonSizer(wx.OK),
			flag=wx.EXPAND | wx.ALL,
			border=guiHelper.BORDER_FOR_DIALOGS,
		)
		self.SetSizerAndFit(outer_sizer)
		self.CentreOnParent()
		self._name_control.SetFocus()


class ExportScopeDialog(wx.Dialog):
	"""Modal chooser for the language scope of a Personal Dictionary Overlay export."""

	def __init__(self, parent: wx.Window):
		super().__init__(
			parent,
			# Translators: Title of the dialog for choosing which languages to export.
			title=_("Export Dictionary Entries"),
		)
		outer_sizer = wx.BoxSizer(wx.VERTICAL)
		self._scope_control = wx.RadioBox(
			self,
			# Translators: Label for choosing the language scope of a dictionary export.
			label=_("Export &scope"),
			choices=[
				# Translators: Export-scope choice that includes only the language currently shown in the editor.
				_("Shown language only"),
				# Translators: Export-scope choice that includes personal entries from every language.
				_("All languages"),
			],
			majorDimension=1,
			style=wx.RA_SPECIFY_COLS,
		)
		self._scope_control.SetSelection(0)
		outer_sizer.Add(
			self._scope_control,
			flag=wx.EXPAND | wx.ALL,
			border=guiHelper.BORDER_FOR_DIALOGS,
		)
		outer_sizer.Add(wx.StaticLine(self), flag=wx.EXPAND)
		outer_sizer.Add(
			self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL),
			flag=wx.EXPAND | wx.ALL,
			border=guiHelper.BORDER_FOR_DIALOGS,
		)
		self.SetSizerAndFit(outer_sizer)
		self.CentreOnParent()
		self._scope_control.SetFocus()

	@property
	def all_languages(self) -> bool:
		"""Whether the user selected the all-languages scope."""

		return self._scope_control.GetSelection() == 1


class EloquenceDictionariesDialog(SettingsDialog):
	"""Standalone editor for effective and personal pronunciation entries."""

	# Translators: Title of the Eloquence dictionary entries editor.
	title = _("Eloquence Dictionary Entries")

	def __init__(self, parent: wx.Window):
		managed_sets, discovery_diagnostics = discover_managed_sets(_available_provider_paths())
		for diagnostic in discovery_diagnostics:
			log.debugWarning(
				"Eloquence Dictionary Manager ignored %s: %s",
				diagnostic.path,
				diagnostic.reason,
			)
		self._managed_sets = tuple(sorted(managed_sets, key=lambda item: item.name.casefold()))
		self._overlay_directory = Path(NVDAState.WritePaths.configDir) / "eciDictionaries" / "personal"
		self._overlay, overlay_diagnostics = load_personal_overlay(self._overlay_directory)
		for diagnostic in overlay_diagnostics:
			log.warning(
				"Eloquence Dictionary Manager ignored Personal Dictionary Overlay file %s: %s",
				diagnostic.path,
				diagnostic.reason,
			)
		self._views: dict[tuple[str, str | None], EffectiveView] = {}
		self._rows: tuple[EffectiveRow, ...] = ()
		self._language_codes: tuple[str, ...] = ()
		self._show_filters = (
			ShowFilter.ALL,
			ShowFilter.PERSONAL,
			ShowFilter.OVERRIDES,
			ShowFilter.MANAGED,
		)
		self._slot_labels = _slot_labels()
		super().__init__(parent, resizeable=True)
		self.SetSize(cast("wx.Size", self.scaleSize((760, 560))))
		self.CentreOnScreen()

	@override
	def makeSettings(self, sizer: wx.BoxSizer) -> None:
		sizer_helper = guiHelper.BoxSizerHelper(self, sizer=sizer)

		top_row = wx.BoxSizer(wx.HORIZONTAL)
		top_row.Add(
			wx.StaticText(
				self,
				# Translators: Label for selecting an Eloquence dictionary language.
				label=_("&Language:"),
			),
			flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
			border=guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL,
		)
		language_names = _language_display_names()
		language_choices = sorted(
			((code, language_names[code]) for code in LANGUAGES),
			key=lambda item: item[1].casefold(),
		)
		self._language_codes = tuple(code for code, _name in language_choices)
		self._language_choice = wx.Choice(self, choices=[name for _code, name in language_choices])
		self._language_choice.SetSelection(self._language_codes.index(self._defaultLanguage()))
		self._language_choice.Bind(wx.EVT_CHOICE, self._onViewChanged)
		top_row.Add(
			self._language_choice,
			flag=wx.RIGHT,
			border=guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL * 3,
		)

		top_row.Add(
			wx.StaticText(
				self,
				# Translators: Label for choosing the Managed Dictionary Set to view.
				label=_("Managed &set:"),
			),
			flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
			border=guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL,
		)
		set_choices = [
			f"{managed_set.name} ({managed_set.source_version})" for managed_set in self._managed_sets
		]
		# Translators: Managed Dictionary Set choice that displays only Personal Dictionary Overlay entries.
		set_choices.append(_("None (personal entries only)"))
		self._set_choice = wx.Choice(self, choices=set_choices)
		self._set_choice.SetSelection(0 if self._managed_sets else len(set_choices) - 1)
		self._set_choice.Bind(wx.EVT_CHOICE, self._onViewChanged)
		top_row.Add(self._set_choice)
		sizer_helper.addItem(top_row)

		sizer_helper.addItem(
			wx.StaticText(
				self,
				label=_(
					# Translators: Explains that this dialog's Managed Dictionary Set choice is only a viewer.
					"Viewing only — the set your synthesizer uses is chosen in the synthesizer's settings.",
				),
			),
			flag=wx.BOTTOM,
			border=guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS,
		)

		filter_row = wx.BoxSizer(wx.HORIZONTAL)
		filter_row.Add(
			wx.StaticText(
				self,
				# Translators: Label for filtering the dictionary entry list.
				label=_("&Filter by:"),
			),
			flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
			border=guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL,
		)
		self._filter_control = wx.TextCtrl(self, size=cast("wx.Size", self.scaleSize((190, -1))))
		self._filter_control.Bind(wx.EVT_TEXT, self._onFilterChanged)
		filter_row.Add(
			self._filter_control,
			flag=wx.RIGHT,
			border=guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL * 3,
		)
		filter_row.Add(
			wx.StaticText(
				self,
				# Translators: Label for selecting which provenance categories the entry list shows.
				label=_("Sho&w:"),
			),
			flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
			border=guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL,
		)
		self._show_choice = wx.Choice(
			self,
			choices=[
				# Translators: Show-filter choice that includes every effective entry.
				_("All entries"),
				# Translators: Show-filter choice for personal-only and override entries.
				_("Personal only"),
				# Translators: Show-filter choice for personal entries that override managed entries.
				_("Personal overrides only"),
				# Translators: Show-filter choice for entries from the selected Managed Dictionary Set.
				_("Managed only"),
			],
		)
		self._show_choice.SetSelection(0)
		self._show_choice.Bind(wx.EVT_CHOICE, self._onFilterChanged)
		filter_row.Add(self._show_choice)
		sizer_helper.addItem(
			filter_row,
			flag=wx.BOTTOM,
			border=guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS,
		)

		sizer_helper.addItem(
			wx.StaticText(
				self,
				# Translators: Label for the virtual list of effective dictionary entries.
				label=_("Dictionary &entries"),
			),
		)
		self._entry_list = AutoWidthColumnListCtrl(
			self,
			autoSizeColumn="LAST",
			itemTextCallable=self._getListItemText,
			style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_VIRTUAL,
		)
		self._entry_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._onSelectionChanged)
		self._entry_list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self._onSelectionChanged)
		# Translators: Column header for the dictionary entry key.
		self._entry_list.AppendColumn(_("Word"), width=cast(int, self.scaleSize(145)))
		# Translators: Column header for the dictionary entry pronunciation.
		self._entry_list.AppendColumn(_("Pronunciation"), width=cast(int, self.scaleSize(180)))
		# Translators: Column header for the ECI dictionary slot type.
		self._entry_list.AppendColumn(_("Type"), width=cast(int, self.scaleSize(110)))
		# Translators: Column header for the dictionary entry provenance.
		self._entry_list.AppendColumn(_("Source"), width=cast(int, self.scaleSize(240)))
		sizer_helper.addItem(self._entry_list, proportion=1, flag=wx.EXPAND)

		button_helper = guiHelper.ButtonHelper(orientation=wx.HORIZONTAL)
		self._add_button = button_helper.addButton(
			parent=self,
			# Translators: Button for adding a personal dictionary entry.
			label=_("&Add"),
		)
		self._add_button.Bind(wx.EVT_BUTTON, self._onAdd)
		self._edit_button = button_helper.addButton(
			parent=self,
			# Translators: Button for editing or customizing a dictionary entry.
			label=_("&Edit"),
		)
		self._edit_button.Bind(wx.EVT_BUTTON, self._onEdit)
		self._set_details_button = button_helper.addButton(
			parent=self,
			# Translators: Button for showing provenance details for the selected Managed Dictionary Set entry.
			label=_("Set &Details..."),
		)
		self._set_details_button.Bind(wx.EVT_BUTTON, self._onSetDetails)
		self._remove_button = button_helper.addButton(
			parent=self,
			# Translators: Button for removing a selected personal dictionary entry.
			label=_("&Remove"),
		)
		self._remove_button.Bind(wx.EVT_BUTTON, self._onRemove)
		self._export_button = button_helper.addButton(
			parent=self,
			# Translators: Button for exporting personal dictionary entries to a shareable file.
			label=_("E&xport..."),
		)
		self._export_button.Bind(wx.EVT_BUTTON, self._onExport)
		button_helper.sizer.AddStretchSpacer()
		self._remove_all_button = button_helper.addButton(
			parent=self,
			# Translators: Button for removing all personal entries for the current language.
			label=_("Remove all personal entries"),
		)
		self._remove_all_button.Bind(wx.EVT_BUTTON, self._onRemoveAll)
		sizer_helper.addItem(button_helper, flag=wx.EXPAND)

	def _defaultLanguage(self) -> str:
		# Active-Eloquence-voice detection arrives with ticket #20.
		return "enu"

	def _current_language(self) -> str:
		return self._language_codes[self._language_choice.GetSelection()]

	def _current_managed_set(self) -> ManagedSet | None:
		selection = self._set_choice.GetSelection()
		return self._managed_sets[selection] if selection < len(self._managed_sets) else None

	def _current_view(self) -> EffectiveView:
		language = self._current_language()
		managed_set = self._current_managed_set()
		cache_key = (language, managed_set.id if managed_set is not None else None)
		view = self._views.get(cache_key)
		if view is None:
			view = EffectiveView(language, managed_set, self._overlay)
			self._views[cache_key] = view
		return view

	def _getListItemText(self, item: int, column: int) -> str:
		row = self._rows[item]
		return (
			row.word,
			row.pronunciation,
			self._slot_labels[row.slot],
			row.source,
		)[column]

	def _selected_row(self) -> EffectiveRow | None:
		selection = cast(int, self._entry_list.GetFirstSelected())
		return self._rows[selection] if 0 <= selection < len(self._rows) else None

	def _updateButtons(self) -> None:
		row = self._selected_row()
		self._edit_button.Enable(row is not None)
		self._set_details_button.Enable(
			row is not None and row.kind is RowKind.MANAGED and self._current_managed_set() is not None,
		)
		self._remove_button.Enable(
			row is not None and row.kind in (RowKind.PERSONAL, RowKind.OVERRIDE),
		)

	def _refresh_rows(
		self,
		focus_target: tuple[str, Slot] | None = None,
		fallback_index: int = 0,
	) -> None:
		self._rows = self._current_view().rows(
			self._filter_control.GetValue(),
			self._show_filters[self._show_choice.GetSelection()],
		)
		self._entry_list.SetItemCount(len(self._rows))
		if self._rows:
			self._entry_list.RefreshItems(0, len(self._rows) - 1)
			target_index = min(max(fallback_index, 0), len(self._rows) - 1)
			if focus_target is not None:
				target_word, target_slot = focus_target
				target_identity = key_identity(target_word, target_slot)
				for index, row in enumerate(self._rows):
					if row.slot is target_slot and key_identity(row.word, row.slot) == target_identity:
						target_index = index
						break
			self._entry_list.Select(target_index)
			self._entry_list.Focus(target_index)
		else:
			self._entry_list.Refresh()
		self._updateButtons()

	def _refreshAfterMutation(
		self,
		focus_target: tuple[str, Slot] | None = None,
		fallback_index: int = 0,
	) -> None:
		self._views.clear()
		self._refresh_rows(focus_target, fallback_index)
		self._entry_list.SetFocus()

	def _onViewChanged(self, _event: wx.CommandEvent) -> None:
		self._refresh_rows()

	def _onFilterChanged(self, _event: wx.CommandEvent) -> None:
		self._refresh_rows()

	def _onSelectionChanged(self, _event: wx.ListEvent) -> None:
		self._updateButtons()

	def _confirmReplace(self, word: str, slot: Slot) -> bool:
		message = _(
			# Translators: Confirmation before replacing a personal entry. {word} is the entry word and {type} is its localized type.
			'You already have a personal entry for "{word}" ({type}). Replace it?',
		).format(word=word, type=self._slot_labels[slot])
		return (
			wx.MessageBox(
				message,
				# Translators: Title of the personal-entry replacement confirmation.
				_("Dictionary Entry"),
				wx.YES_NO | wx.NO_DEFAULT,
				self,
			)
			== wx.YES
		)

	def _onAdd(self, _event: wx.CommandEvent) -> None:
		language = self._current_language()
		# Translators: Title of the dialog for adding a personal dictionary entry.
		dialog = EntryDialog(self, _("Add Dictionary Entry"), language)
		result = dialog.ShowModal()
		entry = dialog.entry
		slot = dialog.slot
		dialog.Destroy()
		if result != wx.ID_OK or entry is None:
			self._entry_list.SetFocus()
			return
		if self._overlay.get_entry(language, slot, entry.key) is not None:
			if not self._confirmReplace(entry.key, slot):
				self._entry_list.SetFocus()
				return
			self._overlay.remove_entry(language, slot, entry.key)
		self._overlay.set_entry(language, slot, entry)
		self._refreshAfterMutation((entry.key, slot))

	def _onEdit(self, _event: wx.CommandEvent) -> None:
		row = self._selected_row()
		if row is None:
			return
		language = self._current_language()
		customizing = row.kind is RowKind.MANAGED
		if customizing:
			# Translators: Title of the dialog for creating a personal copy of a managed entry.
			title = _("Customize Dictionary Entry")
		else:
			# Translators: Title of the dialog for editing a personal dictionary entry.
			title = _("Edit Dictionary Entry")
		dialog = EntryDialog(
			self,
			title,
			language,
			slot=row.slot,
			entry=Entry(row.word, row.pronunciation),
			lock_type=True,
			lock_word=customizing,
		)
		result = dialog.ShowModal()
		entry = dialog.entry
		slot = dialog.slot
		dialog.Destroy()
		if result != wx.ID_OK or entry is None:
			self._entry_list.SetFocus()
			return
		old_identity = (row.slot, key_identity(row.word, row.slot))
		new_identity = (slot, key_identity(entry.key, slot))
		collision = self._overlay.get_entry(language, slot, entry.key)
		if new_identity != old_identity and collision is not None:
			if not self._confirmReplace(entry.key, slot):
				self._entry_list.SetFocus()
				return
		self._overlay.remove_entry(language, row.slot, row.word)
		self._overlay.set_entry(language, slot, entry)
		self._refreshAfterMutation((entry.key, slot))

	def _onSetDetails(self, _event: wx.CommandEvent) -> None:
		row = self._selected_row()
		managed_set = self._current_managed_set()
		if row is None or row.kind is not RowKind.MANAGED or managed_set is None:
			return
		dialog = SetDetailsDialog(self, managed_set)
		dialog.ShowModal()
		dialog.Destroy()
		self._entry_list.SetFocus()

	def _onRemove(self, _event: wx.CommandEvent) -> None:
		selection = cast(int, self._entry_list.GetFirstSelected())
		row = self._selected_row()
		if row is None or row.kind not in (RowKind.PERSONAL, RowKind.OVERRIDE):
			return
		self._overlay.remove_entry(self._current_language(), row.slot, row.word)
		self._refreshAfterMutation((row.word, row.slot), selection)

	def _onRemoveAll(self, _event: wx.CommandEvent) -> None:
		language = self._current_language()
		language_name = _language_display_names()[language]
		count = self._overlay.count_for(language)
		if count == 0:
			wx.MessageBox(
				# Translators: Message shown when the current language has no personal entries. {language} is the localized language name.
				_("You have no personal entries for {language}.").format(language=language_name),
				# Translators: Title of a message in the dictionary entry editor.
				_("Eloquence Dictionary Entries"),
				wx.OK,
				self,
			)
			self._entry_list.SetFocus()
			return
		message = ngettext(
			# Translators: Confirmation for removing one personal entry. {language} is the localized language name.
			"Remove your personal entry for {language}? Managed entries are not affected.",
			# Translators: Confirmation for removing multiple personal entries. {count} is the entry count and {language} is the localized language name.
			"Remove all {count} of your personal entries for {language}? Managed entries are not affected.",
			count,
		).format(count=count, language=language_name)
		if (
			wx.MessageBox(
				message,
				# Translators: Title of the remove-all-personal-entries confirmation.
				_("Eloquence Dictionary Entries"),
				wx.YES_NO | wx.NO_DEFAULT,
				self,
			)
			!= wx.YES
		):
			self._entry_list.SetFocus()
			return
		selection = cast(int, self._entry_list.GetFirstSelected())
		selected_row = self._selected_row()
		focus_target = (selected_row.word, selected_row.slot) if selected_row is not None else None
		_removed = self._overlay.remove_language(language)
		self._refreshAfterMutation(focus_target, selection)

	def _onExport(self, _event: wx.CommandEvent) -> None:
		scope_dialog = ExportScopeDialog(self)
		result = scope_dialog.ShowModal()
		all_languages = scope_dialog.all_languages
		scope_dialog.Destroy()
		if result != wx.ID_OK:
			self._entry_list.SetFocus()
			return

		if all_languages:
			scope_languages = tuple(LANGUAGES)
			# Translators: Phrase used in an export filename when entries from every language are included.
			filename_language = _("all languages")
		else:
			current_language = self._current_language()
			scope_languages = (current_language,)
			filename_language = _language_display_names()[current_language]
		default_filename = _(
			# Translators: Default export filename. {language} is a localized language name or "all languages"; {date} is today's date in YYYY-MM-DD form.
			"Eloquence dictionary entries - {language} - {date}.edm-dict",
		).format(language=filename_language, date=date.today().isoformat())
		file_dialog = wx.FileDialog(
			self,
			# Translators: Title of the save dialog for an exported dictionary artifact.
			message=_("Export Dictionary Entries"),
			defaultDir=wx.StandardPaths.Get().GetDocumentsDir(),
			defaultFile=default_filename,
			# Translators: File type shown in the save dialog for Eloquence dictionary artifacts.
			wildcard=_("Eloquence dictionary files (*.edm-dict)|*.edm-dict"),
			style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
		)
		result = file_dialog.ShowModal()
		export_path = Path(file_dialog.GetPath()) if result == wx.ID_OK else None
		file_dialog.Destroy()
		if export_path is None:
			self._entry_list.SetFocus()
			return

		try:
			artifact_bytes = export_edm_dict_artifact(
				self._overlay,
				scope_languages,
				_currentAddonVersion(),
			)
			export_path.write_bytes(artifact_bytes)
		except (EntryValidationError, DictionaryEncodingError, OSError) as error:
			message = _(
				# Translators: Export error message. {error} describes why the artifact could not be written.
				"The dictionary entries could not be exported.\n\n{error}",
			).format(error=error)
			wx.MessageBox(
				message,
				# Translators: Title of an error shown when dictionary entries cannot be exported.
				_("Export Error"),
				wx.OK | wx.ICON_ERROR,
				self,
			)
			self._entry_list.SetFocus()
			return

		wx.MessageBox(
			# Translators: Confirmation shown after personal dictionary entries are exported successfully.
			_("Your personal dictionary entries were exported successfully."),
			# Translators: Title of the successful dictionary-export confirmation.
			_("Export Dictionary Entries"),
			wx.OK | wx.ICON_INFORMATION,
			self,
		)
		self._entry_list.SetFocus()

	@override
	def postInit(self) -> None:
		self._refresh_rows()
		self._entry_list.SetFocus()

	@override
	def onOk(self, evt: wx.CommandEvent) -> None:
		try:
			save_personal_overlay(self._overlay, self._overlay_directory)
		except (EntryValidationError, DictionaryEncodingError, OSError) as error:
			wx.MessageBox(
				str(error),
				# Translators: Title of an error shown when personal dictionary entries cannot be saved.
				_("Eloquence Dictionary Entries"),
				wx.OK | wx.ICON_ERROR,
				self,
			)
			return
		super().onOk(evt)
