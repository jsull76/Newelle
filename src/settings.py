from typing import Any, Dict, List, Callable, Tuple
import gi
import re, threading, os, json, time, ctypes
from subprocess import Popen
from gi.repository import Gtk, Adw, Gio, GLib

from .handler import Handler

from .stt import STTHandler
from .tts import TTSHandler
from .constants import AVAILABLE_LLMS, AVAILABLE_PROMPTS, AVAILABLE_TTS, AVAILABLE_STT, PROMPTS
from gpt4all import GPT4All
from .llm import GPT4AllHandler, LLMHandler
from .gtkobj import ComboRowHelper, CopyBox, MultilineEntry
from .extra import can_escape_sandbox, override_prompts, human_readable_size
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class Settings(Adw.PreferencesWindow):
    def __init__(self, app: object, headless: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings = Gio.Settings.new('io.github.qwersyk.Newelle')
        if not headless:
            self.set_transient_for(app.win)
        self.set_modal(True)
        self.downloading: Dict[str, bool] = {}
        self.slider_labels: Dict[Gtk.Scale, Gtk.Label] = {}
        self.local_models: List[Dict] = json.loads(self.settings.get_string("available-models"))
        self.directory: str = GLib.get_user_config_dir()
        self.gpt = GPT4AllHandler(self.settings, os.path.join(self.directory, "models"))
        self.custom_prompts: Dict[str, str] = json.loads(self.settings.get_string("custom-prompts"))
        self.prompts: Dict[str, str] = override_prompts(self.custom_prompts, PROMPTS)
        self.sandbox: bool = can_escape_sandbox()
        self.settingsrows: Dict[Tuple[str, str], Dict] = {}
        self._create_ui()

    def _create_ui(self):
        self.general_page = Adw.PreferencesPage()
        self._create_llm_settings()
        self._create_tts_settings()
        self._create_stt_settings()
        self._create_interface_settings()
        self._create_prompt_settings()
        self._create_neural_network_settings()
        self.message = Adw.PreferencesGroup(title=_('The change will take effect after you restart the program.'))
        self.general_page.add(self.message)
        self.add(self.general_page)

    def _create_llm_settings(self):
        self.LLM = Adw.PreferencesGroup(title=_('Language Model'))
        self.general_page.add(self.LLM)
        self.llmbuttons = []
        group = Gtk.CheckButton()
        selected = self.settings.get_string("language-model")
        others_row = Adw.ExpanderRow(title=_('Other LLMs'), subtitle=_("Other available LLM providers"))
        for model_key in AVAILABLE_LLMS:
            row = self.build_row(AVAILABLE_LLMS, model_key, selected, group)
            if "secondary" in AVAILABLE_LLMS[model_key] and AVAILABLE_LLMS[model_key]["secondary"]:
                others_row.add_row(row)
            else:
                self.LLM.add(row)
        self.LLM.add(others_row)

    def _create_tts_settings(self):
        self.TTSgroup = Adw.PreferencesGroup(title=_('Text To Speech'))
        self.general_page.add(self.TTSgroup)
        tts_enabled = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.settings.bind("tts-on", tts_enabled, 'active', Gio.SettingsBindFlags.DEFAULT)
        tts_program = Adw.ExpanderRow(title=_('Text To Speech Program'), subtitle=_("Choose which text to speech to use"))
        tts_program.add_action(tts_enabled)
        self.TTSgroup.add(tts_program)
        group = Gtk.CheckButton()
        selected = self.settings.get_string("tts")
        for tts_key in AVAILABLE_TTS:
            row = self.build_row(AVAILABLE_TTS, tts_key, selected, group)
            tts_program.add_row(row)

    def _create_stt_settings(self):
        self.STTgroup = Adw.PreferencesGroup(title=_('Speech to Text'))
        self.general_page.add(self.STTgroup)
        stt_engine = Adw.ExpanderRow(title=_('Speech To Text Engine'), subtitle=_("Choose which speech recognition engine you want"))
        self.STTgroup.add(stt_engine)
        group = Gtk.CheckButton()
        selected = self.settings.get_string("stt-engine")
        for stt_key in AVAILABLE_STT:
            row = self.build_row(AVAILABLE_STT, stt_key, selected, group)
            stt_engine.add_row(row)

    def _create_interface_settings(self):
        self.interface = Adw.PreferencesGroup(title=_('Interface'))
        self.general_page.add(self.interface)
        row = Adw.ActionRow(title=_("Hidden files"), subtitle=_("Show hidden files"))
        switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        row.add_suffix(switch)
        self.settings.bind("hidden-files", switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        self.interface.add(row)
        row = Adw.ActionRow(title=_("Number of offers"), subtitle=_("Number of message suggestions to send to chat "))
        int_spin = Gtk.SpinButton(valign=Gtk.Align.CENTER)
        int_spin.set_adjustment(Gtk.Adjustment(lower=0, upper=5, step_increment=1, page_increment=10, page_size=0))
        row.add_suffix(int_spin)
        self.settings.bind("offers", int_spin, 'value', Gio.SettingsBindFlags.DEFAULT)
        self.interface.add(row)

    def _create_prompt_settings(self):
        self.prompt = Adw.PreferencesGroup(title=_('Prompt control'))
        self.general_page.add(self.prompt)
        row = Adw.ActionRow(title=_("Auto-run commands"), subtitle=_("Commands that the bot will write will automatically run"))
        switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        row.add_suffix(switch)
        self.settings.bind("auto-run", switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        self.prompt.add(row)
        self.__prompts_entries: Dict[str, MultilineEntry] = {}
        for prompt in AVAILABLE_PROMPTS:
            if not prompt["show_in_settings"]:
                continue
            row = Adw.ExpanderRow(title=prompt["title"], subtitle=prompt["description"])
            if prompt["editable"]:
                self.add_customize_prompt_content(row, prompt["key"])
            switch = Gtk.Switch(valign=Gtk.Align.CENTER)
            row.add_suffix(switch)
            self.settings.bind(prompt["setting_name"], switch, 'active', Gio.SettingsBindFlags.DEFAULT)
            self.prompt.add(row)

    def _create_neural_network_settings(self):
        self.neural_network = Adw.PreferencesGroup(title=_('Neural Network Control'))
        self.general_page.add(self.neural_network)
        row = Adw.ActionRow(title=_("Command virtualization"), subtitle=_("Run commands in a virtual machine"))
        switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        row.add_suffix(switch)
        if not self.sandbox:
            switch.set_active(True)
            self.settings.set_boolean("virtualization", True)
        else:
            switch.set_active(self.settings.get_boolean("virtualization"))
        switch.connect("state-set", self.toggle_virtualization)
        self.neural_network.add(row)
        row = Adw.ExpanderRow(title=_("External Terminal"), subtitle=_("Choose the external terminal where to run the console commands"))
        entry = Gtk.Entry()
        self.settings.bind("external-terminal", entry, 'text', Gio.SettingsBindFlags.DEFAULT)
        row.add_row(entry)
        self.neural_network.add(row)
        row = Adw.ActionRow(title=_("Program memory"), subtitle=_("How long the program remembers the chat "))
        int_spin = Gtk.SpinButton(valign=Gtk.Align.CENTER)
        int_spin.set_adjustment(Gtk.Adjustment(lower=0, upper=30, step_increment=1, page_increment=10, page_size=0))
        row.add_suffix(int_spin)
        self.settings.bind("memory", int_spin, 'value', Gio.SettingsBindFlags.DEFAULT)
        self.neural_network.add(row)

    def build_row(self, constants: Dict, key: str, selected: str, group: Gtk.CheckButton) -> Adw.ActionRow | Adw.ExpanderRow:
        model: Dict = constants[key]
        handler: Handler = self.get_object(constants, key)
        active: bool = model["key"] == selected
        self.settingsrows[(key, self.convert_constants(constants))] = {}
        if len(handler.get_extra_settings()) > 0 or key == "local":
            row = Adw.ExpanderRow(title=model["title"], subtitle=model["description"])
            if key != "local":
                self.add_extra_settings(constants, handler, row)
            else:
                self.llmrow = row
                threading.Thread(target=self.build_local).start()
        else:
            row = Adw.ActionRow(title=model["title"], subtitle=model["description"])
        self.settingsrows[(key, self.convert_constants(constants))]["row"] = row
        button = Gtk.CheckButton(name=key, group=group, active=active)
        button.connect("toggled", self.choose_row, constants)
        self.settingsrows[(key, self.convert_constants(constants))]["button"] = button
        if not self.sandbox and handler.requires_sandbox_escape() or not handler.is_installed():
            button.set_sensitive(False)
        row.add_prefix(button)
        threading.Thread(target=self.add_download_button, args=(handler, row)).start()
        self.add_flatpak_waning_button(handler, row)
        return row

    def get_object(self, constants: Dict, key: str) -> Handler:
        if constants == AVAILABLE_LLMS:
            model = constants[key]["class"](self.settings, os.path.join(self.directory, "pip"))
        elif constants == AVAILABLE_STT:
            model = constants[key]["class"](self.settings, os.path.join(self.directory, "models"))
        elif constants == AVAILABLE_TTS:
            model = constants[key]["class"](self.settings, self.directory)
        else:
            raise Exception("Unknown constants")
        return model

    def convert_constants(self, constants: str | Dict) -> str | Dict:
        if isinstance(constants, str):
            match constants:
                case "tts":
                    return AVAILABLE_TTS
                case "stt":
                    return AVAILABLE_STT
                case "llm":
                    return AVAILABLE_LLMS
                case _:
                    raise Exception("Unknown constants")
        else:
            if constants == AVAILABLE_LLMS:
                return "llm"
            elif constants == AVAILABLE_STT:
                return "stt"
            elif constants == AVAILABLE_TTS:
                return "tts"
            else:
                raise Exception("Unknown constants")

    def get_constants_from_object(self, handler: Handler) -> Dict:
        if isinstance(handler, TTSHandler):
            return AVAILABLE_TTS
        elif isinstance(handler, STTHandler):
            return AVAILABLE_STT
        elif isinstance(handler, LLMHandler):
            return AVAILABLE_LLMS
        else:
            raise Exception("Unknown handler")

    def choose_row(self, button: Gtk.CheckButton, constants: Dict):
        setting_name = ""
        if constants == AVAILABLE_LLMS:
            setting_name = "language-model"
        elif constants == AVAILABLE_TTS:
            setting_name = "tts"
        elif constants == AVAILABLE_STT:
            setting_name = "stt-engine"
        else:
            return
        self.settings.set_string(setting_name, button.get_name())

    def add_extra_settings(self, constants: Dict, handler: Handler, row: Adw.ExpanderRow):
        self.settingsrows[(handler.key, self.convert_constants(constants))] = {"extra_settings": []}
        for setting in handler.get_extra_settings():
            self._add_setting_to_row(setting, constants, handler, row)

    def _add_setting_to_row(self, setting: Dict, constants: Dict, handler: Handler, row: Adw.ExpanderRow):
        if setting["type"] == "entry":
            r = Adw.ActionRow(title=setting["title"], subtitle=setting["description"])
            value = handler.get_setting(setting["key"])
            entry = Gtk.Entry(valign=Gtk.Align.CENTER, text=str(value), name=setting["key"])
            entry.connect("changed", self.setting_change_entry, constants, handler)
            r.add_suffix(entry)
        elif setting["type"] == "toggle":
            r = Adw.ActionRow(title=setting["title"], subtitle=setting["description"])
            toggle = Gtk.Switch(valign=Gtk.Align.CENTER, active=bool(handler.get_setting(setting["key"])), name=setting["key"])
            toggle.connect("state-set", self.setting_change_toggle, constants, handler)
            r.add_suffix(toggle)
        elif setting["type"] == "combo":
            r = Adw.ComboRow(title=setting["title"], subtitle=setting["description"], name=setting["key"])
            helper = ComboRowHelper(r, setting["values"], handler.get_setting(setting["key"]))
            helper.connect("changed", self.setting_change_combo, constants, handler)
        elif setting["type"] == "range":
            r = Adw.ActionRow(title=setting["title"], subtitle=setting["description"], valign=Gtk.Align.CENTER)
            box = Gtk.Box()
            scale = Gtk.Scale(name=setting["key"], round_digits=setting["round-digits"])
            scale.set_range(setting["min"], setting["max"])
            scale.set_value(round(handler.get_setting(setting["key"]), setting["round-digits"]))
            scale.set_size_request(120, -1)
            scale.connect("change-value", self.setting_change_scale, constants, handler)
            label = Gtk.Label(label=str(handler.get_setting(setting["key"])))
            box.append(label)
            box.append(scale)
            self.slider_labels[scale] = label
            r.add_suffix(box)
        else:
            return
        if "website" in setting:
            wbbutton = self.create_web_button(setting["website"])
            r.add_prefix(wbbutton)
        if "folder" in setting:
            wbbutton = self.create_web_button(setting["folder"], folder=True)
            r.add_suffix(wbbutton)
        row.add_row(r)
        self.settingsrows[(handler.key, self.convert_constants(constants))]["extra_settings"].append(r)

    def add_customize_prompt_content(self, row: Adw.ExpanderRow, prompt_name: str):
        box = Gtk.Box()
        entry = MultilineEntry()
        entry.set_text(self.prompts[prompt_name])
        self.__prompts_entries[prompt_name] = entry
        entry.set_name(prompt_name)
        entry.set_on_change(self.edit_prompt)
        wbbutton = Gtk.Button(icon_name="star-filled-rounded-symbolic")
        wbbutton.add_css_class("flat")
        wbbutton.set_valign(Gtk.Align.CENTER)
        wbbutton.set_name(prompt_name)
        wbbutton.connect("clicked", self.restore_prompt)
        box.append(entry)
        box.append(wbbutton)
        row.add_row(box)

    def edit_prompt(self, entry: MultilineEntry):
        prompt_name: str = entry.get_name()
        prompt_text: str = entry.get_text()
        if prompt_text == PROMPTS[prompt_name]:
            del self.custom_prompts[entry.get_name()]
        else:
            self.custom_prompts[prompt_name] = prompt_text
        self.settings.set_string("custom-prompts", json.dumps(self.custom_prompts))

    def restore_prompt(self, button: Gtk.Button):
        prompt_name: str = button.get_name()
        self.prompts[prompt_name] = PROMPTS[prompt_name]
        self.__prompts_entries[prompt_name].set_text(self.prompts[prompt_name])

    def toggle_virtualization(self, toggle: Gtk.Switch, status: bool):
        if not self.sandbox and not status:
            self.show_flatpak_sandbox_notice()
            toggle.set_active(True)
            self.settings.set_boolean("virtualization", True)
        else:
            self.settings.set_boolean("virtualization", status)

    def open_website(self, button: Gtk.Button):
        try:
            Popen(["flatpak-spawn", "--host", "xdg-open", button.get_name()])
        except Exception as e:
            logging.error(f"Error opening website: {e}")

    def on_setting_change(self, constants: Dict, handler: Handler, key: str, force_change: bool = False):
        if not force_change:
            setting_info = next((info for info in handler.get_extra_settings() if info["key"] == key), {})
        else:
            setting_info = {}
        if force_change or ("update_settings" in setting_info and setting_info["update_settings"]):
            row = self.settingsrows[(handler.key, self.convert_constants(constants))]["row"]
            setting_list = self.settingsrows[(handler.key, self.convert_constants(constants))]["extra_settings"]
            for setting_row in setting_list:
                row.remove(setting_row)
            self.add_extra_settings(constants, handler, row)

    def setting_change_entry(self, entry: Gtk.Entry, constants: Dict, handler: Handler):
        handler.set_setting(entry.get_name(), entry.get_text())
        self.on_setting_change(constants, handler, entry.get_name())

    def setting_change_toggle(self, toggle: Gtk.Switch, state: bool, constants: Dict, handler: Handler):
        handler.set_setting(toggle.get_name(), toggle.get_active())
        self.on_setting_change(constants, handler, toggle.get_name())

    def setting_change_scale(self, scale: Gtk.Scale, scroll: object, value: float, constants: Dict, handler: Handler):
        setting: str = scale.get_name()
        digits: int = scale.get_round_digits()
        value: float = round(value, digits)
        self.slider_labels[scale].set_label(str(value))
        handler.set_setting(setting, value)
        self.on_setting_change(constants, handler, setting)

    def setting_change_combo(self, helper: ComboRowHelper, value: str, constants: Dict, handler: Handler):
        handler.set_setting(helper.combo.get_name(), value)
        self.on_setting_change(constants, handler, helper.combo.get_name())

    def add_download_button(self, handler: Handler, row: Adw.ActionRow | Adw.ExpanderRow):
        actionbutton = Gtk.Button(css_classes=["flat"], valign=Gtk.Align.CENTER)
        if not handler.is_installed():
            icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="folder-download-symbolic"))
            actionbutton.connect("clicked", self.install_model, handler)
            actionbutton.add_css_class("accent")
            actionbutton.set_child(icon)
            if isinstance(row, Adw.ActionRow):
                row.add_suffix(actionbutton)
            elif isinstance(row, Adw.ExpanderRow):
                row.add_action(actionbutton)

    def add_flatpak_waning_button(self, handler: Handler, row: Adw.ExpanderRow | Adw.ActionRow | Adw.ComboRow):
        actionbutton = Gtk.Button(css_classes=["flat"], valign=Gtk.Align.CENTER)
        if handler.requires_sandbox_escape() and not self.sandbox:
            icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="warning-outline-symbolic"))
            actionbutton.connect("clicked", self.show_flatpak_sandbox_notice)
            actionbutton.add_css_class("error")
            actionbutton.set_child(icon)
            if isinstance(row, Adw.ActionRow):
                row.add_suffix(actionbutton)
            elif isinstance(row, Adw.ExpanderRow):
                row.add_action(actionbutton)
            elif isinstance(row, Adw.ComboRow):
                row.add_suffix(actionbutton)

    def install_model(self, button: Gtk.Button, handler: Handler):
        spinner = Gtk.Spinner(spinning=True)
        button.set_child(spinner)
        button.set_sensitive(False)
        threading.Thread(target=self.install_model_async, args=(button, handler)).start()

    def install_model_async(self, button: Gtk.Button, model: Handler):
        result = model.install()
        if isinstance(result, str) and "Error" in result:
            logging.error(f"Error installing model: {result}")
            dialog = Adw.MessageDialog(
                transient_for=self,
                heading=_("Error installing model"),
                body=result,
                body_use_markup=True
            )
            dialog.add_response("close", _("Close"))
            dialog.set_close_response("close")
            dialog.present()
        elif model.is_installed():
            self.on_setting_change(self.get_constants_from_object(model), model, "", True)
        button.set_child(None)
        button.set_sensitive(False)
        checkbutton = self.settingsrows[(model.key, self.convert_constants(self.get_constants_from_object(model)))]["button"]
        checkbutton.set_sensitive(True)

    def refresh_models(self, action: object):
        models: List[Dict] = GPT4All.list_models()
        self.settings.set_string("available-models", json.dumps(models))
        self.local_models: List[Dict] = models
        self.build_local()

    def build_local(self):
        if len(self.local_models) == 0:
            self.refresh_models(None)
        radio = Gtk.CheckButton()
        actionbutton = Gtk.Button(css_classes=["flat"], valign=Gtk.Align.CENTER)
        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="update-symbolic"))
        actionbutton.connect("clicked", self.refresh_models)
        actionbutton.add_css_class("accent")
        actionbutton.set_child(icon)
        self.llmrow.add_action(actionbutton)
        self.add_extra_settings(AVAILABLE_LLMS, self.gpt, self.llmrow)
        for row in self.settingsrows["local", self.convert_constants(AVAILABLE_LLMS)]["extra_settings"]:
            if row.get_name() == "custom_model":
                button = Gtk.CheckButton()
                button.set_group(radio)
                button.set_active(self.settings.get_string("local-model") == "custom")
                button.set_name("custom")
                button.connect("toggled", self.choose_local_model)
                row.add_prefix(button)
                if len(self.gpt.get_custom_model_list()) == 0:
                    button.set_sensitive(False)
        self.rows: Dict[str, Dict] = {}
        self.model_threads: Dict[str, List] = {}
        for model in self.local_models:
            available: bool = self.gpt.model_available(model["filename"])
            active: bool = model["filename"] == self.settings.get_string("local-model")
            subtitle: str = _(" RAM Required: ") + str(model["ramrequired"]) + "GB"
            subtitle += "\n" + _(" Parameters: ") + model["parameters"]
            subtitle += "\n" + _(" Size: ") + human_readable_size(model["filesize"], 1)
            subtitle += "\n" + re.sub('<[^<]+?>', '', model["description"]).replace("</ul", "")
            r = Adw.ActionRow(title=model["name"], subtitle=subtitle)
            button = Gtk.CheckButton()
            button.set_group(radio)
            button.set_active(active)
            button.set_name(model["filename"])
            button.connect("toggled", self.choose_local_model)
            button.set_sensitive(available)
            actionbutton = Gtk.Button(css_classes=["flat"], valign=Gtk.Align.CENTER)
            icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="user-trash-symbolic" if available else "folder-download-symbolic"))
            icon.set_icon_size(Gtk.IconSize.INHERIT)
            actionbutton.set_child(icon)
            actionbutton.set_name(model["filename"])
            actionbutton.connect("clicked", self.download_local_model if not available else self.remove_local_model)
            actionbutton.add_css_class("error" if available else "accent")
            self.rows[model["filename"]] = {"radio": button}
            r.add_prefix(button)
            r.add_suffix(actionbutton)
            self.llmrow.add_row(r)

    def choose_local_model(self, button: Gtk.CheckButton):
        if button.get_active():
            self.settings.set_string("local-model", button.get_name())

    def download_local_model(self, button: Gtk.Button):
        model: str = button.get_name()
        filesize: int = next((x["filesize"] for x in self.local_models if x["filename"] == model), 0)
        box = Gtk.Box(homogeneous=True, spacing=4)
        box.set_orientation(Gtk.Orientation.VERTICAL)
        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="folder-download-symbolic"))
        icon.set_icon_size(Gtk.IconSize.INHERIT)
        progress = Gtk.ProgressBar(hexpand=False)
        progress.set_size_request(4, 4)
        box.append(icon)
        box.append(progress)
        button.set_child(box)
        button.disconnect_by_func(self.download_local_model)
        button.connect("clicked", self.remove_local_model)
        th = threading.Thread(target=self.download_model_thread, args=(model, button, progress))
        self.model_threads[model] = [th, 0]
        th.start()

    def update_download_status(self, model: str, filesize: int, progressbar: Gtk.ProgressBar):
        file: str = os.path.join(self.gpt.modelspath, model) + ".part"
        while model in self.downloading and self.downloading[model]:
            try:
                currentsize: int = os.path.getsize(file)
                perc: float = currentsize / int(filesize)
                progressbar.set_fraction(perc)
            except Exception as e:
                logging.error(f"Error updating download status: {e}")
            time.sleep(1)

    def download_model_thread(self, model: str, button: Gtk.Button, progressbar: Gtk.ProgressBar):
        self.model_threads[model][1] = threading.current_thread().ident
        self.downloading[model] = True
        threading.Thread(target=self.update_download_status, args=(model, self.local_models[self.local_models.index(next((x for x in self.local_models if x["filename"] == model), {}))]["filesize"], progressbar)).start()
        self.gpt.download_model(model)
        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="user-trash-symbolic"))
        icon.set_icon_size(Gtk.IconSize.INHERIT)
        button.add_css_class("error")
        button.set_child(icon)
        self.downloading[model] = False
        self.rows[model]["radio"].set_sensitive(True)

    def remove_local_model(self, button: Gtk.Button):
        model: str = button.get_name()
        if model in self.downloading and self.downloading[model]:
            self.downloading[model] = False
            if model in self.model_threads:
                thid = self.model_threads[model][1]
                res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thid), ctypes.py_object(SystemExit))
                if res > 1:
                    ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thid), 0)
        try:
            os.remove(os.path.join(self.gpt.modelspath, model))
            button.add_css_class("accent")
            if model in self.downloading:
                self.downloading[model] = False
            icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="folder-download-symbolic"))
            button.disconnect_by_func(self.remove_local_model)
            button.connect("clicked", self.download_local_model)
            button.add_css_class("accent")
            button.remove_css_class("error")
            icon.set_icon_size(Gtk.IconSize.INHERIT)
            button.set_child(icon)
        except Exception as e:
            logging.error(f"Error removing local model: {e}")

    def create_web_button(self, website: str, folder: bool = False) -> Gtk.Button:
        wbbutton = Gtk.Button(icon_name="internet-symbolic" if not folder else "search-folder-symbolic")
        wbbutton.add_css_class("flat")
        wbbutton.set_valign(Gtk.Align.CENTER)
        wbbutton.set_name(website)
        wbbutton.connect("clicked", self.open_website)
        return wbbutton

    def show_flatpak_sandbox_notice(self, el: object = None):
        dialog = Adw.MessageDialog(
            title="Permission Error",
            modal=True,
            transient_for=self,
            destroy_with_parent=True
        )
        dialog.set_heading(_("Not enough permissions"))
        dialog.set_body_use_markup(True)
        dialog.set_body(_("Newelle does not have enough permissions to run commands on your system, please run the following command"))
        dialog.add_response("close", _("Understood"))
        dialog.set_default_response("close")
        dialog.set_extra_child(CopyBox("flatpak --user override --talk-name=org.freedesktop.Flatpak --filesystem=home io.github.qwersyk.Newelle", "bash", parent=self))
        dialog.set_close_response("close")
        dialog.set_response_appearance("close", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect('response', lambda dialog, response_id: dialog.destroy())
        dialog.present()


class TextItemFactory(Gtk.ListItemFactory):
    def create_widget(self, item: str) -> Gtk.Label:
        label: Gtk.Label = Gtk.Label()
        return label

    def bind_widget(self, widget: Gtk.Label, item: str):
        widget.set_text(item)
