import time, re, sys
import gi, os, subprocess
import pickle
from typing import List, Dict, Callable, Tuple, Any
from .presentation import PresentationWindow
from .gtkobj import File, CopyBox, BarChartBox, MultilineEntry
from .constants import AVAILABLE_LLMS, AVAILABLE_PROMPTS, PROMPTS, AVAILABLE_TTS, AVAILABLE_STT
from gi.repository import Gtk, Adw, Pango, Gio, Gdk, GObject, GLib
from .stt import AudioRecorder
from .extra import markwon_to_pango, override_prompts, replace_variables
import threading
import posixpath
import shlex, json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_default_size(1400, 800)
        self.main_program_block = Adw.Flap(flap_position=Gtk.PackType.END, modal=False, swipe_to_close=False,
                                           swipe_to_open=False)
        self.main_program_block.set_name("hide")
        self.check_streams = {"folder": False, "chat": False}
        self.path: str = GLib.get_user_data_dir()
        self.directory: str = GLib.get_user_config_dir()
        self.pip_directory: str = os.path.join(self.directory, "pip")
        sys.path.append(self.pip_directory)
        self.filename: str = "chats.pkl"
        self._load_chat_history()
        self._init_settings()
        self._create_ui()
        GLib.idle_add(self.update_folder)
        GLib.idle_add(self.update_history)
        GLib.idle_add(self.show_chat)
        if not self.settings.get_boolean("welcome-screen-shown"):
            GLib.idle_add(self.show_presentation_window)

    def _load_chat_history(self):
        if not os.path.exists(self.path):
            os.makedirs(self.path)
        filepath: str = os.path.join(self.path, self.filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'rb') as f:
                    self.chats: List[Dict] = pickle.load(f)
            except Exception as e:
                logging.error(f"Error loading chat history: {e}")
                self.chats: List[Dict] = [{"name": _("Chat ") + "1", "chat": []}]
        else:
            self.chats: List[Dict] = [{"name": _("Chat ") + "1", "chat": []}]

    def _init_settings(self):
        settings: Gio.Settings = Gio.Settings.new('io.github.qwersyk.Newelle')
        self.settings: Gio.Settings = settings
        self.update_settings()

    def _create_ui(self):
        self.set_titlebar(Gtk.Box())
        self.chat_panel = Gtk.Box(hexpand_set=True, hexpand=True)
        self.chat_panel.set_size_request(450, -1)
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu = Gio.Menu()
        menu.append(_("Thread editing"), "app.thread_editing")
        menu.append(_("Extensions"), "app.extension")
        menu.append(_("Settings"), "app.settings")
        menu.append(_("Keyboard shorcuts"), "app.shortcuts")
        menu.append(_("About"), "app.about")
        menu_button.set_menu_model(menu)
        self.chat_block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, css_classes=["view"])
        self.chat_header = Adw.HeaderBar(css_classes=["flat", "view"])
        self.chat_header.set_title_widget(Gtk.Label(label=_("Chat"), css_classes=["title"]))
        self.headerbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, hexpand=True)
        self.mute_tts_button = Gtk.Button(css_classes=["flat"], icon_name="audio-volume-muted-symbolic", visible=False)
        self.mute_tts_button.connect("clicked", self.mute_tts)
        self.headerbox.append(self.mute_tts_button)
        self.flap_button_left = Gtk.ToggleButton.new()
        self.flap_button_left.set_icon_name(icon_name='sidebar-show-right-symbolic')
        self.flap_button_left.connect('clicked', self.on_flap_button_toggled)
        self.headerbox.append(child=self.flap_button_left)
        self.chat_header.pack_end(self.headerbox)
        self.left_panel_back_button = Gtk.Button(css_classes=["flat"], visible=False)
        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="go-previous-symbolic"))
        icon.set_icon_size(Gtk.IconSize.INHERIT)
        box = Gtk.Box(halign=Gtk.Align.CENTER)
        box.append(icon)
        self.left_panel_back_button.set_child(box)
        self.left_panel_back_button.connect("clicked", self.go_back_to_chats_panel)
        self.chat_header.pack_start(self.left_panel_back_button)
        self.chat_block.append(self.chat_header)
        self.chat_block.append(Gtk.Separator())
        self.chat_panel.append(self.chat_block)
        self.chat_panel.append(Gtk.Separator())
        self.main = Adw.Leaflet(fold_threshold_policy=True, can_navigate_back=True, can_navigate_forward=True)
        self.streams = []
        self.chats_main_box = Gtk.Box(hexpand_set=True)
        self.chats_main_box.set_size_request(300, -1)
        self.chats_secondary_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        self.chat_panel_header = Adw.HeaderBar(css_classes=["flat"], show_end_title_buttons=False)
        self.chat_panel_header.set_title_widget(Gtk.Label(label=_("History"), css_classes=["title"]))
        self.chats_secondary_box.append(self.chat_panel_header)
        self.chats_secondary_box.append(Gtk.Separator())
        self.chat_panel_header.pack_end(menu_button)
        self.chats_buttons_block = Gtk.ListBox(css_classes=["separators", "background"])
        self.chats_buttons_block.set_selection_mode(Gtk.SelectionMode.NONE)
        self.chats_buttons_scroll_block = Gtk.ScrolledWindow(vexpand=True)
        self.chats_buttons_scroll_block.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.chats_buttons_scroll_block.set_child(self.chats_buttons_block)
        self.chats_secondary_box.append(self.chats_buttons_scroll_block)
        button = Gtk.Button(valign=Gtk.Align.END, css_classes=["suggested-action"], margin_start=7, margin_end=7,
                            margin_top=7, margin_bottom=7)
        button.set_child(Gtk.Label(label=_("Create a chat")))
        button.connect("clicked", self.new_chat)
        self.chats_secondary_box.append(button)
        self.chats_main_box.append(self.chats_secondary_box)
        self.chats_main_box.append(Gtk.Separator())
        self.main.append(self.chats_main_box)
        self.main.append(self.chat_panel)
        self.main.set_visible_child(self.chat_panel)
        self.explorer_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["background", "view"])
        self.explorer_panel.set_size_request(420, -1)
        self.explorer_panel_header = Adw.HeaderBar(css_classes=["flat"])
        self.explorer_panel.append(self.explorer_panel_header)
        self.folder_blocks_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.explorer_panel.append(self.folder_blocks_panel)
        self.set_child(self.main_program_block)
        self.main_program_block.set_content(self.main)
        self.main_program_block.set_flap(self.explorer_panel)
        self.secondary_message_chat_block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.chat_block.append(self.secondary_message_chat_block)
        self.chat_list_block = Gtk.ListBox(css_classes=["separators", "background", "view"])
        self.chat_list_block.set_selection_mode(Gtk.SelectionMode.NONE)
        self.chat_scroll = Gtk.ScrolledWindow(vexpand=True)
        self.chat_scroll_window = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["background", "view"])
        self.chat_scroll.set_child(self.chat_scroll_window)
        drop_target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.COPY)
        drop_target.connect('drop', self.handle_file_drag)
        self.chat_scroll.add_controller(drop_target)
        self.chat_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.chat_scroll_window.append(self.chat_list_block)
        self.notification_block = Adw.ToastOverlay()
        self.notification_block.set_child(self.chat_scroll)
        self.secondary_message_chat_block.append(self.notification_block)
        self.offers_entry_block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                          spacing=6, valign=Gtk.Align.END, halign=Gtk.Align.FILL, margin_bottom=6)
        self.chat_scroll_window.append(self.offers_entry_block)
        self.chat_controls_entry_block = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                                 spacing=6, vexpand=True, valign=Gtk.Align.END,
                                                 halign=Gtk.Align.CENTER, margin_top=6, margin_bottom=6)
        self.chat_scroll_window.append(self.chat_controls_entry_block)
        self.message_suggestion_buttons_array: List[Gtk.Button] = []
        self.chat_stop_button = Gtk.Button(css_classes=["flat"])
        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="media-playback-stop"))
        icon.set_icon_size(Gtk.IconSize.INHERIT)
        box = Gtk.Box(halign=Gtk.Align.CENTER)
        box.append(icon)
        label = Gtk.Label(label=_(" Stop"))
        box.append(label)
        self.chat_stop_button.set_child(box)
        self.chat_stop_button.connect("clicked", self.stop_chat)
        self.chat_stop_button.set_visible(False)
        button_folder_back = Gtk.Button(css_classes=["flat"])
        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="go-previous-symbolic"))
        icon.set_icon_size(Gtk.IconSize.INHERIT)
        box = Gtk.Box(halign=Gtk.Align.CENTER)
        box.append(icon)
        button_folder_back.set_child(box)
        button_folder_back.connect("clicked", self.go_back_in_explorer_panel)
        button_folder_forward = Gtk.Button(css_classes=["flat"])
        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="go-next-symbolic"))
        icon.set_icon_size(Gtk.IconSize.INHERIT)
        box = Gtk.Box(halign=Gtk.Align.CENTER)
        box.append(icon)
        button_folder_forward.set_child(box)
        button_folder_forward.connect("clicked", self.go_forward_in_explorer_panel)
        button_home = Gtk.Button(css_classes=["flat"])
        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="go-home-symbolic"))
        icon.set_icon_size(Gtk.IconSize.INHERIT)
        box = Gtk.Box(halign=Gtk.Align.CENTER)
        box.append(icon)
        button_home.set_child(box)
        button_home.connect("clicked", self.go_home_in_explorer_panel)
        button_reload = Gtk.Button(css_classes=["flat"])
        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="view-refresh-symbolic"))
        icon.set_icon_size(Gtk.IconSize.INHERIT)
        box = Gtk.Box(halign=Gtk.Align.CENTER)
        box.append(icon)
        button_reload.set_child(box)
        button_reload.connect("clicked", self.update_folder)
        box = Gtk.Box(spacing=6)
        box.append(button_folder_back)
        box.append(button_folder_forward)
        box.append(button_home)
        self.explorer_panel_header.pack_start(box)
        box = Gtk.Box(spacing=6)
        box.append(button_reload)
        self.explorer_panel_headerbox = box
        self.main_program_block.set_reveal_flap(False)
        self.explorer_panel_header.pack_end(box)
        self.status: bool = True
        self.chat_controls_entry_block.append(self.chat_stop_button)
        for i in range(self.offers):
            button = Gtk.Button(css_classes=["flat"], margin_start=6, margin_end=6)
            label = Gtk.Label(label=str(i + 1), wrap=True, wrap_mode=Pango.WrapMode.CHAR)
            button.set_child(label)
            button.connect("clicked", self.send_bot_response)
            button.set_visible(False)
            self.offers_entry_block.append(button)
            self.message_suggestion_buttons_array.append(button)
        self.button_clear = Gtk.Button(css_classes=["flat"])
        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="edit-clear-all-symbolic"))
        icon.set_icon_size(Gtk.IconSize.INHERIT)
        box = Gtk.Box(halign=Gtk.Align.CENTER)
        box.append(icon)
        label = Gtk.Label(label=_(" Clear"))
        box.append(label)
        self.button_clear.set_child(box)
        self.button_clear.connect("clicked", self.clear_chat)
        self.button_clear.set_visible(False)
        self.chat_controls_entry_block.append(self.button_clear)
        self.button_continue = Gtk.Button(css_classes=["flat"])
        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="media-seek-forward-symbolic"))
        icon.set_icon_size(Gtk.IconSize.INHERIT)
        box = Gtk.Box(halign=Gtk.Align.CENTER)
        box.append(icon)
        label = Gtk.Label(label=_(" Continue"))
        box.append(label)
        self.button_continue.set_child(box)
        self.button_continue.connect("clicked", self.continue_message)
        self.button_continue.set_visible(False)
        self.chat_controls_entry_block.append(self.button_continue)
        self.regenerate_message_button = Gtk.Button(css_classes=["flat"])
        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="view-refresh-symbolic"))
        icon.set_icon_size(Gtk.IconSize.INHERIT)
        box = Gtk.Box(halign=Gtk.Align.CENTER)
        box.append(icon)
        label = Gtk.Label(label=_(" Regenerate"))
        box.append(label)
        self.regenerate_message_button.set_child(box)
        self.regenerate_message_button.connect("clicked", self.regenerate_message)
        self.regenerate_message_button.set_visible(False)
        self.chat_controls_entry_block.append(self.regenerate_message_button)
        input_box = Gtk.Box(halign=Gtk.Align.FILL, margin_start=6, margin_end=6, margin_top=6, margin_bottom=6,
                            spacing=6)
        input_box.set_valign(Gtk.Align.CENTER)
        self.input_panel = MultilineEntry()
        input_box.append(self.input_panel)
        self.input_panel.set_placeholder(_("Send a message..."))
        self.mic_button = Gtk.Button(css_classes=["suggested-action"], icon_name="audio-input-microphone-symbolic",
                                     width_request=36, height_request=36)
        self.mic_button.set_vexpand(False)
        self.mic_button.set_valign(Gtk.Align.CENTER)
        self.mic_button.connect("clicked", self.start_recording)
        input_box.append(self.mic_button)
        box = Gtk.Box()
        box.set_vexpand(False)
        self.send_button = Gtk.Button(css_classes=["suggested-action"], icon_name="go-next-symbolic", width_request=36,
                                      height_request=36)
        self.send_button.set_vexpand(False)
        self.send_button.set_valign(Gtk.Align.CENTER)
        box.append(self.send_button)
        input_box.append(box)
        self.input_panel.set_on_enter(self.on_entry_activate)
        self.send_button.connect('clicked', self.on_entry_button_clicked)
        self.main.connect("notify::folded", self.handle_main_block_change)
        self.main_program_block.connect("notify::reveal-flap", self.handle_second_block_change)
        self.secondary_message_chat_block.append(Gtk.Separator())
        self.secondary_message_chat_block.append(input_box)
        self.stream_number_variable: int = 0

    def show_presentation_window(self):
        self.presentation_dialog = PresentationWindow("presentation", self.settings, self.directory, self)
        self.presentation_dialog.show()

    def mute_tts(self, button: Gtk.Button):
        if self.tts_enabled:
            self.tts.stop()
        button.set_visible(False)

    def start_recording(self, button: Gtk.Button):
        button.set_icon_name("media-playback-stop-symbolic")
        button.disconnect_by_func(self.start_recording)
        button.remove_css_class("suggested-action")
        button.add_css_class("error")
        button.connect("clicked", self.stop_recording)
        self.recorder: AudioRecorder = AudioRecorder()
        threading.Thread(target=self.recorder.start_recording).start()

    def stop_recording(self, button: Gtk.Button):
        self.recorder.stop_recording(os.path.join(self.directory, "recording.wav"))
        threading.Thread(target=self._stop_recording_async, args=(button,)).start()

    def _stop_recording_async(self, button: Gtk.Button):
        button.set_child(None)
        button.set_icon_name("audio-input-microphone-symbolic")
        button.add_css_class("suggested-action")
        button.remove_css_class("error")
        button.disconnect_by_func(self.stop_recording)
        button.connect("clicked", self.start_recording)
        engine: Dict = AVAILABLE_STT[self.stt_engine]
        recognizer: Handler = engine["class"](self.settings, self.pip_directory)
        result: str | None = recognizer.recognize_file(os.path.join(self.directory, "recording.wav"))
        if result:
            self.input_panel.set_text(result)
            self.on_entry_activate(self.input_panel)
        else:
            self.notification_block.add_toast(Adw.Toast(title=_('Could not recognize your voice'), timeout=2))

    def update_settings(self):
        settings: Gio.Settings = self.settings
        self.offers: int = settings.get_int("offers")
        self.virtualization: bool = settings.get_boolean("virtualization")
        self.memory: int = settings.get_int("memory")
        self.console: bool = settings.get_boolean("console")
        self.hidden_files: bool = settings.get_boolean("hidden-files")
        self.chat_id: int = settings.get_int("chat")
        self.main_path: str = settings.get_string("path")
        self.auto_run: bool = settings.get_boolean("auto-run")
        self.chat: List[Dict] = self.chats[min(self.chat_id, len(self.chats) - 1)]["chat"]
        self.graphic: bool = settings.get_boolean("graphic")
        self.cutom_extra_prompt: bool = settings.get_boolean("custom-extra-prompt")
        self.basic_functionality: bool = settings.get_boolean("basic-functionality")
        self.show_image: bool = settings.get_boolean("show-image")
        self.language_model: str = settings.get_string("language-model")
        self.local_model: str = settings.get_string("local-model")
        self.tts_enabled: bool = settings.get_boolean("tts-on")
        self.tts_program: str = settings.get_string("tts")
        self.tts_voice: str = settings.get_string("tts-voice")
        self.stt_engine: str = settings.get_string("stt-engine")
        self.stt_settings: str = settings.get_string("stt-settings")
        self.external_terminal: str = settings.get_string("external-terminal")
        self.custom_prompts: Dict[str, str] = json.loads(self.settings.get_string("custom-prompts"))
        self.prompts: Dict[str, str] = override_prompts(self.custom_prompts, PROMPTS)
        self._load_model()
        self._load_extensions()

    def _load_model(self):
        if self.language_model in AVAILABLE_LLMS:
            self.model: LLMHandler = AVAILABLE_LLMS[self.language_model]["class"](self.settings,
                                                                               os.path.join(self.directory, "models"))
        else:
            mod: Dict = list(AVAILABLE_LLMS.values())[0]
            self.model: LLMHandler = mod["class"](self.settings, os.path.join(self.directory, "models"))
        self.model.load_model(self.local_model)
        self.bot_prompts: List[str] = [replace_variables(value["prompt"]) for value in self.extensions.values() if value["status"]]
        for prompt in self.bot_prompts:
            self.model.set_history(self.bot_prompts, self)

    def _load_extensions(self):
        self.extensions: Dict[str, Dict] = {}
        extension_path: str = os.path.expanduser("~") + "/.var/app/io.github.qwersyk.Newelle/extension"
        if os.path.exists(extension_path):
            for name in os.listdir(extension_path):
                main_json_path: str = os.path.join(extension_path, name, "main.json")
                if os.path.exists(main_json_path):
                    try:
                        with open(main_json_path, "r") as file:
                            main_json_data: Dict = json.load(file)
                            prompt: str | None = main_json_data.get("prompt")
                            name: str | None = main_json_data.get("name")
                            status: bool | None = main_json_data.get("status")
                            api: str | None = main_json_data.get("api")
                            if api:
                                self.extensions[name] = {"api": api, "status": status, "prompt": prompt}
                    except Exception as e:
                        logging.error(f"Error loading extension data: {e}")
        if os.path.exists(os.path.expanduser(self.main_path)):
            os.chdir(os.path.expanduser(self.main_path))
        else:
            self.main_path = "~"
        if self.tts_program in AVAILABLE_TTS:
            self.tts: TTSHandler = AVAILABLE_TTS[self.tts_program]["class"](self.settings, self.directory)
            self.tts.connect('start', lambda: GLib.idle_add(self.mute_tts_button.set_visible, True))
            self.tts.connect('stop', lambda: GLib.idle_add(self.mute_tts_button.set_visible, False))

    def send_button_start_spinner(self):
        spinner = Gtk.Spinner(spinning=True)
        self.send_button.set_child(spinner)

    def remove_send_button_spinner(self):
        self.send_button.set_child(None)
        self.send_button.set_icon_name("go-next-symbolic")

    def on_entry_button_clicked(self, *a):
        self.on_entry_activate(self.input_panel)

    def handle_second_block_change(self, *a):
        status: bool = self.main_program_block.get_reveal_flap()
        if self.main_program_block.get_name() == "hide" and status:
            self.main_program_block.set_reveal_flap(False)
            return
        elif (self.main_program_block.get_name() == "visible") and (not status):
            self.main_program_block.set_reveal_flap(True)
            return
        status: bool = self.main_program_block.get_reveal_flap()
        header_widget: Gtk.Widget = self.explorer_panel_headerbox if status else self.chat_header
        self.headerbox.unparent()
        if isinstance(header_widget, Adw.HeaderBar) or isinstance(header_widget, Gtk.HeaderBar):
            header_widget.pack_end(self.headerbox)
        elif isinstance(header_widget, Gtk.Box):
            self.explorer_panel_headerbox.append(self.headerbox)
        self.chat_panel_header.set_show_end_title_buttons(not self.main_program_block.get_reveal_flap())
        self.left_panel_back_button.set_visible(self.main.get_folded())

    def on_flap_button_toggled(self, toggle_button: Gtk.ToggleButton):
        self.flap_button_left.set_active(True)
        self.main_program_block.set_name("visible" if self.main_program_block.get_name() == "hide" else "hide")
        self.main_program_block.set_reveal_flap(not self.main_program_block.get_reveal_flap())

    def get_file_button(self, path: str) -> Gtk.Button:
        path = os.path.expanduser(os.path.normpath(path if not path.startswith("./") else self.main_path + path[1:]))
        button = Gtk.Button(css_classes=["flat"], margin_top=5, margin_start=5, margin_bottom=5, margin_end=5)
        button.connect("clicked", self.run_file_on_button_click)
        button.set_name(path)
        box = Gtk.Box()
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        file_name: str = path.split("/")[-1]
        name: str = "folder" if os.path.isdir(path) else ("image-x-generic" if file_name.lower().endswith(('.png', '.jpg')) else "text-x-generic")
        icon = Gtk.Image(icon_name=name)
        icon.set_css_classes(["large"])
        icon.set_valign(Gtk.Align.END)
        icon.set_vexpand(True)
        file_label = Gtk.Label(label=file_name, css_classes=["title-3"], halign=Gtk.Align.START, wrap=True,
                              wrap_mode=Pango.WrapMode.WORD_CHAR)
        file_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        file_box.append(icon)
        file_box.set_size_request(110, 110)
        file_box.append(file_label)
        button.set_child(file_box)
        return button

    def run_file_on_button_click(self, button: Gtk.Button, *a):
        path: str = button.get_name()
        if os.path.exists(path):
            if os.path.isdir(path):
                self.main_path = path
                os.chdir(os.path.expanduser(self.main_path))
                GLib.idle_add(self.update_folder)
            else:
                try:
                    subprocess.run(['xdg-open', path], check=True)
                except subprocess.CalledProcessError as e:
                    logging.error(f"Error opening file: {e}")
                    self.notification_block.add_toast(Adw.Toast(title=_('Error opening file'), timeout=2))
        else:
            self.notification_block.add_toast(Adw.Toast(title=_('File not found'), timeout=2))

    def handle_file_drag(self, DropTarget: Gtk.DropTarget, data: str, x: int, y: int) -> bool:
        if not self.status:
            self.notification_block.add_toast(Adw.Toast(title=_('The file cannot be sent until the program is finished'), timeout=2))
            return False
        for path in data.split("\n"):
            if os.path.exists(path):
                message_label: Gtk.Widget = self.get_file_button(path)
                self.chat.append({"User": "Folder" if os.path.isdir(path) else "File", "Message": " " + path})
                self.add_message("Folder" if os.path.isdir(path) else "File", message_label)
                self.chats[self.chat_id]["chat"] = self.chat
            else:
                self.notification_block.add_toast(Adw.Toast(title=_('The file is not recognized'), timeout=2))
        return True

    def go_back_in_explorer_panel(self, *a):
        self.main_path = os.path.normpath(self.main_path + "/..")
        GLib.idle_add(self.update_folder)

    def go_home_in_explorer_panel(self, *a):
        self.main_path = "~"
        GLib.idle_add(self.update_folder)

    def go_forward_in_explorer_panel(self, *a):
        if self.main_path.endswith("/.."):
            self.main_path = os.path.normpath(self.main_path[:-3])
            GLib.idle_add(self.update_folder)

    def go_back_to_chats_panel(self, button: Gtk.Button):
        self.main.set_visible_child(self.chats_main_box)

    def return_to_chat_panel(self, button: Gtk.Button):
        self.main.set_visible_child(self.chat_panel)

    def continue_message(self, button: Gtk.Button):
        if self.chat and self.chat[-1]["User"] in ["Assistant", "Console", "User"]:
            threading.Thread(target=self.send_message).start()
            self.send_button_start_spinner()
        else:
            self.notification_block.add_toast(Adw.Toast(title=_('You can no longer continue the message.'), timeout=2))

    def regenerate_message(self, *a):
