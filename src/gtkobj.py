import gi, os, subprocess
from gi.repository import Gtk, Pango, Gio, Gdk, GtkSource, GObject, Adw, GLib
import threading
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def apply_css_to_widget(widget, css_string):
    provider = Gtk.CssProvider()
    context = widget.get_style_context()
    try:
        provider.load_from_data(css_string.encode())
        context.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
    except Exception as e:
        logging.error(f"Error applying CSS: {e}")


class File(Gtk.Image):
    def __init__(self, path, file_name):
        icon_name = self._get_icon_name(file_name)
        super().__init__(icon_name=icon_name)
        self.path = path
        self.file_name = file_name
        self.drag_source = Gtk.DragSource.new()
        self.drag_source.set_actions(Gdk.DragAction.COPY)
        self.drag_source.connect("prepare", self.move)
        self.add_controller(self.drag_source)

    def _get_icon_name(self, file_name):
        if os.path.isdir(os.path.join(os.path.expanduser(self.path), file_name)):
            # Use a dictionary for more efficient lookup
            icon_map = {
                "Desktop": "user-desktop",
                "Documents": "folder-documents",
                "Downloads": "folder-download",
                "Music": "folder-music",
                "Pictures": "folder-pictures",
                "Public": "folder-publicshare",
                "Templates": "folder-templates",
                "Videos": "folder-videos",
                ".var/app/io.github.qwersyk.Newelle/Newelle": "user-bookmarks",
            }
            return icon_map.get(file_name, "folder")
        else:
            return "image-x-generic" if file_name.lower().endswith(('.png', '.jpg')) else "text-x-generic"

    def move(self, drag_source, x, y):
        snapshot = Gtk.Snapshot.new()
        self.do_snapshot(self, snapshot)
        paintable = snapshot.to_paintable()
        drag_source.set_icon(paintable, int(x), int(y))
        data = os.path.normpath(os.path.expanduser(f"{self.path}/{self.file_name}"))
        return Gdk.ContentProvider.new_for_value(data)


class MultilineEntry(Gtk.Box):
    def __init__(self):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL)
        self.placeholder = ""
        self.enter_func = None
        self.on_change_func = None
        self._create_widgets()
        self.set_placeholder("")

    def _create_widgets(self):
        # Key handling
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self._on_key_pressed)

        # Scroll and TextView
        scroll = Gtk.ScrolledWindow()
        scroll.set_hexpand(True)
        scroll.set_max_content_height(150)
        scroll.set_propagate_natural_height(True)
        scroll.set_margin_start(10)
        scroll.set_margin_end(10)
        self.append(scroll)

        self.input_panel = Gtk.TextView()
        self.input_panel.set_wrap_mode(Gtk.WrapMode.WORD)
        self.input_panel.set_hexpand(True)
        self.input_panel.set_vexpand(False)
        self.input_panel.set_top_margin(5)
        self.input_panel.add_controller(key_controller)
        self.input_panel.add_css_class("multilineentry")
        apply_css_to_widget(self.input_panel, ".multilineentry { background-color: rgba(0,0,0,0); font-size: 15px;}")
        scroll.set_child(self.input_panel)

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Return and not (state & Gdk.ModifierType.SHIFT_MASK):
            self.handle_enter_key()

    def set_placeholder(self, text):
        self.placeholder = text
        self.input_panel.get_buffer().set_text(text)

    def set_on_enter(self, function):
        self.enter_func = function

    def handle_enter_key(self):
        if self.enter_func:
            GLib.idle_add(self.enter_func, self)

    def get_input_panel(self):
        return self.input_panel

    def set_text(self, text):
        self.input_panel.get_buffer().set_text(text)

    def get_text(self):
        return self.input_panel.get_buffer().get_text(self.input_panel.get_buffer().get_start_iter(), self.input_panel.get_buffer().get_end_iter(), False)

    def set_on_change(self, function):
        self.on_change_func = function
        self.input_panel.get_buffer().connect("changed", self._on_text_changed)

    def _on_text_changed(self, buffer):
        if self.on_change_func:
            self.on_change_func(self)


