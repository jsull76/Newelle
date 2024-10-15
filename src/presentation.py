import gi
from gi.repository import Gtk, Adw, GdkPixbuf
from gi.repository.Gio import Subprocess
from typing import List, Dict, Callable
from .settings import Settings
from .gtkobj import CopyBox
from .extra import can_escape_sandbox
import subprocess
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class PresentationWindow(Adw.Window):
    def __init__(self, title: str, settings: Settings, path: str, parent: Adw.ApplicationWindow):
        super().__init__(title=title, deletable=True, modal=True)
        self.app = parent.get_application()
        self.settings = settings
        self.path = path
        self.set_default_size(640, 700)
        self.set_transient_for(parent)
        self.set_modal(True)
        self._create_ui()
        self.connect("close-request", self.close_window)

    def _create_ui(self):
        mainbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        headerbar = Gtk.HeaderBar(css_classes=["flat"])
        indicator = Adw.CarouselIndicatorDots()
        headerbar.set_title_widget(indicator)
        mainbox.append(headerbar)
        contentbox = Gtk.Box()
        self.previous = Gtk.Button(opacity=0, icon_name="left-large-symbolic", valign=Gtk.Align.CENTER,
                                   margin_start=12, margin_end=12, css_classes=["circular"])
        self.next = Gtk.Button(opacity=1, icon_name="right-large-symbolic", valign=Gtk.Align.CENTER, margin_start=12,
                               margin_end=12, css_classes=["circular", "suggested-action"])
        self.carousel = Adw.Carousel(hexpand=True, vexpand=True, allow_long_swipes=True, allow_scroll_wheel=True,
                                     interactive=True, allow_mouse_drag=False)
        indicator.set_carousel(self.carousel)
        contentbox.append(self.previous)
        contentbox.append(self.carousel)
        contentbox.append(self.next)
        mainbox.append(contentbox)
        self.carousel.connect("page-changed", self.page_changes)
        self.previous.connect("clicked", self.previous_page)
        self.next.connect("clicked", self.next_page)
        self.build_pages()
        self.set_size_request(640, 700)
        self.set_content(mainbox)

    def close_window(self, _=None):
        self.settings.set_boolean("welcome-screen-shown", True)
        self.destroy()

    def page_changes(self, carousel: Adw.Carousel, page: int):
        if page > 0:
            self.previous.set_opacity(1)
        else:
            self.previous.set_opacity(0)
        if page >= self.carousel.get_n_pages() - 1:
            self.next.set_opacity(0)
        else:
            self.next.set_opacity(1)

    def next_page(self, button: Gtk.Button):
        if self.carousel.get_position() < self.carousel.get_n_pages() - 1:
            self.carousel.scroll_to(self.carousel.get_nth_page(int(self.carousel.get_position() + 1)), True)

    def previous_page(self, button: Gtk.Button):
        if self.carousel.get_position() > 0:
            self.carousel.scroll_to(self.carousel.get_nth_page(int(self.carousel.get_position() - 1)), True)

    def build_pages(self):
        pages = self._create_presentation_pages()
        for page in pages:
            self.carousel.append(self._create_page_from_data(page))

    def _create_presentation_pages(self) -> List[Dict]:
        settings = Settings(self.app, headless=True)
        pages: List[Dict] = [
            {
                "title": _("Welcome to Newelle"),
                "description": _("Your ultimate virtual assistant."),
                "picture": "/io/github/qwersyk/Newelle/images/illustration.svg",
                "actions": [
                    {
                        "label": _("Github Page"),
                        "classes": [],
                        "callback": lambda x: self._open_url("https://github.com/qwersyk/Newelle"),
                    }
                ]
            },
            {
                "title": _("Choose your favourite AI Language Model"),
                "description": _(
                    "Newelle can be used with multiple models and providers!\n<b>Note: It is strongly suggested to read the Guide to LLM page</b>"),
                "widget": self.__steal_from_settings(settings.LLM),
                "actions": [
                    {
                        "label": _("Guide to LLM"),
                        "classes": ["suggested-action"],
                        "callback": lambda x: self._open_url(
                            "https://github.com/qwersyk/Newelle/wiki/User-guide-to-the-available-LLMs"),
                    }
                ]
            },
            {
                "title": _("Extensions"),
                "description": _("You can extend Newelle's functionalities using extensions!"),
                "picture": "/io/github/qwersyk/Newelle/images/extension.svg",
                "actions": [
                    {
                        "label": _("Download extensions"),
                        "classes": ["suggested-action"],
                        "callback": lambda x: self._open_url("https://github.com/topics/newelle-extension"),
                    }
                ]
            }
        ]
        if not can_escape_sandbox():
            pages.append({
                "title": _("Permission Error"),
                "description": _("Newelle does not have enough permissions to run commands on your system."),
                "picture": "/io/github/qwersyk/Newelle/images/error.svg",
                "actions": [
                    {
                        "label": "Learn more",
                        "classes": ["suggested-action"],
                        "callback": lambda x: self._open_url(
                            "https://github.com/qwersyk/Newelle?tab=readme-ov-file#permission"),
                    }
                ]
            })
        pages.append({
            "title": _("Begin using the app"),
            "description": None,
            "widget": self.__create_icon("emblem-default-symbolic"),
            "actions": [
                {
                    "label": _("Start chatting"),
                    "classes": ["suggested-action"],
                    "callback": self.close_window,
                }
            ]
        })
        return pages

    def _create_page_from_data(self, page_data: Dict) -> Gtk.Widget:
        if "picture" in page_data:
            return self.create_image_page(page_data["title"], page_data["description"], page_data["picture"],
                                          page_data["actions"])
        elif "widget" in page_data:
            return self.create_page(page_data["title"], page_data["description"], page_data["widget"],
                                    page_data["actions"])
        else:
            return Gtk.Label(label=_("Invalid page data"))

    def __steal_from_settings(self, widget: Gtk.Widget) -> Gtk.ScrolledWindow:
        scroll = Gtk.ScrolledWindow(propagate_natural_height=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        widget.unparent()
        widget.set_margin_bottom(3)
        widget.set_margin_end(3)
        widget.set_margin_start(3)
        widget.set_margin_top(3)
        scroll.set_child(widget)
        return scroll

    def __create_icon(self, icon_name: str) -> Gtk.Image:
        img = Gtk.Image.new_from_icon_name(icon_name)
        img.set_pixel_size(200)
        return img

    def __create_copybox(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, hexpand=False)
        copy = CopyBox("flatpak --user override --talk-name=org.freedesktop.Flatpak --filesystem=home io.github.qwersyk.Newelle", "bash", parent=box)
        copy.set_hexpand(False)
        copy.set_vexpand(True)
        img = Gtk.Image.new_from_icon_name("warning-outline-symbolic")
        img.add_css_class("error")
        img.set_vexpand(True)
        img.set_pixel_size(200)
        box.append(img)
        box.append(copy)
        return box

    def create_page(self, title: str, description: str | None, widget: Gtk.Widget, actions: List[Dict]) -> Gtk.Widget:
        page = Gtk.Box(hexpand=True, vexpand=True, valign=Gtk.Align.CENTER, orientation=Gtk.Orientation.VERTICAL, spacing=20)
        page.append(widget)
        title_label = Gtk.Label(css_classes=["title-1"])
        title_label.set_halign(Gtk.Align.CENTER)
        title_label.set_text(title)
        page.append(title_label)
        if description:
            description_label = Gtk.Label(single_line_mode=False, max_width_chars=50, wrap=True, css_classes=["body-1"])
            description_label.set_halign(Gtk.Align.CENTER)
            description_label.set_text(description)
            description_label.set_use_markup(True)
            page.append(description_label)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.CENTER, hexpand=False,
                          baseline_position=Gtk.BaselinePosition.CENTER, margin_bottom=20)
        for action in actions:
            button = Gtk.Button(css_classes=action["classes"])
            button.set_label(action["label"])
            button.connect("clicked", action["callback"])
            buttons.append(button)
        page.append(buttons)
        return page

    def create_image_page(self, title: str, description: str | None, picture: str, actions: List[Dict]) -> Gtk.Widget:
        pic = Gtk.Image()
        try:
            pic.set_from_resource(picture)
        except Exception as e:
            logging.error(f"Error loading image resource {picture}: {e}")
            pic = Gtk.Label(label=f"Error loading image: {picture}")
        pic.set_size_request(-1, 300)
        return self.create_page(title, description, pic, actions)

    def _open_url(self, url: str):
        try:
            subprocess.run(["xdg-open", url], check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Error opening URL {url}: {e}")
