from __future__ import absolute_import
import importlib, subprocess
import re
import os, sys
import xml.dom.minidom, html
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ReplaceHelper:
    DISTRO = None

    @staticmethod
    def get_distribution() -> str:
        if ReplaceHelper.DISTRO is None:
            try:
                ReplaceHelper.DISTRO = subprocess.check_output(['flatpak-spawn', '--host', 'bash', '-c', 'lsb_release -ds']).decode('utf-8').strip()
            except subprocess.CalledProcessError as e:
                logging.error(f"Error getting distribution: {e}")
                ReplaceHelper.DISTRO = "Unknown"
        return ReplaceHelper.DISTRO
    
    @staticmethod
    def get_desktop_environment() -> str:
        desktop = os.getenv("XDG_CURRENT_DESKTOP")
        return desktop or "Unknown"

def quote_string(s):
    if "'" in s:
        return "'" + s.replace("'", "'\\''") + "'"
    else:
        return "'" + s + "'"

def replace_variables(text: str, variables: dict) -> str:
    """Replaces variables in a string using a dictionary."""
    for key, value in variables.items():
        text = text.replace("{" + key + "}", str(value))
    return text

def markwon_to_pango(markdown_text):
    markdown_text = html.escape(markdown_text)
    try:
        # Use a more concise approach with a dictionary for mapping
        markdown_mappings = {
            r'\*\*(.*?)\*\*': r'<b>\1</b>',
            r'\*(.*?)\*': r'<i>\1</i>',
            r'`(.*?)`': r'<tt>\1</tt>',
            r'~(.*?)~': r'<span strikethrough="true">\1</span>',
            r'\[(.*?)\]\((.*?)\)': r'<a href="\2">\1</a>',
        }
        for pattern, replacement in markdown_mappings.items():
            markdown_text = re.sub(pattern, replacement, markdown_text)

        # Handle headers separately
        absolute_sizes = ['xx-small', 'x-small', 'small', 'medium', 'large', 'x-large', 'xx-large']
        markdown_text = re.sub(r'^(#+) (.*)$', lambda match: f'<span font_weight="bold" font_size="{absolute_sizes[6 - len(match.group(1)) - 1]}">{match.group(2)}</span>', markdown_text, flags=re.MULTILINE)

        xml.dom.minidom.parseString("<html>" + markdown_text + "</html>")
        return markdown_text
    except Exception as e:
        logging.error(f"Error converting markdown: {e}")
        return markdown_text


def human_readable_size(size: float, decimal_places:int =2) -> str:
    size = int(size)
    unit = ''
    for unit in ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB']:
        if size < 1024.0 or unit == 'PiB':
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"


def find_module(full_module_name):
    """Finds a module by name, returning None if not found."""
    try:
        return importlib.import_module(full_module_name)
    except ImportError:
        return None
    except Exception as e:
        logging.error(f"Error importing module {full_module_name}: {e}")
        return None


def install_module(module, path):
    """Installs a module using pip, handling potential errors."""
    if find_module("pip") is None:
        logging.info("Downloading pip...")
        try:
            subprocess.check_call(["bash", "-c", "wget https://bootstrap.pypa.io/get-pip.py && python get-pip.py"])
        except subprocess.CalledProcessError as e:
            logging.error(f"Error installing pip: {e}")
            return f"Error installing pip: {e}"

    try:
        result = subprocess.check_output([sys.executable, "-m", "pip", "install", "--target", path, module], text=True)
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Error installing module {module}: {e}")
        return f"Error installing module {module}: {e}"


def can_escape_sandbox():
    """Checks if the process can escape the sandbox."""
    try:
        subprocess.check_output(["flatpak-spawn", "--host", "echo", "test"], stderr=subprocess.STDOUT, text=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.warning(f"Sandbox escape check failed: {e}")
        return False
    except FileNotFoundError:
        logging.warning("flatpak-spawn not found. Assuming sandboxed environment.")
        return False


def override_prompts(override_setting, PROMPTS):
    """Overrides prompts with user-defined values."""
    prompt_list = {}
    for prompt in PROMPTS:
        prompt_list[prompt] = override_setting.get(prompt, PROMPTS[prompt])
    return prompt_list
