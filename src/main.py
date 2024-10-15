import sys
import gi, os

gi.require_version('Gtk', '4.0')
gi.require_version('GtkSource', '5')
gi.require_version('Adw', '1')
import pickle
from gi.repository import Gtk, Adw, Pango, Gio, Gdk, GtkSource, GObject
from .settings import Settings
from .window import MainWindow
from .shortcuts import Shortcuts
from .thread_editing import ThreadEditing
from .extension import Extension
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Move CSS to a separate file (src/style.css) for better organization.


class MyApp(Adw.Application):
    def __init__(self, version: str, **kwargs):
        self.version: str = version
        super().__init__(**kwargs)
        self._load_css() #Load CSS from separate file
        self._create_actions()
        self.connect('activate', self.on_activate)

    def _load_css(self):
        """Loads CSS from a separate file."""
        css_path = os.path.join(os.path.dirname(__file__), "style.css")
        if os.path.exists(css_path):
            css_provider = Gtk.CssProvider()
            try:
                css_provider.load_from_path(css_path)
                Gtk.StyleContext.add_provider_for_display(
                    Gdk.Display.get_default(),
                    css_provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
            except Exception as e:
                logging.error(f"Error loading CSS: {e}")


    def _create_actions(self):
        """Creates application actions."""
        self.create_action('about', self.on_about_action, ['<primary>a'])
        self.create_action('shortcuts', self.on_shortcuts_action, ['<primary>h'])
        self.create_action('settings', self.settings_action, ['<primary>s'])
        self.create_action('thread_editing', self.thread_editing_action, ['<primary>e'])
        self.create_action('extension', self.extension_action, ['<primary>x'])
        self.create_action('reload_chat', self.reload_chat, ['<primary>r'])
        self.create_action('reload_folder', self.reload_folder, ['<primary>e'])
        self.create_action('new_chat', self.new_chat, ['<primary>t'])


    def create_action(self, name: str, callback: Callable, shortcuts: List[str] | None = None):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)

    def on_shortcuts_action(self, *a):
        shortcuts = Shortcuts(self)
        shortcuts.present()

    def on_about_action(self, *a):
        Adw.AboutWindow(transient_for=self.props.active_window,
                        application_name='Newelle',
                        application_icon='io.github.qwersyk.Newelle',
                        developer_name='qwersyk',
                        version=self.version,
                        issue_url='https://github.com/qwersyk/Newelle/issues',
                        website='https://github.com/qwersyk/Newelle',
                        developers=['Yehor Hliebov  https://github.com/qwersyk',
                                    "Francesco Caracciolo https://github.com/FrancescoCaracciolo"],
                        documenters=["Francesco Caracciolo https://github.com/FrancescoCaracciolo"],
                        designers=["Nokse22 https://github.com/Nokse22"],
                        translator_credits="\n".join(
                            ["Amine Saoud (Arabic) https://github.com/amiensa",
                             "Heimen Stoffels (Dutch) https://github.com/Vistaus",
                             "Albano Battistella (Italian) https://github.com/albanobattistella"]),
                        copyright='© 2024 qwersyk').present()

    def thread_editing_action(self, *a):
        threadediting = ThreadEditing(self)
        threadediting.present()

    def settings_action(self, *a):
        settings = Settings(self)
        settings.present()
        settings.connect("close-request", self.close_settings)
        self.settingswindow = settings

    def close_settings(self, *a) -> bool:
        settings = Gio.Settings.new('io.github.qwersyk.Newelle')
        try:
            settings.set_int("chat", self.win.chat_id)
            settings.set_string("path", os.path.normpath(self.win.main_path))
            self.win.update_settings()
            self.settingswindow.destroy()
            return True
        except Exception as e:
            logging.error(f"Error closing settings: {e}")
            return False

    def extension_action(self, *a):
        extension = Extension(self)
        extension.present()

    def close_window(self, *a) -> bool:
        if all(element.poll() is not None for element in self.win.streams):
            return False
        else:
            dialog = Adw.MessageDialog(
                transient_for=self.win,
                heading=_("Terminal threads are still running in the background"),
                body=_("When you close the window, they will be automatically terminated"),
                body_use_markup=True
            )
            dialog.add_response("cancel", _("Cancel"))
            dialog.add_response("close", _("Close"))
            dialog.set_response_appearance("close", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.set_default_response("cancel")
            dialog.set_close_response("cancel")
            dialog.connect("response", self.close_message)
            dialog.present()
            return True

    def close_message(self, a: object, status: str):
        if status == "close":
            for i in self.win.streams:
                i.terminate()
            self.win.destroy()

    def on_activate(self, app: object):
        self.win = MainWindow(application=app)
        self.win.connect("close-request", self.close_window)
        self.win.present()

    def reload_chat(self, *a):
        self.win.show_chat()
        self.win.notification_block.add_toast(
            Adw.Toast(title=_('Chat is rebooted')))

    def reload_folder(self, *a):
        self.win.update_folder()
        self.win.notification_block.add_toast(
            Adw.Toast(title=_('Folder is rebooted')))

    def new_chat(self, *a):
        self.win.new_chat(None)
        self.win.notification_block.add_toast(
            Adw.Toast(title=_('Chat is created')))

    def do_shutdown(self):
        try:
            self.win.save_chat()
            settings = Gio.Settings.new('io.github.qwersyk.Newelle')
            settings.set_int("chat", self.win.chat_id)
            settings.set_string("path", os.path.normpath(self.win.main_path))
            self.win.stream_number_variable += 1
            Gtk.Application.do_shutdown(self)
        except Exception as e:
            logging.error(f"Error during shutdown: {e}")


def main(version: str):
    app = MyApp(application_id="io.github.qwersyk.Newelle", version=version)
    app.run(sys.argv)
