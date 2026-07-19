"""Read-only effective-entry editor dialog for Eloquence dictionaries."""

# The wx stubs leave many member types partially unknown, and wx GUI construction
# discards returned sizer items pervasively, so relax those two rules file-wide.
# pyright: reportUnknownMemberType=false, reportUnusedCallResult=false

from __future__ import annotations

from pathlib import Path
from typing import cast, override

import addonHandler
from gui import guiHelper
from gui.nvdaControls import AutoWidthColumnListCtrl
from gui.settingsDialogs import SettingsDialog
from logHandler import log
import NVDAState
import wx

from .ecidic.effective import EffectiveRow, EffectiveView, ShowFilter
from .ecidic.languages import LANGUAGES
from .ecidic.model import Slot
from .ecidic.overlay import load_personal_overlay
from .ecidic.sets import ManagedSet, discover_managed_sets


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


def _available_provider_paths() -> tuple[Path, ...]:
	return tuple(
		Path(addon.path) for addon in addonHandler.getAvailableAddons() if not addon.isPendingInstall
	)


class EloquenceDictionariesDialog(SettingsDialog):
	"""Standalone read-only editor for the effective pronunciation entries."""

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
		overlay_directory = Path(NVDAState.WritePaths.configDir) / "eciDictionaries" / "personal"
		self._overlay, overlay_diagnostics = load_personal_overlay(overlay_directory)
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
				# Translators: Explains that this dialog's Managed Dictionary Set choice is only a viewer.
				label=_(
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
		# Translators: Column header for the dictionary entry key.
		self._entry_list.AppendColumn(_("Word"), width=cast(int, self.scaleSize(145)))
		# Translators: Column header for the dictionary entry pronunciation.
		self._entry_list.AppendColumn(_("Pronunciation"), width=cast(int, self.scaleSize(180)))
		# Translators: Column header for the ECI dictionary slot type.
		self._entry_list.AppendColumn(_("Type"), width=cast(int, self.scaleSize(110)))
		# Translators: Column header for the dictionary entry provenance.
		self._entry_list.AppendColumn(_("Source"), width=cast(int, self.scaleSize(240)))
		sizer_helper.addItem(self._entry_list, proportion=1, flag=wx.EXPAND)

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

	def _refresh_rows(self) -> None:
		self._rows = self._current_view().rows(
			self._filter_control.GetValue(),
			self._show_filters[self._show_choice.GetSelection()],
		)
		self._entry_list.SetItemCount(len(self._rows))
		if self._rows:
			self._entry_list.RefreshItems(0, len(self._rows) - 1)
			self._entry_list.Select(0)
			self._entry_list.Focus(0)
		else:
			self._entry_list.Refresh()

	def _onViewChanged(self, _event: wx.CommandEvent) -> None:
		self._refresh_rows()

	def _onFilterChanged(self, _event: wx.CommandEvent) -> None:
		self._refresh_rows()

	@override
	def postInit(self) -> None:
		self._refresh_rows()
		self._entry_list.SetFocus()

	@override
	def onOk(self, evt: wx.CommandEvent) -> None:
		# This read-only slice intentionally performs no Personal Dictionary Overlay write;
		# validation and commit arrive with ticket #19.
		super().onOk(evt)