class CopyBox(Gtk.Box):
    def __init__(self, txt, lang, parent=None, id_message=-1):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=10, margin_start=10,
                         margin_bottom=10, margin_end=10, css_classes=["osd", "toolbar", "code"])
        self.txt = txt
        self.id_message = id_message
        self.parent = parent
        self._create_widgets(lang)

    def _create_widgets(self, lang):
        box = Gtk.Box(halign=Gtk.Align.END)
        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="edit-copy-symbolic"))
        icon.set_icon_size(Gtk.IconSize.INHERIT)
        self.copy_button = Gtk.Button(halign=Gtk.Align.END, margin_end=10, css_classes=["flat"])
        self.copy_button.set_child(icon)
        self.copy_button.connect("clicked", self.copy_button_clicked)
        box.append(self.copy_button)

        self.sourceview = GtkSource.View()
        self.buffer = GtkSource.Buffer()
        self.buffer.set_text(self.txt, -1)
        manager = GtkSource.LanguageManager.new()
        language = manager.get_language(lang)
        self.buffer.set_language(language)
        style_scheme_manager = GtkSource.StyleSchemeManager.new()
        style_scheme = style_scheme_manager.get_scheme('classic')
        self.buffer.set_style_scheme(style_scheme)
        self.sourceview.set_buffer(self.buffer)
        self.sourceview.set_vexpand(True)
        self.sourceview.set_show_line_numbers(True)
        self.sourceview.set_background_pattern(GtkSource.BackgroundPatternType.GRID)
        self.sourceview.set_editable(False)

        style = self._get_style_class(lang)
        main = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        main.set_homogeneous(True)
        label = Gtk.Label(label=lang, halign=Gtk.Align.START, margin_start=10, css_classes=[style, "heading"], wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        main.append(label)
        self.append(main)
        self.append(self.sourceview)
        main.append(box)

        if lang == "python":
            self._add_run_button(box)
        elif lang == "console":
            self._add_console_buttons(box)

    def _get_style_class(self, lang):
        style_map = {
            ("python", "cpp", "php", "objc", "go", "typescript", "lua", "perl", "r", "dart", "sql"): "accent",
            ("java", "javascript", "kotlin", "rust"): "warning",
            ("ruby", "swift", "scala"): "error",
            "console": "",
        }
        for key, value in style_map.items():
            if isinstance(key, tuple) and lang in key:
                return value
            elif isinstance(key, str) and lang == key:
                return value
        return "success"

    def _add_run_button(self, box):
        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="media-playback-start-symbolic"))
        icon.set_icon_size(Gtk.IconSize.INHERIT)
        self.run_button = Gtk.Button(halign=Gtk.Align.END, margin_end=10, css_classes=["flat"])
        self.run_button.set_child(icon)
        self.run_button.connect("clicked", self.run_python)
        self.text_expander = Gtk.Expander(label="Console", css_classes=["toolbar", "osd"], margin_top=10, margin_start=10, margin_bottom=10, margin_end=10)
        self.text_expander.set_expanded(False)
        self.text_expander.set_visible(False)
        box.append(self.run_button)
        self.append(self.text_expander)

    def _add_console_buttons(self, box):
        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="media-playback-start-symbolic"))
        icon.set_icon_size(Gtk.IconSize.INHERIT)
        self.run_button = Gtk.Button(halign=Gtk.Align.END, margin_end=10, css_classes=["flat"])
        self.run_button.set_child(icon)
        self.run_button.connect("clicked", self.run_console)

        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="gnome-terminal-symbolic"))
        icon.set_icon_size(Gtk.IconSize.INHERIT)
        self.terminal_button = Gtk.Button(halign=Gtk.Align.END, margin_end=10, css_classes=["flat"])
        self.terminal_button.set_child(icon)
        self.terminal_button.connect("clicked", self.run_console_terminal)

        self.text_expander = Gtk.Expander(label="Console", css_classes=["toolbar", "osd"], margin_top=10, margin_start=10, margin_bottom=10, margin_end=10)
        console = "None"
        if self.id_message < len(self.parent.chat) and self.parent.chat[self.id_message]["User"] == "Console":
            console = self.parent.chat[self.id_message]["Message"]
        self.text_expander.set_child(Gtk.Label(wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, label=console, selectable=True))
        self.text_expander.set_expanded(False)
        box.append(self.run_button)
        box.append(self.terminal_button)
        self.append(self.text_expander)

    def copy_button_clicked(self, widget):
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set_content(Gdk.ContentProvider.new_for_value(self.txt))
        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="object-select-symbolic"))
        icon.set_icon_size(Gtk.IconSize.INHERIT)
        self.copy_button.set_child(icon)

    def run_console(self, widget, multithreading=False):
        if multithreading:
            icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="emblem-ok-symbolic"))
            icon.set_icon_size(Gtk.IconSize.INHERIT)
            widget.set_child(icon)
            widget.set_sensitive(False)
            code = self.parent.execute_terminal_command(self.txt.split("\n"))
            if self.id_message < len(self.parent.chat) and self.parent.chat[self.id_message]["User"] == "Console":
                self.parent.chat[self.id_message]["Message"] = code[1]
            else:
                self.parent.chat.append({"User": "Console", "Message": " " + code[1]})
            self.text_expander.set_child(Gtk.Label(wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, label=code[1], selectable=True))
            if self.parent.status and len(self.parent.chat) - 1 == self.id_message and self.id_message < len(self.parent.chat) and self.parent.chat[self.id_message]["User"] == "Console":
                self.parent.status = False
                self.parent.update_button_text()
                self.parent.scrolled_chat()
                self.parent.send_message()
            icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="media-playback-start-symbolic"))
            icon.set_icon_size(Gtk.IconSize.INHERIT)
            widget.set_child(icon)
            widget.set_sensitive(True)
        else:
            threading.Thread(target=self.run_console, args=[widget, True]).start()

    def run_console_terminal(self, widget, multithreading=False):
        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="emblem-ok-symbolic"))
        icon.set_icon_size(Gtk.IconSize.INHERIT)
        widget.set_child(icon)
        widget.set_sensitive(False)
        command = self.txt + "; exec bash"
        cmd = self.parent.external_terminal.split()
        arguments = [s.replace("{0}", command) for s in cmd]
        subprocess.Popen(["flatpak-spawn", "--host"] + arguments)

    def run_python(self, widget):
        self.text_expander.set_visible(True)
        t = self.txt.replace("'", '"""')
        console_permissions = ""
        if not self.parent.virtualization:
            console_permissions = "flatpak-spawn --host "
        process = subprocess.Popen(f"""{console_permissions}python3 -c '{t}'""", stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, shell=True)
        stdout, stderr = process.communicate()
        text = "Done"
        if process.returncode != 0:
            text = stderr.decode()
        else:
            if stdout.decode() != "":
                text = stdout.decode()
        self.text_expander.set_child(Gtk.Label(wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, label=text, selectable=True))


