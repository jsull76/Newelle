import gi, os, shutil, json
from gi.repository import Gtk, Adw, Gio
from newelle_extension_generator import generate_extension_code, install_extension, validate_extension_code
from .llm import LLMHandler
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def handle_file_operations(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        logging.error(f"Error during file operation: {e}")
        return None

def load_extension_data(path: str) -> Dict | None:
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.error(f"Error loading extension data: {e}")
        return None

class Extension(Gtk.Window):
    def __init__(self, app: object):
        Gtk.Window.__init__(self, title=_("Extensions"))
        self.path: str = os.path.expanduser("~") + "/.var/app/io.github.qwersyk.Newelle/extension"
        self.app: object = app
        self.set_default_size(500, 500)
        self.set_transient_for(app.win)
        self.set_modal(True)
        self.set_titlebar(Adw.HeaderBar(css_classes=["flat"]))
        self.notification_block = Adw.ToastOverlay()
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.notification_block.set_child(self.scrolled_window)
        self.set_child(self.notification_block)
        self.update()

    def _create_extension_box(self, name: str, main_json_data: Dict) -> Gtk.Box:
        box = Gtk.Box(margin_top=10, margin_bottom=10, css_classes=["card"], hexpand=True)
        box.append(Gtk.Label(label=f"{name}", margin_top=10, margin_start=10, margin_end=10, margin_bottom=10))
        box_elements = Gtk.Box(valign=Gtk.Align.CENTER, halign=Gtk.Align.END, hexpand=True)
        button = Gtk.Button(css_classes=["flat"], margin_top=10, margin_start=10, margin_end=10, margin_bottom=10)
        button.connect("clicked", self.delete_extension)
        button.set_name(name)
        icon = Gtk.Image.new_from_gicon(Gio.ThemedIcon(name="user-trash-symbolic"))
        icon.set_icon_size(Gtk.IconSize.INHERIT)
        button.set_child(icon)
        switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        switch.connect("notify::state", self.change_status)
        switch.set_name(name)
        switch.set_active(main_json_data.get("status", False))  # Handle missing status gracefully
        box_elements.append(switch)
        box_elements.append(button)
        box.append(box_elements)
        return box

    def update(self):
        self.main = Gtk.Box(margin_top=10, margin_start=10, margin_bottom=10, margin_end=10, valign=Gtk.Align.FILL,
                            halign=Gtk.Align.CENTER, orientation=Gtk.Orientation.VERTICAL)
        self.main.set_size_request(300, -1)
        self.scrolled_window.set_child(self.main)
        if os.path.exists(self.path):
            for name in os.listdir(self.path):
                path: str = os.path.join(self.path, name, "main.json")
                main_json_data: Dict | None = load_extension_data(path)
                if main_json_data and os.path.isdir(os.path.join(self.path, name)):
                    box: Gtk.Box = self._create_extension_box(name, main_json_data)
                    self.main.append(box)
        folder_button = Gtk.Button(label=_("Choose an extension"), css_classes=["suggested-action"], margin_top=10)
        folder_button.connect("clicked", self.on_folder_button_clicked)
        generate_button = Gtk.Button(label=_("Generate Extension"), css_classes=["suggested-action"], margin_top=10)
        generate_button.connect("clicked", self.generate_extension)
        self.main.append(folder_button)
        self.main.append(generate_button)

    def change_status(self, widget: Gtk.Switch, *a):
        name: str = widget.get_name()
        path: str = os.path.join(os.path.join(self.path, name), "main.json")
        main_json_data: Dict | None = load_extension_data(path)
        if main_json_data:
            main_json_data["status"] = widget.get_active()
            if name in self.app.win.extensions:
                self.app.win.extensions[name]["status"] = widget.get_active()
            with open(path, "w") as f:
                json.dump(main_json_data, f)

    def delete_extension(self, widget: Gtk.Button):
        folder_path: str = os.path.join(self.path, widget.get_name())
        if handle_file_operations(shutil.rmtree, folder_path):
            self.notification_block.add_toast(Adw.Toast(title=(widget.get_name() + _(' has been removed'))))
        self.update()

    def on_folder_button_clicked(self, widget: Gtk.Button):
        dialog = Gtk.FileChooserNative(transient_for=self.app.win, title=_("Add extension"), modal=True,
                                       action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.connect("response", self.process_folder)
        dialog.show()

    def process_folder(self, dialog: Gtk.FileChooserNative, response: int):
        if response != Gtk.ResponseType.ACCEPT:
            dialog.destroy()
            return

        file = dialog.get_file()
        if file is None:
            return

        folder_path: str = file.get_path()
        main_json_path: str = os.path.join(folder_path, "main.json")
        main_json_data: Dict | None = load_extension_data(main_json_path)

        if main_json_data:
            name: str | None = main_json_data.get("name")
            prompt: str | None = main_json_data.get("prompt")
            api: str | None = main_json_data.get("api")
            about: str | None = main_json_data.get("about")

            if name and about and prompt and api:
                new_folder_path: str = os.path.join(self.path, name)
                if handle_file_operations(shutil.rmtree, new_folder_path):
                    pass  # Ignore errors if the directory doesn't exist

                if handle_file_operations(shutil.copytree, folder_path, new_folder_path):
                    self.notification_block.add_toast(
                        Adw.Toast(title=(_("Extension added. New extensions will run from the next launch"))))
                    main_json_data["status"] = False
                    with open(os.path.join(new_folder_path, "main.json"), "w") as f:
                        json.dump(main_json_data, f)
                    self.update()
                else:
                    self.notification_block.add_toast(Adw.Toast(title=_('Error copying extension')))
            else:
                self.notification_block.add_toast(Adw.Toast(title=_('The extension is wrong')))
        else:
            self.notification_block.add_toast(Adw.Toast(title=_("This is not an extension")))

        dialog.destroy()

    def generate_extension(self, widget: Gtk.Button):
        dialog = Gtk.Dialog(title=_("Generate Extension"), transient_for=self, modal=True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Generate", Gtk.ResponseType.OK)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=12)
        name_entry = Gtk.Entry(placeholder_text=_("Extension Name"))
        description_entry = Gtk.Entry(placeholder_text=_("Description"))
        functionality_entry = Gtk.Entry(placeholder_text=_("Functionality"))
        vbox.append(name_entry)
        vbox.append(description_entry)
        vbox.append(functionality_entry)
        dialog.get_content_area().append(vbox)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            extension_name: str = name_entry.get_text()
            description: str = description_entry.get_text()
            functionality: str = functionality_entry.get_text()
            if not extension_name or not description or not functionality:
                self.notification_block.add_toast(Adw.Toast(title=_("Please fill all fields")))
                return
            extension_code, valid = generate_extension_code(extension_name, description, functionality, self.app.win.model)
            if valid:
                extension_path: str = os.path.join(self.path, extension_name)
                if install_extension(extension_code, extension_path):
                    self.notification_block.add_toast(Adw.Toast(title=f"Extension '{extension_name}' generated and installed successfully."))
                    self.update()
                else:
                    self.notification_block.add_toast(Adw.Toast(title=f"Error installing extension '{extension_name}'. Check logs for details."))
            else:
                self.notification_block.add_toast(Adw.Toast(title=f"Generated code for extension '{extension_name}' is invalid."))
        dialog.destroy()
