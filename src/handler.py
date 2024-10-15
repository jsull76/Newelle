import os, json
from .extra import find_module, install_module
from typing import Any, Dict, Tuple, Union, List, Callable
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class Handler:
    """Base class for managing modules."""
    key: str = ""
    schema_key: str = ""

    def __init__(self, settings: object, path: str):
        self.settings = settings
        self.path = path

    @staticmethod
    def requires_sandbox_escape() -> bool:
        """Indicates if the handler requires sandbox escape to run commands."""
        return False

    def get_extra_settings(self) -> List[Dict]:
        """Returns extra settings for the handler."""
        return []

    @staticmethod
    def get_extra_requirements() -> List[str]:
        """Returns extra pip requirements for the handler."""
        return []

    def install(self) -> Union[str, bool]:
        """Installs handler requirements, handling potential errors."""
        pip_path = os.path.join(os.path.abspath(os.path.join(self.path, os.pardir)), "pip")
        for module in self.get_extra_requirements():
            result = install_module(module, pip_path)
            if isinstance(result, str) and "Error" in result:  # Check for errors from install_module
                return result
        return self._custom_install() #Call custom installation if defined

    def _custom_install(self) -> bool:
        """Allows for custom installation logic in subclasses."""
        return True #Default to successful installation if not overridden

    def is_installed(self) -> bool:
        """Checks if the handler is installed."""
        for module in self.get_extra_requirements():
            if find_module(module) is None:
                return False
        return True

    def get_setting(self, key: str) -> Any:
        """Gets a setting value, handling potential errors."""
        try:
            j: Dict = json.loads(self.settings.get_string(self.schema_key))
            if self.key not in j or key not in j[self.key]:
                return self.get_default_setting(key)
            return j[self.key][key]
        except (json.JSONDecodeError, KeyError) as e:
            logging.error(f"Error getting setting '{key}': {e}")
            return self.get_default_setting(key)

    def set_setting(self, key: str, value: Any):
        """Sets a setting value, handling potential errors."""
        try:
            j: Dict = json.loads(self.settings.get_string(self.schema_key))
            if self.key not in j:
                j[self.key] = {}
            j[self.key][key] = value
            self.settings.set_string(self.schema_key, json.dumps(j))
        except json.JSONDecodeError as e:
            logging.error(f"Error setting setting '{key}': {e}")

    def get_default_setting(self, key: str) -> Any:
        """Gets the default setting value."""
        default_settings = {s["key"]: s["default"] for s in self.get_extra_settings()}
        return default_settings.get(key)
