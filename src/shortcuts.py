import gi, os
import pickle
from gi.repository import Gtk, Adw
from typing import List
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class Shortcuts(Gtk.Window):
    def __init__(self, app: object, *args, **kwargs):
        try:
            super().__init__(*args, **kwargs, title=_('Help'))
            self.set_transient_for(app.win)
            self.set_modal(True)
            self.set_titlebar(Adw.HeaderBar(css_classes=["flat"]))
            self._create_shortcuts_ui()
        except Exception as e:
            logging.error(f"Error creating shortcuts window: {e}")

    def _create_shortcuts_ui(self):
        sect_main = Gtk.Box(margin_top=10, margin_start=10, margin_bottom=10, margin_end=10, valign=Gtk.Align.START,
                            halign=Gtk.Align.CENTER)
        gr = Gtk.ShortcutsGroup(title=_("Shortcuts"))
        shortcuts: List[Gtk.ShortcutsShortcut] = [
            Gtk.ShortcutsShortcut(title=_("Reload chat"), accelerator='<primary>r'),
            Gtk.ShortcutsShortcut(title=_("Reload folder"), accelerator='<primary>e'),
            Gtk.ShortcutsShortcut(title=_("New chat"), accelerator='<primary>t'),
            Gtk.ShortcutsShortcut(title=_("Settings"), accelerator='<primary>s'),
            Gtk.ShortcutsShortcut(title=_("About"), accelerator='<primary>a'),
            Gtk.ShortcutsShortcut(title=_("Extensions"), accelerator='<primary>x'),
            Gtk.ShortcutsShortcut(title=_("Thread Editing"), accelerator='<primary>e'),

        ]
        for shortcut in shortcuts:
            gr.append(shortcut)
        sect_main.append(gr)
        self.set_child(sect_main)