class BarChartBox(Gtk.Box):
    def __init__(self, data_dict, percentages):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL, margin_top=10, margin_start=10,
                         margin_bottom=10, margin_end=10, css_classes=["card", "chart"])
        self.data_dict = data_dict
        max_value = max(self.data_dict.values()) if self.data_dict else 1 #Handle empty dictionary
        if percentages and max_value <= 100:
            max_value = 100
        for label, value in self.data_dict.items():
            bar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=10, margin_start=10,
                              margin_bottom=10, margin_end=10)
            bar = Gtk.ProgressBar()
            bar.set_fraction(value / max_value) if max_value else 0 #Handle division by zero
            label = Gtk.Label(label=label, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
            label.set_halign(Gtk.Align.CENTER)
            bar_box.append(label)
            bar_box.append(bar)
            self.append(bar_box)


class ComboRowHelper(GObject.Object):
    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, combo: Adw.ComboRow, options: tuple[tuple[str, str]], selected_value: str):
        super().__init__()
        self.combo = combo
        self.__create_combo(combo, options, selected_value)

    def __create_combo(self, combo: Adw.ComboRow, options: tuple[tuple[str, str]], selected_value: str):
        self.__factory = Gtk.SignalListItemFactory()
        self.__factory.connect("setup", self.__on_setup_listitem)
        self.__factory.connect("bind", self.__on_bind_listitem)
        combo.set_factory(self.__factory)

        self.__store = Gio.ListStore(item_type=self.ItemWrapper)
        for option in options:
            self.__store.append(self.ItemWrapper(option[0], option[1]))
        combo.set_model(self.__store)

        selected_index = next((i for i, item in enumerate(self.__store) if item.value == selected_value), 0)
        combo.set_selected(selected_index)
        combo.connect("notify::selected-item", self.__on_selected)

    class ItemWrapper(GObject.Object):
        def __init__(self, name: str, value: str):
            super().__init__()
            self.name = name
            self.value = value

    def __on_selected(self, combo: Adw.ComboRow, selected_item: GObject.ParamSpec) -> None:
        value = self.__combo.get_selected_item().value
        self.emit("changed", value)

    def __on_setup_listitem(self, factory: Gtk.ListItemFactory, list_item: Gtk.ListItem) -> None:
        label = Gtk.Label()
        list_item.set_child(label)
        list_item.row_w = label

    def __on_bind_listitem(self, factory: Gtk.ListItemFactory, list_item: Gtk.ListItem) -> None:
        label = list_item.get_child()
        label.set_text(list_item.get_item().name)
